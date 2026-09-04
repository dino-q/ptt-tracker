#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓 NOWnews 的「本周咖啡優惠」週更專欄，整理成結構化資料給省錢頁的置頂區塊。

為什麼不用 Dino 給的那個搜尋網址（2026-09-04 實測）：
    https://www.nownews.com/search?q=本周咖啡優惠！ 對程式化存取是**壞的**——
    用真瀏覽器、擋掉廣告、正常 UA 都一樣回「查無符合資料」，連只搜「咖啡」兩字也是。
    改走兩個純 HTTP 的入口（都不需要瀏覽器）：
      ① NOWnews 官方 RSS：真實網址、真實時間，但只有最新 20 筆（全站混合）
      ② 生活分類頁 /cat/life/：伺服器端渲染，18 篇，補 RSS 被洗掉的漏
    Google News RSS 雖然找得到，但 <link> 是 JS 轉址頁、解不出真實網址，所以不用。

收錄範圍（2026-09-04 Dino 定）：
    **只收 NOWnews**（上面兩個來源本來就都是 NOWnews，加別的來源前要先問過），
    標題同時含「咖啡」與優惠字樣就收——不限定「本周咖啡優惠」這個精確片語，
    因為這系列標題不固定，只比對精確片語實測會抓到 0 筆。詳見 COFFEE_RE 上方註解。

抽取用 Gemini：標題與排版都會變，寫死規則撐不住（Dino 2026-09-04 拍板）。
需要環境變數 GEMINI_API_KEY；沒有金鑰時**安靜跳過**，不影響其他掃描。
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET

# ♻️ 沿用共用的 Gemini 呼叫層（金鑰／重試／備援模型）
import gemini_client
from datetime import datetime, timezone, timedelta

TAIPEI = timezone(timedelta(hours=8))
UA = "Mozilla/5.0 (compatible; PTT-Assistant/1.0; +https://dino-q.github.io/ptt-tracker/)"

NOWNEWS_RSS = "https://feed.nownews.com/rss/7d948070-66ea-11f0-a670-0bb14ef7a283"
NOWNEWS_LIFE = "https://www.nownews.com/cat/life/"
ARTICLE_RE = re.compile(r"https://www\.nownews\.com/news/(\d+)")

#: 收錄條件：標題要同時命中「咖啡」與「優惠字樣」。
#
# 為什麼不是只比對「本周咖啡優惠」（2026-09-04 Dino 改的）：
#   這系列標題不固定，實測一週內就有四種寫法——
#     09/04 五六日咖啡優惠！／09/02 7-11拿鐵買20送20…全家咖啡10元
#     08/30 本周咖啡優惠！／08/28 週末咖啡買一送一！
#   只比對精確片語的話，實際抓到 0 筆（那篇 08/30 已被兩個來源洗掉），
#   而當天真正有效的 09/04 那篇（優惠期間 9/2～9/16）反而被擋在外面。
#
# 「優惠字樣」是必要條件，用來擋掉「咖啡廳火災」這種只是提到咖啡的新聞。
COFFEE_RE = re.compile(r"咖啡")
DEAL_RE = re.compile(r"優惠|買\s*\d+\s*送\s*\d+|買一送一|買1送1|半價|寄杯|第\s*2\s*杯|折扣")


def is_coffee_deal(title: str) -> bool:
    t = title or ""
    return bool(COFFEE_RE.search(t) and DEAL_RE.search(t))

# 模型、重試、備援統一在 gemini_client。要換模型設環境變數 GEMINI_MODEL / GEMINI_MODEL_FALLBACK。
#: 3.8 常在尖峰回 503，退到這個（實測穩定，分組一樣正確、偶有錯字）
TIMEOUT = 25

