#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PTT 文章圖片 OCR：擷取公開圖片網址、限制下載大小，再呼叫 Tesseract。

本模組刻意不依賴雲端視覺 API。Tesseract 不存在時會安全略過，讓一般掃描維持可用。
"""
from __future__ import annotations

import ipaddress
import csv
import io
import os
import re
import shutil
import socket
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

try:
    from PIL import Image, ImageOps
except ImportError:  # Tesseract 仍可直接讀原圖；Pillow 只負責提升海報小字辨識率
    Image = ImageOps = None


URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)
IMAGE_EXT_RE = re.compile(r"\.(?:jpe?g|png|webp|gif|bmp)(?:$|[?#])", re.I)
TRAILING_PUNCTUATION = ").,;:!?]}>'\"，。；：！？）】》」』"
MAX_IMAGE_BYTES = 8 * 1024 * 1024
OCR_TIMEOUT_SECONDS = 20
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
            headers={"User-Agent": "PTT-Assistant-Image-OCR/1.0", "Referer": "https://www.ptt.cc/"},
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


@lru_cache(maxsize=1)
def tesseract_command() -> str | None:
    configured = os.environ.get("TESSERACT_CMD", "").strip()
    if configured and Path(configured).is_file():
        return configured
    return shutil.which("tesseract")


@lru_cache(maxsize=1)
def _tesseract_language(command: str) -> str:
    try:
        proc = subprocess.run(
            [command, "--list-langs"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=15, check=False,
        )
        langs = set(proc.stdout.split())
    except (OSError, subprocess.SubprocessError):
        langs = set()
    if {"chi_tra", "eng"}.issubset(langs):
        return "chi_tra+eng"
    if "chi_tra" in langs:
        return "chi_tra"
    return "eng"


def clean_ocr_text(text: str, max_chars: int = 1800) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in (text or "").splitlines()]
    compact: list[str] = []
    for line in lines:
        if line or (compact and compact[-1]):
            compact.append(line)
    cleaned = "\n".join(compact).strip()
    meaningful = re.sub(r"[^0-9A-Za-z\u3400-\u9fff]", "", cleaned)
    if len(meaningful) < 6:
        return ""
    return cleaned[:max_chars].rstrip()


def _prepare_image(source: Path, target: Path) -> Path:
    """校正手機照片方向、灰階增強對比，並把小圖放大供 Tesseract 讀細字。"""
    if Image is None or ImageOps is None:
        return source
    try:
        Image.MAX_IMAGE_PIXELS = 40_000_000
        with Image.open(source) as opened:
            frame = ImageOps.exif_transpose(opened.copy())
        frame = ImageOps.grayscale(frame)
        frame = ImageOps.autocontrast(frame, cutoff=1)
        longest = max(frame.size)
        if longest and longest < 2200:
            scale = min(3.0, 2200 / longest)
            frame = frame.resize(
                (max(1, round(frame.width * scale)), max(1, round(frame.height * scale))),
                Image.Resampling.LANCZOS,
            )
        frame.save(target, format="PNG", optimize=True)
        return target
    except Exception:
        return source


def _layout_text_from_tsv(tsv: str) -> tuple[str, float]:
    """依 OCR 座標重組文字行與區塊，避免優惠海報的價錢、日期、限制全黏成一段。"""
    lines: dict[tuple[int, int, int], dict] = {}
    reader = csv.DictReader(io.StringIO(tsv or ""), delimiter="\t")
    for row in reader:
        word = (row.get("text") or "").strip()
        if not word:
            continue
        try:
            confidence = float(row.get("conf") or -1)
            if confidence < 15:
                continue
            block = int(row.get("block_num") or 0)
            paragraph = int(row.get("par_num") or 0)
            line = int(row.get("line_num") or 0)
            left = int(row.get("left") or 0)
            top = int(row.get("top") or 0)
        except ValueError:
            continue
        item = lines.setdefault((block, paragraph, line), {
            "words": [], "left": left, "top": top, "conf": [], "block": block,
        })
        item["words"].append((left, word))
        item["left"] = min(item["left"], left)
        item["top"] = min(item["top"], top)
        item["conf"].append(confidence)
    if not lines:
        return "", 0.0

    blocks: dict[int, list[dict]] = {}
    for line in lines.values():
        blocks.setdefault(line["block"], []).append(line)
    ordered_blocks = sorted(
        blocks.values(),
        key=lambda group: (min(x["top"] for x in group), min(x["left"] for x in group)),
    )
    rendered: list[str] = []
    confidences: list[float] = []
    for group in ordered_blocks:
        group_lines = []
        for line in sorted(group, key=lambda x: (x["top"], x["left"])):
            group_lines.append(" ".join(word for _, word in sorted(line["words"])))
            confidences.extend(line["conf"])
        if group_lines:
            rendered.append("\n".join(group_lines))
    text = clean_ocr_text("\n\n".join(rendered))
    meaningful = len(re.sub(r"[^0-9A-Za-z\u3400-\u9fff]", "", text))
    average_confidence = sum(confidences) / len(confidences) if confidences else 0
    # 文字量與信心並重；區塊數只給小幅加分，避免把碎裂誤當好排版。
    score = meaningful * max(average_confidence, 1) + min(len(rendered), 8) * 20
    return text, score


def _run_layout_ocr(command: str, image_path: Path, psm: int) -> tuple[str, float]:
    proc = subprocess.run(
        [command, str(image_path), "stdout", "-l", _tesseract_language(command),
         "--psm", str(psm), "tsv"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=OCR_TIMEOUT_SECONDS, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or "Tesseract 辨識失敗").strip()[:300])
    return _layout_text_from_tsv(proc.stdout)


def ocr_image_url(url: str) -> str:
    """下載單張圖片並回 OCR 文字；任何失敗都交由呼叫端決定是否重試。"""
    command = tesseract_command()
    if not command:
        raise RuntimeError("找不到 Tesseract OCR")
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}:
        suffix = ".img"
    with tempfile.TemporaryDirectory(prefix="ptt-ocr-") as tmp:
        image_path = Path(tmp) / f"source{suffix}"
        _download_image(url, image_path)
        prepared = _prepare_image(image_path, Path(tmp) / "prepared.png")
        # PSM 11 適合海報的散落大字/小字；PSM 6 適合表格狀、整齊的優惠清單。
        candidates = []
        errors = []
        for psm in (11, 6):
            try:
                candidates.append(_run_layout_ocr(command, prepared, psm))
            except Exception as exc:
                errors.append(str(exc))
        if not candidates:
            raise RuntimeError("；".join(errors) or "Tesseract 辨識失敗")
        return max(candidates, key=lambda item: item[1])[0]


def ocr_article_images(body: str, max_images: int = 2) -> dict:
    """辨識文章內圖片，回傳可持久化的狀態；單張壞圖不會中止整篇。"""
    urls = extract_image_urls(body, max_images=max_images)
    if not urls:
        return {"checked": True, "image_urls": [], "text": "", "errors": []}
    if not tesseract_command():
        return {"checked": False, "image_urls": urls, "text": "", "errors": ["找不到 Tesseract OCR"]}
    blocks: list[str] = []
    errors: list[str] = []
    for index, url in enumerate(urls, 1):
        try:
            text = ocr_image_url(url)
            if text:
                blocks.append(f"【圖片 {index}】\n{text}")
        except Exception as exc:
            errors.append(f"{url}：{exc}")
    return {
        "checked": not errors,
        "image_urls": urls,
        "text": "\n\n".join(blocks),
        "errors": errors,
    }


def append_ocr_block(text: str, ocr_text: str) -> str:
    marker = "【圖片文字辨識（自動 OCR，請以原圖為準）】"
    # 重試成功後要能取代先前的部分結果；空結果則移除可能殘留的舊區塊。
    base = (text or "").split(marker, 1)[0].rstrip()
    if not ocr_text:
        return base
    block = f"{marker}\n{ocr_text.strip()}"
    return f"{base}\n\n{block}" if base else block
