#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓 NOWnews 的「本周咖啡優惠」週更專欄，整理成結構化資料給省錢頁的置頂區塊。

為什麼不用 Dino 給的那個搜尋網址（2026-09-04 實測）：
    https://www.nownews.com/search?q=本周咖啡優惠！ 對程式化存取是**壞的**——
    用真瀏覽器、擋掉廣告、正常 UA 都一樣回「查無符合資料」，連只搜「咖啡」兩字也是。
    改走純 HTTP 的官方入口（都不需要瀏覽器）：
      ① NOWnews 官方 RSS：真實網址、真實時間，但只有最新 20 筆（全站混合）
      ② 生活分類頁 /cat/life/：伺服器端渲染，18 篇，補 RSS 被洗掉的漏
    Google News RSS 雖然找得到，但 <link> 是 JS 轉址頁、解不出真實網址，所以不用。
    2026-10-24 補上「咖啡優惠」「超商咖啡優惠」標籤：首頁只有短暫的最新文章，
    每日掃描會漏掉已被洗出的咖啡新聞；標籤保留同類文章，仍只收 NOWnews。

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
from server import _refresh_log
from datetime import datetime, timezone, timedelta

TAIPEI = timezone(timedelta(hours=8))
UA = "Mozilla/5.0 (compatible; PTT-Assistant/1.0; +https://dino-q.github.io/ptt-tracker/)"

NOWNEWS_RSS = "https://feed.nownews.com/rss/7d948070-66ea-11f0-a670-0bb14ef7a283"
NOWNEWS_LIFE = "https://www.nownews.com/cat/life/"
NOWNEWS_COFFEE_TAGS = (
    "https://www.nownews.com/tag?q=%E5%92%96%E5%95%A1%E5%84%AA%E6%83%A0",
    "https://www.nownews.com/tag?q=%E8%B6%85%E5%95%86%E5%92%96%E5%95%A1%E5%84%AA%E6%83%A0",
)
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


def _from_tags() -> list[dict]:
    """咖啡專屬標籤保留舊文章，避免每日一次的掃描漏掉短暫出現在首頁的新聞。"""
    out = []
    for url in NOWNEWS_COFFEE_TAGS:
        try:
            page = _get(url).decode("utf-8", "ignore")
        except Exception as exc:                              # noqa: BLE001
            _refresh_log(f"咖啡情報 -> 標籤讀取失敗（{url}；{type(exc).__name__}: {exc}）")
            continue
        # 標籤頁的 href 與 aria-label 會含換行，不能沿用分類頁的內文規則。
        items = []
        for anchor in re.findall(r'<a\b[^>]*>', page, re.I):
            href = re.search(r'\bhref=[\"\']([^\"\']+)[\"\']', anchor, re.I)
            label = re.search(r'\baria-label=[\"\']([^\"\']+)[\"\']', anchor, re.I)
            if href and label and ARTICLE_RE.fullmatch(href.group(1).strip()):
                items.append({"title": html.unescape(label.group(1)).strip(),
                              "url": href.group(1).strip(), "published": ""})
        if not items:
            _refresh_log(f"咖啡情報 -> 標籤沒有可解析文章（{url}）")
        out.extend(items)
    return out


def find_articles() -> list[dict]:
    """合併官方入口，保留最近十二篇；單品牌新聞與綜合整理一起收錄。"""
    seen, merged = set(), []
    for item in _from_rss() + _from_category() + _from_tags():
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        merged.append(item)
    hits = [i for i in merged if is_coffee_deal(i["title"])]
    # 網址尾巴的流水號愈大愈新；RSS 有時間但分類頁沒有，用 id 排最可靠
    hits.sort(key=lambda i: int(ARTICLE_RE.match(i["url"]).group(1)), reverse=True)
    return hits[:12]


def find_latest() -> dict | None:
    """保留舊查詢入口；資料建置改用多篇來源。"""
    return next(iter(find_articles()), None)


def article_text(url: str, raw: str | None = None) -> str:
    """把文章 HTML 轉成純文字。先抽文章區塊再去標籤，避免把導覽跟廣告餵給模型。"""
    raw = raw if raw is not None else _get(url).decode("utf-8", "ignore")
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