SCHEMA = {
    "type": "object",
    "properties": {
        "活動期間": {"type": "string", "description": "整篇的活動期間；文中沒寫就空字串"},
        "通路": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "名稱": {"type": "string", "description": "例如 7-ELEVEN、全家、星巴克"},
                    "管道": {
                        "type": "string",
                        "description": ("在哪裡才買得到：門市／APP／LINE禮物／會員／官網／外送。"
                                        "文章用「📍門市｜」「📍APP｜」「🟡LINE禮物」這種方式標，"
                                        "照它寫的填；真的沒標就空字串，不要自己猜"),
                    },
                    "期間": {"type": "string",
                             "description": "只放日期範圍，不要把管道混進來；沒寫就空字串"},
                    "優惠": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "品項": {"type": "string"},
                                "說明": {"type": "string", "description": "例如 買1送1、2杯95元"},
                                "原價": {"type": "string", "description": "沒寫就空字串"},
                                "優惠價": {"type": "string", "description": "沒寫就空字串"},
                            },
                            "required": ["品項", "說明", "原價", "優惠價"],
                        },
                    },
                },
                "required": ["名稱", "管道", "期間", "優惠"],
            },
        },
    },
    "required": ["活動期間", "通路"],
}

PROMPT = (
    "這是一篇台灣的超商／咖啡連鎖優惠整理新聞。請用繁體中文（台灣用語）把它整理成結構化資料。\n\n"
    "規則：\n"
    "- **依通路分組**（7-ELEVEN、全家、萊爾富、OKmart、星巴克、路易莎、85度C、全聯、美廉社…），"
    "順序照文章原本的順序\n"
    "- **管道與期間要分開填**：文章會標「📍門市｜8月19日至9月15日」「📍APP｜即日起至9月29日」"
    "「🟡LINE禮物（7-11電子票券）」。管道欄填『門市』『APP』『LINE禮物』，期間欄只放日期。\n"
    "- **同一家超商的不同管道不可以合併**：門市價、APP 價、LINE禮物價常常不一樣，"
    "照文章的分段各自成為一筆（名稱相同、管道不同）\n"
    "- 路易莎那種「出示會員頁面」的，管道填『會員』\n"
    "- 品項寫完整（例如「特選美式／特選拿鐵」而不是「美式」）\n"
    "- 原價／優惠價照文章寫的抄，沒寫就留空字串，不要自己算\n"
    "- 只寫文章真的有的內容，不要推測；廣告、推薦閱讀、記者署名一律不要收\n"
)


def _get(url: str, timeout: int = TIMEOUT) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _from_rss() -> list[dict]:
    """官方 RSS：最新 20 筆，帶真實網址與發佈時間。"""
    out = []
    try:
        root = ET.fromstring(_get(NOWNEWS_RSS))
    except Exception:                                        # noqa: BLE001
        return out
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if ARTICLE_RE.match(link):
            out.append({"title": title, "url": link,
                        "published": (item.findtext("pubDate") or "").strip()})
    return out


def _from_category() -> list[dict]:
    """生活分類頁：伺服器端渲染，補 RSS 被洗掉的漏（週日早上發的文常來不及抓）。"""
    out = []
    try:
        page = _get(NOWNEWS_LIFE).decode("utf-8", "ignore")
    except Exception:                                        # noqa: BLE001
        return out
    for m in re.finditer(
            r'href="(https://www\.nownews\.com/news/\d+)"[^>]*>(?:\s*<[^>]+>)*\s*([^<]{6,120})',
            page):
        out.append({"title": html.unescape(m.group(2)).strip(),
                    "url": m.group(1), "published": ""})
    return out


def find_latest() -> dict | None:
    """兩個來源合併，挑出最新一篇「本周咖啡優惠」。"""
    seen, merged = set(), []
    for item in _from_rss() + _from_category():
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        merged.append(item)
    hits = [i for i in merged if is_coffee_deal(i["title"])]
    if not hits:
        return None
    # 網址尾巴的流水號愈大愈新；RSS 有時間但分類頁沒有，用 id 排最可靠
    hits.sort(key=lambda i: int(ARTICLE_RE.match(i["url"]).group(1)), reverse=True)
    return hits[0]


