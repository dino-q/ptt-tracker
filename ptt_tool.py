#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PTT Assistant
- Natural-language PTT search
- Author/[創作] export to TXT
- Lifeismoney weekend convenience-store coffee/drink deal tracker

Usage:
    python ptt_tool.py "幫我上PTT的marvel版找abc123這個作者，並且把他的創作做成txt檔"
    python ptt_tool.py "幫我找這週五六日超商咖啡或飲料優惠"
"""

from __future__ import annotations

import argparse
import html
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup


BASE = "https://www.ptt.cc"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36 "
    "PTT-Assistant/1.0"
)

BOARD_ALIASES = {
    "媽佛版": "marvel",
    "媽佛板": "marvel",
    "省錢版": "Lifeismoney",
    "省錢板": "Lifeismoney",
    "lifeismoney": "Lifeismoney",
}

CONVENIENCE_KEYWORDS = [
    "超商", "便利商店", "全家", "7-11", "7-ELEVEN", "統一超商",
    "萊爾富", "OK", "OKmart", "康康五", "超值五六日",
]
DRINK_KEYWORDS = [
    "咖啡", "飲料", "茶", "拿鐵", "美式", "買一送一", "第二杯",
    "寄杯", "冰品", "FMC", "Let's Café", "CITY CAFE", "CITY PRIMA",
]


@dataclass
class SearchItem:
    title: str
    author: str
    date_text: str
    url: str
    push: str = ""  # 板面列表的推文數欄位：爆 / 99 / 數字 / X1（噓）


@dataclass
class Article:
    title: str
    author: str
    board: str
    date_text: str
    url: str
    body: str


class PTTClient:
    def __init__(self, delay: float = 0.8, timeout: int = 20):
        self.delay = delay
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        # PTT adult-check cookie; harmless on boards that do not require it.
        self.session.cookies.set("over18", "1", domain=".ptt.cc")

    def _get(self, url: str) -> requests.Response:
        last_exc = None
        for attempt in range(3):
            try:
                r = self.session.get(url, timeout=self.timeout)
                if r.status_code == 200:
                    time.sleep(self.delay)
                    return r
                if r.status_code in (429, 502, 503, 504):
                    time.sleep(1.5 * (attempt + 1))
                    continue
                r.raise_for_status()
            except requests.RequestException as exc:
                last_exc = exc
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"讀取 PTT 失敗：{url}\n{last_exc or 'HTTP error'}")

    def search(self, board: str, query: str, max_pages: int = 8, max_posts: int = 200) -> list[SearchItem]:
        url = f"{BASE}/bbs/{board}/search?q={quote(query)}"
        results: list[SearchItem] = []
        seen = set()

        for _ in range(max_pages):
            r = self._get(url)
            soup = BeautifulSoup(r.text, "html.parser")

            for row in soup.select(".r-ent"):
                a = row.select_one(".title a")
                if not a:
                    continue
                href = a.get("href", "")
                full_url = urljoin(BASE, href)
                if full_url in seen:
                    continue
                seen.add(full_url)
                title = " ".join(a.get_text(" ", strip=True).split())
                author_el = row.select_one(".author")
                date_el = row.select_one(".date")
                push_el = row.select_one(".nrec")
                results.append(
                    SearchItem(
                        title=title,
                        author=author_el.get_text(strip=True) if author_el else "",
                        date_text=date_el.get_text(strip=True) if date_el else "",
                        url=full_url,
                        push=push_el.get_text(strip=True) if push_el else "",
                    )
                )
                if len(results) >= max_posts:
                    return results

            prev = None
            for a in soup.select(".btn-group-paging a.btn"):
                if "上頁" in a.get_text():
                    prev = a.get("href")
                    break
            if not prev:
                break
            url = urljoin(BASE, prev)

        return results

    def latest_board_posts(self, board: str, pages: int = 4, max_posts: int = 150) -> list[SearchItem]:
        url = f"{BASE}/bbs/{board}/index.html"
        results: list[SearchItem] = []
        seen = set()

        for _ in range(pages):
            r = self._get(url)
            soup = BeautifulSoup(r.text, "html.parser")

            for row in soup.select(".r-ent"):
                a = row.select_one(".title a")
                if not a:
                    continue
                full_url = urljoin(BASE, a.get("href", ""))
                if full_url in seen:
                    continue
                seen.add(full_url)
                author_el = row.select_one(".author")
                date_el = row.select_one(".date")
                push_el = row.select_one(".nrec")
                results.append(
                    SearchItem(
                        title=" ".join(a.get_text(" ", strip=True).split()),
                        author=author_el.get_text(strip=True) if author_el else "",
                        date_text=date_el.get_text(strip=True) if date_el else "",
                        url=full_url,
                        push=push_el.get_text(strip=True) if push_el else "",
                    )
                )
                if len(results) >= max_posts:
                    return results

            prev = None
            for a in soup.select(".btn-group-paging a.btn"):
                if "上頁" in a.get_text():
                    prev = a.get("href")
                    break
            if not prev:
                break
            url = urljoin(BASE, prev)

        return results

    def hotboards(self, top: int = 20) -> list[dict]:
        """抓 PTT 即時熱門看板排行（/bbs/hotboards.html），回 [{board, nuser, category, title}]。"""
        r = self._get(f"{BASE}/bbs/hotboards.html")
        soup = BeautifulSoup(r.text, "html.parser")
        boards: list[dict] = []
        for ent in soup.select(".b-ent"):
            name_el = ent.select_one(".board-name")
            if not name_el:
                continue
            nuser_el = ent.select_one(".board-nuser")
            nuser_text = nuser_el.get_text(strip=True) if nuser_el else "0"
            try:
                nuser = int(re.sub(r"\D", "", nuser_text) or 0)
            except ValueError:
                nuser = 0
            cat_el = ent.select_one(".board-class")
            title_el = ent.select_one(".board-title")
            boards.append({
                "board": name_el.get_text(strip=True),
                "nuser": nuser,
                "category": cat_el.get_text(strip=True) if cat_el else "",
                "title": title_el.get_text(strip=True) if title_el else "",
            })
            if len(boards) >= top:
                break
        return boards

    def article(self, url: str, include_comments: bool = False) -> Article:
        r = self._get(url)
        soup = BeautifulSoup(r.text, "html.parser")
        main = soup.select_one("#main-content")
        if not main:
            raise RuntimeError(f"找不到文章正文：{url}")

        meta = {}
        for line in main.select(".article-metaline"):
            tag = line.select_one(".article-meta-tag")
            val = line.select_one(".article-meta-value")
            if tag and val:
                meta[tag.get_text(strip=True)] = val.get_text(" ", strip=True)

        # 留言（推文）要在 decompose 前先收
        comments: list[str] = []
        if include_comments:
            for p in main.select(".push"):
                tag_el = p.select_one(".push-tag")
                uid_el = p.select_one(".push-userid")
                content_el = p.select_one(".push-content")
                dt_el = p.select_one(".push-ipdatetime")
                line = " ".join(filter(None, [
                    tag_el.get_text(strip=True) if tag_el else "",
                    (uid_el.get_text(strip=True) if uid_el else "")
                    + (content_el.get_text(" ", strip=True) if content_el else ""),
                    dt_el.get_text(strip=True) if dt_el else "",
                ])).strip()
                if line:
                    comments.append(line)

        for selector in [
            ".article-metaline",
            ".article-metaline-right",
            ".push",
            ".f2",
            ".richcontent",
        ]:
            for node in main.select(selector):
                node.decompose()

        text = main.get_text("\n")
        text = html.unescape(text)
        text = clean_ptt_body(text)
        if comments:
            text += "\n\n" + "─" * 30 + " 留言 " + "─" * 30 + "\n" + "\n".join(comments)

        return Article(
            title=meta.get("標題", ""),
            author=meta.get("作者", ""),
            board=meta.get("看板", ""),
            date_text=meta.get("時間", ""),
            url=url,
            body=text,
        )


def clean_ptt_body(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Remove standard footer if it survives DOM cleanup.
    text = re.split(r"\n※\s*發信站:", text, maxsplit=1)[0]
    text = re.split(r"\n※\s*文章網址:", text, maxsplit=1)[0]

    # Trim common signature delimiter only when it occurs near the end.
    lines = text.splitlines()
    sig_indices = [i for i, line in enumerate(lines) if line.strip() == "--"]
    if sig_indices:
        idx = sig_indices[-1]
        if idx > len(lines) * 0.55:
            lines = lines[:idx]

    # Normalize whitespace, but preserve paragraph breaks.
    out = []
    blank = False
    for line in lines:
        line = line.rstrip()
        if not line.strip():
            if not blank:
                out.append("")
            blank = True
        else:
            out.append(line)
            blank = False

    return "\n".join(out).strip()


def parse_board(text: str) -> str:
    lower = text.lower()
    for alias, board in BOARD_ALIASES.items():
        if alias.lower() in lower:
            return board

    m = re.search(r"PTT(?:的|上)?\s*([A-Za-z0-9_]+)(?:版|板)", text, re.I)
    if m:
        return m.group(1)
    return "Lifeismoney"


def parse_author(text: str) -> Optional[str]:
    # "找 abc123 這個作者", "作者 abc123"
    patterns = [
        r"找\s*([A-Za-z0-9_-]{2,})\s*這個作者",
        r"作者(?:是|為|:|：)?\s*([A-Za-z0-9_-]{2,})",
        r"author\s*[:：]?\s*([A-Za-z0-9_-]{2,})",
    ]
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            return m.group(1)
    return None


def safe_filename(s: str) -> str:
    s = re.sub(r'[\\/:*?"<>|]+', "_", s)
    return re.sub(r"\s+", " ", s).strip()[:100] or "ptt_export"


def title_sort_key(title: str):
    # Prefer final (N) / -NN / _NN / 第N... patterns.
    base = strip_ptt_category(re.sub(r"^\s*(?:Re|Fw)\s*:\s*", "", title, flags=re.I))
    nums = re.findall(r"(?:\(|（|-|－|_|\s|第)(\d{1,4})(?:\)|）|$|\D)", base)
    if not nums:
        # 無分隔符直接黏在字尾的集數（例：未央光年43）
        m = re.search(r"(\d{1,4})\s*[\)）]?\s*$", base)
        if m:
            nums = [m.group(1)]
    # 沒有集數視為第 0 集（系列首篇常不編號）
    n = int(nums[-1]) if nums else 0
    # 去掉尾端集數標記與空白後當系列名，讓「未央光年 (43)」與「未央光年(1)」歸同一系列
    series = re.sub(r"[\s\-－_]*[\(（]?\d{1,4}[\)）]?\s*$", "", base).replace(" ", "").strip()
    return (series, n, base)


def strip_ptt_category(title: str) -> str:
    return re.sub(r"^\s*\[[^\]]+\]\s*", "", title).strip()


def export_author_creations(
    client: PTTClient,
    board: str,
    author: str,
    out_dir: Path,
    max_pages: int = 20,
    tag: str = "[創作]",
    on_progress=None,
    collect: list | None = None,
) -> Path:
    """作者文章合併匯出 TXT。tag 為標題篩選字串（空字串＝不篩）；
    on_progress(msg) 供網頁回報進度（預設印到 console）；collect 若給 list 會收集 SearchItem。"""

    def report(msg: str) -> None:
        if on_progress:
            on_progress(msg)
        else:
            print(msg)

    items = client.search(board, f"author:{author}", max_pages=max_pages, max_posts=500)
    creations = [x for x in items if not tag or tag in x.title]

    if not creations:
        label = f"標題含 {tag} 的" if tag else ""
        raise RuntimeError(f"找不到 {board} 板作者 {author} 的{label}文章。")

    creations.sort(key=lambda x: title_sort_key(x.title))
    if collect is not None:
        collect.extend(creations)
    out_dir.mkdir(parents=True, exist_ok=True)
    tag_label = safe_filename(tag.strip("[]")) if tag else "全部文章"  # 維持 v1 的 xxx_創作.txt 命名
    out_file = out_dir / f"{safe_filename(author)}_{safe_filename(board)}_{tag_label}.txt"

    chunks = [
        f"PTT {board} 板｜作者 {author}｜{tag or '全部文章'} 合併匯出",
        f"匯出時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"共 {len(creations)} 篇",
        "=" * 72,
        "",
    ]

    for idx, item in enumerate(creations, 1):
        report(f"[{idx}/{len(creations)}] 讀取：{item.title}")
        try:
            article = client.article(item.url)
            body = article.body
        except Exception as exc:
            body = f"[讀取失敗：{exc}]"

        chunks.extend(
            [
                "",
                "#" * 72,
                item.title,
                f"作者：{item.author or author}",
                f"網址：{item.url}",
                "#" * 72,
                "",
                body,
                "",
            ]
        )

    out_file.write_text("\n".join(chunks), encoding="utf-8-sig")
    return out_file


def this_weekend_window(now: datetime) -> tuple[datetime, datetime]:
    # Mon=0 ... Fri=4
    days_to_friday = (4 - now.weekday()) % 7
    friday = (now + timedelta(days=days_to_friday)).replace(hour=0, minute=0, second=0, microsecond=0)
    sunday = friday + timedelta(days=2, hours=23, minutes=59, seconds=59)
    return friday, sunday


def looks_like_weekend_deal(title: str, body: str = "") -> bool:
    text = f"{title}\n{body}".lower()
    has_store = any(k.lower() in text for k in CONVENIENCE_KEYWORDS)
    has_drink = any(k.lower() in text for k in DRINK_KEYWORDS)
    return has_store and has_drink


def find_weekend_deals(client: PTTClient, out_dir: Path, pages: int = 6) -> Path:
    # Searching several focused terms is more reliable than a single broad PTT query.
    queries = [
        "咖啡", "飲料", "全家", "7-11", "統一超商",
        "萊爾富", "康康五", "超值五六日",
    ]
    dedup: dict[str, SearchItem] = {}

    for q in queries:
        print(f"搜尋 Lifeismoney：{q}")
        for item in client.search("Lifeismoney", q, max_pages=pages, max_posts=100):
            dedup[item.url] = item

    # Also scan latest pages for posts whose titles use unexpected wording.
    for item in client.latest_board_posts("Lifeismoney", pages=pages):
        dedup[item.url] = item

    candidates = sorted(dedup.values(), key=lambda x: x.url, reverse=True)
    hits = []

    # Cap full article reads to keep PTT load polite.
    for item in candidates[:120]:
        if not (
            any(k.lower() in item.title.lower() for k in CONVENIENCE_KEYWORDS)
            or any(k.lower() in item.title.lower() for k in DRINK_KEYWORDS)
        ):
            continue
        try:
            art = client.article(item.url)
        except Exception:
            continue
        if looks_like_weekend_deal(item.title, art.body):
            hits.append((item, art))

    friday, sunday = this_weekend_window(datetime.now())
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"Lifeismoney_週末咖啡飲料優惠_{friday:%Y%m%d}-{sunday:%Y%m%d}.txt"

    chunks = [
        "PTT Lifeismoney｜週五六日超商咖啡／飲料優惠候選",
        f"目標週末：{friday:%Y-%m-%d} ～ {sunday:%Y-%m-%d}",
        f"整理時間：{datetime.now():%Y-%m-%d %H:%M:%S}",
        "",
        "注意：PTT 貼文可能提早數天公告，且優惠期限、會員資格、門市限制可能變動；",
        "請以貼文內官方活動來源與門市現場規則為準。",
        "=" * 72,
        "",
    ]

    for item, art in hits:
        preview = re.sub(r"\n{3,}", "\n\n", art.body).strip()
        if len(preview) > 1800:
            preview = preview[:1800].rstrip() + "\n……（內容已截短，請開原文確認）"

        chunks.extend(
            [
                f"【{item.title}】",
                f"作者：{item.author}",
                f"網址：{item.url}",
                "",
                preview,
                "",
                "-" * 72,
                "",
            ]
        )

    if not hits:
        chunks.append("目前沒有抓到符合關鍵字的候選優惠。")

    out_file.write_text("\n".join(chunks), encoding="utf-8-sig")
    return out_file


def search_and_export_index(
    client: PTTClient, board: str, query: str, out_dir: Path
) -> Path:
    items = client.search(board, query, max_pages=10, max_posts=300)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{safe_filename(board)}_{safe_filename(query)}_搜尋結果.txt"

    lines = [f"PTT {board}｜搜尋：{query}", f"共 {len(items)} 筆", "=" * 72, ""]
    for x in items:
        lines.extend([x.title, f"作者：{x.author}｜日期：{x.date_text}", x.url, ""])
    out_file.write_text("\n".join(lines), encoding="utf-8-sig")
    return out_file


def run_natural_language(text: str, out_dir: Path, delay: float = 0.8) -> Path:
    client = PTTClient(delay=delay)
    board = parse_board(text)
    author = parse_author(text)

    lower = text.lower()

    if author and any(k in text for k in ["小說", "創作", "txt", "TXT", "匯出", "下載"]):
        return export_author_creations(client, board, author, out_dir)

    if board == "Lifeismoney" or "省錢" in text:
        if any(k in text for k in ["咖啡", "飲料", "超商", "五六日", "週末", "周末"]):
            return find_weekend_deals(client, out_dir)

    if any(k in text for k in ["咖啡", "飲料", "超商"]) and any(k in text for k in ["週末", "周末", "五六日"]):
        return find_weekend_deals(client, out_dir)

    # Generic fallback: search the quoted content / last meaningful phrase.
    q = text.strip()
    q = re.sub(r"幫我|請|上PTT|PTT|找|搜尋|查一下", " ", q, flags=re.I)
    q = re.sub(r"\s+", " ", q).strip()
    if not q:
        raise RuntimeError("無法判斷搜尋關鍵字。")
    return search_and_export_index(client, board, q, out_dir)


def main():
    parser = argparse.ArgumentParser(description="一句話搜尋／整理 PTT")
    parser.add_argument("request", nargs="*", help="自然語言要求")
    parser.add_argument("--out", default="output", help="輸出資料夾，預設 output")
    parser.add_argument("--delay", type=float, default=0.8, help="每次請求後等待秒數，預設 0.8")
    parser.add_argument("--board", help="直接指定板名")
    parser.add_argument("--author", help="直接指定作者")
    parser.add_argument("--query", help="直接指定搜尋字串")
    parser.add_argument("--weekend-deals", action="store_true", help="整理省錢板週末超商咖啡/飲料優惠")
    args = parser.parse_args()

    out_dir = Path(args.out)

    try:
        if args.weekend_deals:
            path = find_weekend_deals(PTTClient(args.delay), out_dir)
        elif args.board and args.author:
            path = export_author_creations(PTTClient(args.delay), args.board, args.author, out_dir)
        elif args.board and args.query:
            path = search_and_export_index(PTTClient(args.delay), args.board, args.query, out_dir)
        else:
            request = " ".join(args.request).strip()
            if not request:
                print("請輸入一句話要求，例如：")
                print('  python ptt_tool.py "幫我上PTT的marvel版找abc123這個作者，並且把他的創作做成txt檔"')
                print('  python ptt_tool.py "幫我找這週五六日超商咖啡或飲料優惠"')
                sys.exit(2)
            path = run_natural_language(request, out_dir, args.delay)

        print(f"\n完成：{path.resolve()}")
    except KeyboardInterrupt:
        print("\n已中止。")
        sys.exit(130)
    except Exception as exc:
        print(f"\n錯誤：{exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
