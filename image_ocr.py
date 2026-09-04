#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PTT 文章圖片辨識：擷取公開圖片網址、限制下載大小，再交給 Gemini 讀。

**2026-09-04 換引擎**：原本用 Tesseract，實測輸出 46% 是雜訊（最差一篇 73%）。
問題不在調參——優惠海報是格狀排版，品項、價格、期間、取得管道分散在不同格子裡，
逐字擷取的 OCR 結構上就沒辦法把它們配對起來，讀出一堆字卻沒有一句看得懂的優惠。
Gemini 看得懂版面，回來的是「大杯拿鐵／買1送1／100→50元／APP」這種可用的句子。

沒有金鑰或呼叫失敗都會安全略過（`checked=False`，下一輪再試），
不會拖垮一般 PTT 掃描。網址擷取、白名單、SSRF 防護、8 MB 上限全部沿用舊版，
那一層跟用哪個引擎無關。
"""
from __future__ import annotations

import ipaddress
import re
import socket
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

# ♻️ 沿用 gemini_client 的金鑰／重試／備援模型，不要在這裡另寫一套
import gemini_client


URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)
IMAGE_EXT_RE = re.compile(r"\.(?:jpe?g|png|webp|gif|bmp)(?:$|[?#])", re.I)
TRAILING_PUNCTUATION = ").,;:!?]}>'\"，。；：！？）】》」』"
MAX_IMAGE_BYTES = 8 * 1024 * 1024

# 換引擎時把這個字串改掉，build_site 就會把舊引擎讀過的文章全部重讀一次。
# 沒有這個標記的話，Tesseract 時代那批 46% 雜訊會被永遠「沿用」下去。
OCR_ENGINE = "gemini-1"

# ⚠️ 不要加 Referer。2026-09-04 實測：帶 `Referer: https://www.ptt.cc/` 時
# i.imgur.com 一律回 403（防盜連），不帶就 200——而 imgur 是 PTT 最常用的圖床。
# 這個 bug 從 Tesseract 時代就在，只是當時失敗沒印進 log 所以沒人發現。
_REQUEST_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/127.0 Safari/537.36"),
}
# 只連已知公開圖床。PTT 內文由任何人控制，任意網域即使先查 DNS 為公網，
# 仍可能在 requests 第二次解析時 DNS rebinding 到內網；白名單移除該攻擊者控制面。
TRUSTED_IMAGE_HOSTS = {
    "i.imgur.com", "i.mopix.cc", "imgpoi.com", "files.catbox.moe",
    "i.ibb.co", "pbs.twimg.com", "truth.bahamut.com.tw", "upload.cc",
}


def _is_trusted_image_host(host: str) -> bool:
    return (host or "").lower().rstrip(".") in TRUSTED_IMAGE_HOSTS


def extract_image_urls(text: str, max_images: int = 3) -> list[str]:
    """從文章純文字取出可直接下載的圖片網址，保持原順序並去重。"""
    if max_images <= 0:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for match in URL_RE.finditer(text or ""):
        url = match.group(0).rstrip(TRAILING_PUNCTUATION)
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if host == "imgur.com" and re.fullmatch(r"/[A-Za-z0-9]+", parsed.path):
            url = f"https://i.imgur.com{parsed.path}.jpg"
            parsed = urlparse(url)
            host = "i.imgur.com"
        if not _is_trusted_image_host(host):
            continue
        if not (IMAGE_EXT_RE.search(parsed.path) or host == "i.imgur.com"):
            continue
        if url not in seen:
            seen.add(url)
            found.append(url)
        if len(found) >= max_images:
            break
    return found


def _is_public_url(url: str) -> bool:
    """拒絕本機/私有網段，避免由 PTT 文章內容觸發 SSRF。"""
    parsed = urlparse(url)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or not _is_trusted_image_host(parsed.hostname)):
        return False
    try:
        default_port = 443 if parsed.scheme == "https" else 80
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or default_port)}
    except OSError:
        return False
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return False
        if not ip.is_global:
            return False
    return bool(addresses)


def _download_image(url: str, target: Path, session: requests.Session | None = None) -> None:
    client = session or requests.Session()
    current = url
    response = None
    for _ in range(5):
        # 每次連線前先驗證，不能等 requests 跟完 redirect 才檢查（那時 SSRF 已發生）。
        if not _is_public_url(current):
            raise ValueError("圖片網址不是公開網路位址")
        response = client.get(
            current,
            headers=_REQUEST_HEADERS,
            timeout=(8, 20), stream=True, allow_redirects=False,
        )
        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise ValueError("圖片重新導向缺少 Location")
            current = urljoin(current, location)
            continue
        break
    else:
        raise ValueError("圖片重新導向次數過多")
    assert response is not None
    with response:
        response.raise_for_status()
        content_type = (response.headers.get("Content-Type") or "").lower()
        if not content_type.startswith("image/"):
            raise ValueError(f"網址回傳的不是圖片（{content_type or '無 Content-Type'}）")
        declared = int(response.headers.get("Content-Length") or 0)
        if declared > MAX_IMAGE_BYTES:
            raise ValueError("圖片超過 8 MB 上限")
        size = 0
        with target.open("wb") as fh:
            for chunk in response.iter_content(64 * 1024):
                if not chunk:
                    continue
                size += len(chunk)
                if size > MAX_IMAGE_BYTES:
                    raise ValueError("圖片超過 8 MB 上限")
                fh.write(chunk)
        if size == 0:
            raise ValueError("圖片內容是空的")


# ── Gemini 讀圖 ──────────────────────────────────────────────────────

PROMPT = """你在讀一張台灣 PTT 省錢版文章裡的圖片，通常是優惠活動海報或商品截圖。