def article_document(url: str) -> dict | None:
    """先核對官方發稿日期，只抽取近 45 天新聞；舊標籤不能讓去年活動復活。"""
    raw = _get(url).decode("utf-8", "ignore")
    match = re.search(r'"datePublished"\s*:\s*"([^"]+)"', raw)
    if not match:
        return None
    try:
        published = datetime.fromisoformat(match.group(1)).astimezone(TAIPEI)
    except ValueError:
        return None
    age = datetime.now(TAIPEI) - published
    if age < timedelta(0) or age > timedelta(days=45):
        return None
    return {"text": article_text(url, raw), "published": match.group(1)}


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


def merge_articles(articles: list[dict]) -> dict:
    """保留每篇原始抽取，依通路／管道／期間合併，完全相同優惠只顯示一次。"""
    articles = sorted(articles, key=lambda a: int(ARTICLE_RE.fullmatch(a["article"]["url"]).group(1)), reverse=True)[:16]
    channels, groups, seen = [], {}, set()
    for source in articles:
        for original in source.get("通路", []):
            ch = dict(original)
            name = ch.get("名稱", "").strip()
            ch["名稱"] = {"全家便利商店": "全家", "7-11": "7-ELEVEN", "統一超商": "7-ELEVEN",
                          "85度Ｃ": "85度C", "85°C": "85度C"}.get(name, name)
            ch["期間"] = ch.get("期間") or source.get("活動期間", "")
            key = tuple(ch.get(k, "").strip() for k in ("名稱", "管道", "期間"))
            offers = []
            for offer in ch.get("優惠", []):
                identity = (key, json.dumps(offer, sort_keys=True, ensure_ascii=False))
                if identity not in seen:
                    seen.add(identity)
                    offers.append(offer)
            if not offers:
                continue
            if key in groups:
                groups[key]["優惠"].extend(offers)
            else:
                ch["優惠"] = offers
                groups[key] = ch
                channels.append(ch)
    # App 的通路卡片與捷徑都依資料首次出現順序建立；其他通路維持原順序。
    channels.sort(key=lambda ch: {"星巴克": 1, "85度C": 2}.get(ch["名稱"], 0))
    return {"updated_at": datetime.now(TAIPEI).strftime("%Y-%m-%d %H:%M"),
            "article": articles[0]["article"], "articles": articles,
            "活動期間": "", "通路": channels}


def build(previous: dict | None = None) -> dict | None:
    """追加未收錄來源；每輪最多抽四篇，失敗來源下輪重試，舊資料保留。"""
    candidates = find_articles()
    if not candidates:
        _refresh_log("咖啡情報 -> 沒找到優惠文章，保留上一版；請檢查來源")
        if previous:
            print("咖啡情報：這輪沒找到新文章，沿用上一版")
        return previous
    articles = list((previous or {}).get("articles") or ([previous] if previous else []))
    articles = [a for a in articles if ARTICLE_RE.fullmatch(a.get("article", {}).get("url", ""))]
    known = {a["article"]["url"] for a in articles}
    added, attempts = 0, 0
    for latest in [a for a in candidates if a["url"] not in known]:
        if attempts >= 4:
            break
        print(f"咖啡情報：發現未收錄文章 {latest['title'][:40]}")
        try:
            document = article_document(latest["url"])
            if not document:
                _refresh_log(f"咖啡情報 -> 超出近45天或無有效發稿日期，略過（{latest['url']}）")
                continue
            attempts += 1
            data = extract(document["text"], latest["title"])
        except Exception as exc:                              # noqa: BLE001
            _refresh_log(f"咖啡情報 -> 讀取失敗（{latest['url']}；{type(exc).__name__}: {exc}），保留既有資料")
            continue
        if not data or not any(ch.get("優惠") for ch in data.get("通路", [])):
            _refresh_log(f"咖啡情報 -> 結構化擷取失敗（{latest['url']}），保留既有資料")
            continue
        articles.append({"article": {"title": latest["title"], "url": latest["url"],
                    "published": document["published"],
                    "source": "NOWnews 今日新聞"},
                         "活動期間": data.get("活動期間", ""), "通路": data["通路"]})
        added += 1
        _refresh_log(f"咖啡情報 -> 追加成功（{latest['url']}；{latest['title']}）")
    return merge_articles(articles) if added else previous


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
        for item in _from_rss() + _from_category() + _from_tags():
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