def article_text(url: str) -> str:
    """把文章 HTML 轉成純文字。先抽文章區塊再去標籤，避免把導覽跟廣告餵給模型。"""
    raw = _get(url).decode("utf-8", "ignore")
    body = raw
    m = re.search(r'<article[^>]*>(.*?)</article>', raw, re.S | re.I)
    if m:
        body = m.group(1)
    body = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", body, flags=re.S | re.I)
    body = re.sub(r"<br\s*/?>|</p>|</div>|</li>|</h\d>", "\n", body, flags=re.I)
    body = re.sub(r"<[^>]+>", " ", body)
    body = html.unescape(body)
    lines = [re.sub(r"[ \t　]+", " ", ln).strip() for ln in body.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)[:14000]


def extract(text: str, title: str) -> dict | None:
    """丟給 Gemini 做結構化。沒金鑰或呼叫失敗都回 None，由呼叫端決定怎麼辦。

    ♻️ 沿用 gemini_client.generate（金鑰／重試／備援模型）。原本這裡自己寫了
    一份一模一樣的重試迴圈，圖片辨識也要用同一套——複製出去兩邊遲早分岔。
    """
    try:
        types = gemini_client.parts()
    except ImportError:
        print("咖啡情報：沒裝 google-genai，跳過結構化擷取")
        return None
    resp = gemini_client.generate(
        [types.Part.from_text(text=f"{PROMPT}\n\n標題：{title}\n\n內文：\n{text}")],
        config=types.GenerateContentConfig(
            response_mime_type="application/json", response_schema=SCHEMA),
        label="咖啡情報")
    if resp is None:
        return None
    try:
        return json.loads((resp.text or "").strip())
    except (ValueError, TypeError) as exc:
        print(f"咖啡情報：回傳不是合法 JSON（{exc}）")
        return None


def build(previous: dict | None = None) -> dict | None:
    """回傳可直接寫成 coffee.json 的內容；抓不到新的就沿用舊的。"""
    latest = find_latest()
    if not latest:
        if previous:
            print("咖啡情報：這輪沒找到新文章，沿用上一版")
        return previous
    if previous and previous.get("article", {}).get("url") == latest["url"]:
        print(f"咖啡情報：仍是同一篇（{latest['title'][:28]}），沿用")
        return previous

    print(f"咖啡情報：發現新文章 {latest['title'][:40]}")
    try:
        text = article_text(latest["url"])
    except Exception as exc:                                  # noqa: BLE001
        print(f"咖啡情報：文章抓取失敗（{type(exc).__name__}），沿用上一版")
        return previous
    data = extract(text, latest["title"])
    if not data:
        return previous          # 擷取不出來就別把舊的好資料蓋掉

    return {
        "updated_at": datetime.now(TAIPEI).strftime("%Y-%m-%d %H:%M"),
        "article": {"title": latest["title"], "url": latest["url"],
                    "published": latest.get("published", ""),
                    "source": "NOWnews 今日新聞"},
        "活動期間": data.get("活動期間", ""),
        "通路": data.get("通路", []),
    }


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="抓 NOWnews 本周咖啡優惠")
    ap.add_argument("--out", default="", help="寫出 JSON 檔（預設只印出來）")
    ap.add_argument("--list", action="store_true", help="只列出兩個來源看得到什麼")
    ap.add_argument("--url", default="", help="指定文章網址（測試抽取用，跳過來源搜尋）")
    args = ap.parse_args()

    if args.url:
        text = article_text(args.url)
        print(f"（內文 {len(text)} 字）")
        data = extract(text, "")
        if not data:
            return 1
        print(json.dumps({
            "updated_at": datetime.now(TAIPEI).strftime("%Y-%m-%d %H:%M"),
            "article": {"title": "", "url": args.url, "published": "",
                        "source": "NOWnews 今日新聞"},
            **data,
        }, ensure_ascii=False, indent=2))
        return 0

    if args.list:
        for item in _from_rss() + _from_category():
            mark = "★" if is_coffee_deal(item["title"]) else " "
            print(f" {mark} {item['title'][:56]}")
            print(f"     {item['url']}")
        return 0

    result = build()
    if not result:
        print("沒有可用的咖啡情報")
        return 1
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        from pathlib import Path
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"已寫出：{args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:                                         # noqa: BLE001
        pass
    sys.exit(main())