把圖片裡「對想省錢的人有用」的資訊寫成條列，用繁體中文：
- 品項名稱要完整，連同它自己的價格、折扣規則寫在同一行
- 有活動期間、門檻（滿額多少）、取得管道（門市／APP／官網／會員）就一併寫在該行
- 純裝飾字、店家標語、免責聲明、頁碼、浮水印一律不要

⚠️ 只寫圖片上真的看得到的字。看不清楚就略過那一項，**絕對不要推測或補齊**
——這些內容會直接顯示給使用者當成優惠資訊，猜錯比漏掉嚴重得多。

圖片裡沒有任何優惠資訊（純風景、迷因、表情包、單純的商品照）就只回四個字：無相關資訊
"""

MAX_TEXT_CHARS = 1800
# 單張圖只重試 2 次（而不是預設 3）。一輪要讀二十幾張，每張硬拚重試會把
# 30 分鐘的 Actions job 吃光；這輪讀不到，下一輪還會再讀。
IMAGE_ATTEMPTS = 2


def clean_ocr_text(text: str, max_chars: int = MAX_TEXT_CHARS) -> str:
    """收斂空白與長度。Gemini 回的已經是通順句子，不需要舊版那套雜訊過濾。"""
    lines = []
    for raw in (text or "").splitlines():
        line = re.sub(r"[ \t\u3000]+", " ", raw).strip()
        if line:
            lines.append(line)
    out = "\n".join(lines).strip()
    if len(out) > max_chars:
        out = out[:max_chars].rstrip() + "…"
    return out


def _sniff_mime(data: bytes) -> str:
    """靠 magic bytes 判型別。副檔名是文章作者寫的，不能信。"""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"GIF8"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"BM"):
        return "image/bmp"
    return "image/jpeg"


def read_image_url(url: str, quiet: bool = True) -> str:
    """下載單張圖片交給 Gemini 讀，回純文字。失敗丟例外，由呼叫端決定怎麼辦。"""
    import tempfile

    with tempfile.TemporaryDirectory(prefix="ptt-img-") as tmp:
        path = Path(tmp) / "source.img"
        _download_image(url, path)
        data = path.read_bytes()

    types = gemini_client.parts()
    # 用 generate_ex 拿得到真正的失敗原因。只用 generate() 的話 log 上永遠是
    # 「Gemini 不可用」，分不出速率限制、金鑰錯還是圖片格式問題。
    resp, err = gemini_client.generate_ex(
        [types.Part.from_bytes(data=data, mime_type=_sniff_mime(data)),
         types.Part.from_text(text=PROMPT)],
        label="圖片辨識", quiet=quiet, attempts=IMAGE_ATTEMPTS)
    if resp is None:
        raise RuntimeError(err or "Gemini 沒有回應")
    text = clean_ocr_text(resp.text or "")
    # 模型明講沒東西可讀時回空字串，不要把「無相關資訊」四個字塞進使用者的摘要
    if text.replace(" ", "") in {"無相關資訊", "無相關資訊。"}:
        return ""
    return text


def ocr_article_images(body: str, max_images: int = 2) -> dict:
    """辨識文章內圖片，回傳可持久化的狀態；單張壞圖不會中止整篇。"""
    urls = extract_image_urls(body, max_images=max_images)
    if not urls:
        return {"checked": True, "image_urls": [], "text": "", "errors": [],
                "engine": OCR_ENGINE}
    if not gemini_client.available():
        return {"checked": False, "image_urls": urls, "text": "",
                "errors": ["Gemini 不可用（沒有 GEMINI_API_KEY 或未安裝 google-genai）"],
                "engine": OCR_ENGINE}
    blocks: list[str] = []
    errors: list[str] = []
    for index, url in enumerate(urls, 1):
        try:
            text = read_image_url(url)
            if text:
                blocks.append(f"【圖片 {index}】\n{text}")
        except Exception as exc:                              # noqa: BLE001
            errors.append(f"{url}：{exc}")
    return {
        # 有錯就不標 checked，下一輪會重試這篇（暫時性失敗不該變成永久空白）
        "checked": not errors,
        "image_urls": urls,
        "text": "\n\n".join(blocks),
        "errors": errors,
        "engine": OCR_ENGINE,
    }


MARKER = "【圖片文字辨識（AI 讀圖，請以原圖為準）】"
# 舊版標題。清掉已部署資料裡的 Tesseract 區塊要靠它認得出來。
LEGACY_MARKERS = ("【圖片文字辨識（自動 OCR，請以原圖為準）】",)


def strip_ocr_block(text: str) -> str:
    """移除任何版本的辨識區塊，回純原文。換引擎重讀之前一定要先做這一步，
    否則舊的 Tesseract 亂碼會留在使用者看到的摘要與全文裡。"""
    out = text or ""
    for marker in (MARKER,) + LEGACY_MARKERS:
        out = out.split(marker, 1)[0]
    return out.rstrip()


def append_ocr_block(text: str, ocr_text: str) -> str:
    """將辨識結果以明確警語併入摘要或全文。可重複呼叫，不會重複附加。"""
    base = strip_ocr_block(text)
    if not ocr_text:
        return base
    block = f"{MARKER}\n{ocr_text.strip()}"
    return f"{base}\n\n{block}" if base else block
