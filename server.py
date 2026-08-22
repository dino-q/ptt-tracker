#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PTT Assistant 本機網頁伺服器（通用掃描引擎）

- 白話輸入 → 解析成結構化掃描條件（板名/關鍵字/天數），UI 可修正後執行
- 通用 task 引擎：任何看板 + 任意關鍵字組 + 日期過濾，追蹤項存 tracks.json
- 背景 job + 進度輪詢 + 取消

啟動：
    .venv\\Scripts\\python.exe server.py            # 預設 http://127.0.0.1:8877
    .venv\\Scripts\\python.exe server.py --port 8878
"""

from __future__ import annotations

import argparse
import json
import os
import re
import threading
import time
import uuid
import webbrowser
from datetime import datetime, timedelta, timezone

# PTT 顯示的都是台灣時間；伺服器可能跑在 UTC（GitHub Actions），
# 所有跟文章時間比較的「現在」一律用台灣時間，否則文章年齡會算錯。
try:
    from zoneinfo import ZoneInfo
    TAIPEI = ZoneInfo("Asia/Taipei")
except Exception:  # Windows 無 tzdata 時退固定 UTC+8（台灣無夏令時間）
    TAIPEI = timezone(timedelta(hours=8))


def now_tw() -> datetime:
    return datetime.now(TAIPEI).replace(tzinfo=None)
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

# ♻️ 沿用 ptt_tool.py 的爬蟲核心與關鍵字常數
from ptt_tool import (
    BOARD_ALIASES,
    CONVENIENCE_KEYWORDS,
    DRINK_KEYWORDS,
    PTTClient,
    export_author_creations,
    parse_author,
    safe_filename,
    this_weekend_window,
)

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
OUTPUT_DIR = ROOT / "output"
TRACKS_FILE = ROOT / "tracks.json"
CONFIG_FILE = ROOT / "config.json"
CONFIG_EXAMPLE = ROOT / "config.example.json"

DEFAULT_PORT = 8877

# ---------------------------------------------------------------- config / tracks


def load_config() -> dict:
    for p in (CONFIG_FILE, CONFIG_EXAMPLE):
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {}


CONFIG = load_config()


def _fix_ambiguous(words: list[str]) -> list[str]:
    """把單獨的品牌詞 OK 換成明確寫法，避免命中內文裡口語的「ok」。"""
    out: list[str] = []
    for w in words:
        if str(w).strip().lower() == "ok":
            out.extend(["OK超商", "OKmart", "OK咖啡"])
        else:
            out.append(w)
    return list(dict.fromkeys(out))


STORE_WORDS = _fix_ambiguous(
    CONFIG.get("weekend_deal_keywords", {}).get("stores") or CONVENIENCE_KEYWORDS
)
DRINK_WORDS = CONFIG.get("weekend_deal_keywords", {}).get("drinks") or DRINK_KEYWORDS

# 板名別名：ptt_tool 內建 + config 的 boards 區塊
ALIAS_TO_BOARD: dict[str, str] = dict(BOARD_ALIASES)
for board, aliases in (CONFIG.get("boards") or {}).items():
    for a in aliases:
        ALIAS_TO_BOARD[a.lower()] = board
# 常用中文板名補充
ALIAS_TO_BOARD.update({
    "省錢": "Lifeismoney",
    "八卦版": "Gossiping", "八卦板": "Gossiping",
    "股版": "Stock", "股板": "Stock", "股票版": "Stock",
    "特價版": "BuyTogether",
    "電影版": "movie", "電影板": "movie",
    "美食版": "Food", "美食板": "Food",
    "笨版": "StupidClown", "笨板": "StupidClown",
    "nba版": "NBA", "棒球版": "Baseball",
    "西斯版": "sex", "表特版": "Beauty",
    "工作版": "Salary", "薪水版": "Salary",
    "信用卡版": "creditcard",
    "3c版": "PC_Shopping", "電蝦": "PC_Shopping",
})


# 結果分類（省錢版瀏覽用）：一篇文可同時屬多類，全都沒中＝「其他」。
# 可在 config.json 以 "categories": {"分類名": ["詞", ...]} 覆蓋。
DEFAULT_CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("四大超商", [
        "7-11", "711", "小七", "統一超商", "全家", "FamilyMart", "萊爾富", "Hi-Life",
        "OK超商", "OKmart", "OK咖啡", "超商", "便利商店", "CITY CAFE", "Let's Café", "康康五",
    ]),
    ("超市量販", [
        "全聯", "家樂福", "Carrefour", "大潤發", "愛買", "美廉社", "好市多", "Costco",
        "楓康", "超市", "量販", "全聯小時達",
    ]),
    ("網購電商", [
        "蝦皮", "shopee", "momo", "PChome", "Yahoo", "酷澎", "Coupang", "淘寶", "天貓",
        "樂天", "東森購物", "生活市集", "松果", "Amazon", "亞馬遜", "折扣碼", "網購", "電商",
    ]),
    ("餐飲美食", [
        "麥當勞", "肯德基", "KFC", "摩斯", "漢堡王", "必勝客", "達美樂", "拿坡里", "頂呱呱",
        "星巴克", "路易莎", "85度C", "cama", "可不可", "五十嵐", "清心", "手搖", "速食",
        "SUBWAY", "爭鮮", "壽司郎", "藏壽司", "八方雲集", "三商巧福", "鬍鬚張",
    ]),
    ("支付回饋", [
        "LINE Pay", "LINEPay", "街口", "全支付", "全盈", "悠遊付", "icash", "Pi拍錢包",
        "OPEN錢包", "信用卡", "刷卡", "回饋", "點數",
    ]),
]


def load_category_rules() -> list[tuple[str, list[str]]]:
    custom = CONFIG.get("categories")
    if isinstance(custom, dict) and custom:
        return [(name, list(words)) for name, words in custom.items() if words]
    return DEFAULT_CATEGORY_RULES


CATEGORY_RULES = load_category_rules()
CATEGORY_NAMES = [name for name, _ in CATEGORY_RULES]


def default_tracks() -> list[dict]:
    return [
        {
            "id": "weekend-coffee",
            "name": "省錢版｜週五六日超商咖啡/飲料優惠",
            "task": {
                "intent": "scan",
                "board": "Lifeismoney",
                "queries": ["咖啡", "飲料", "全家", "7-11", "萊爾富", "康康五", "超值五六日"],
                "scan_latest_pages": 4,
                "search_pages": 3,
                "must_groups": [list(STORE_WORDS), list(DRINK_WORDS)],
                "exclude": [],
                "days": 10,
                "read_body": True,
                "max_body_reads": 30,
                "weekend": True,
            },
        },
        {
            "id": "lifeismoney-browse",
            "name": "省錢版｜最新優惠總覽（分類瀏覽）",
            "auto": True,
            "task": {
                "intent": "scan",
                "board": "Lifeismoney",
                "queries": [],
                "scan_latest_pages": 6,
                "search_pages": 3,
                "must_groups": [],
                "exclude": [],
                "days": 3,
                "read_body": False,
                "max_body_reads": 0,
            },
        },
        {
            "id": "hot-now",
            "name": "PTT｜當前全站熱門討論",
            "auto": True,
            "task": {
                "intent": "hot",
                "board": "",
                "hot_boards": 10,
                "min_push": 30,
                "search_pages": 2,
                "max_detail": 40,
                "days": 2,
            },
        },
    ]


_tracks_lock = threading.Lock()


def _write_tracks_atomic(tracks: list[dict]) -> None:
    # 先寫暫存檔再 replace，避免寫到一半當機留下半截 JSON
    tmp = TRACKS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(tracks, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(TRACKS_FILE)


def load_tracks() -> list[dict]:
    with _tracks_lock:
        if not TRACKS_FILE.exists():
            tracks = default_tracks()
            _write_tracks_atomic(tracks)
            return tracks
        try:
            return json.loads(TRACKS_FILE.read_text(encoding="utf-8"))
        except Exception:
            # 檔案壞掉：備份原檔再回預設，不讓下一次 save 無聲蓋掉使用者資料
            try:
                TRACKS_FILE.replace(TRACKS_FILE.with_suffix(".json.bak"))
                print(f"警告：tracks.json 無法解析，已備份為 tracks.json.bak 並改用預設追蹤項。")
            except Exception:
                pass
            return default_tracks()


def save_tracks(tracks: list[dict]) -> None:
    with _tracks_lock:
        _write_tracks_atomic(tracks)


# ---------------------------------------------------------------- 白話解析

FILLER_WORDS = [
    "幫我", "請問", "請", "我想要", "我想", "我要", "希望可以", "希望", "可以",
    "追蹤", "看看", "查一下", "查詢", "查", "搜尋", "搜", "找找", "找",
    "上ptt", "去ptt", "ptt上", "ptt的", "ptt", "有什麼", "有哪些", "有沒有",
    "顯示", "整理", "列出", "告訴我", "看一下", "相關", "的文章", "文章",
    "資訊", "消息", "內容",
]

WEEKEND_HINTS = ["五六日", "週末", "周末", "週五六日", "假日"]
STORE_HINTS = ["超商", "便利商店", "全家", "7-11", "711", "小七", "萊爾富", "ok"]
DRINK_HINTS = ["咖啡", "飲料", "拿鐵", "美式", "茶", "冰品"]


def detect_board(text: str) -> tuple[str | None, str | None]:
    """回 (board, 命中的別名)。別名長的優先，避免『省錢版』被『省錢』搶走。"""
    lower = text.lower()
    for alias in sorted(ALIAS_TO_BOARD, key=len, reverse=True):
        if alias.lower() in lower:
            return ALIAS_TO_BOARD[alias], alias
    m = re.search(r"([A-Za-z0-9_]{2,})\s*[版板]", text)
    if m:
        return m.group(1), m.group(0)
    return None, None


def parse_days(text: str) -> tuple[int, str | None]:
    m = re.search(r"最近\s*(\d{1,3})\s*天", text)
    if m:
        return int(m.group(1)), m.group(0)
    if "今天" in text:
        return 2, "今天"
    for w in ("這週", "本週", "这周", "本周", "這周"):
        if w in text:
            return 7, w
    if "本月" in text or "這個月" in text:
        return 31, "本月"
    return 10, None


def parse_request(text: str) -> dict:
    """白話 → 結構化 task 提案。UI 會把結果攤開讓使用者修正，解析不必完美。"""
    raw = text.strip()
    board, board_alias = detect_board(raw)
    days, days_hit = parse_days(raw)
    lower = raw.lower()

    is_weekend = any(w in raw for w in WEEKEND_HINTS)
    wants_store = any(w in lower for w in STORE_HINTS)
    wants_drink = any(w in lower for w in DRINK_HINTS)

    # 情境零之一：作者文章匯出（♻️ 沿用 ptt_tool.parse_author 的規則）
    author = parse_author(raw)
    if author and any(k in raw for k in ["小說", "創作", "txt", "TXT", "匯出", "下載", "做成"]):
        return {
            "task": {
                "intent": "author_export",
                "board": board or "",
                "author": author,
                "tag": "[創作]" if any(k in raw for k in ["小說", "創作"]) else "",
                "max_pages": 20,
            },
            "summary": f"匯出作者 {author} 的文章成 TXT",
        }

    # 情境零之二：熱門討論（有板名＝該板熱門文；沒板名＝全站熱門看板掃描）
    if any(w in raw for w in ["熱門", "爆文", "在討論什麼", "在聊什麼", "大家在討論", "大家在聊"]):
        return {
            "task": {
                "intent": "hot",
                "board": board or "",
                "hot_boards": 10,
                "min_push": 30,
                "search_pages": 2 if not board else 3,
                "max_detail": 40,
                "days": min(days, 2) if not days_hit else days,
            },
            "summary": "熱門討論掃描（衝火速度排序，爆=100）",
        }

    # 情境一：超商 × 咖啡/飲料優惠（雙關鍵字組判定）
    if wants_store and wants_drink:
        task = default_tracks()[0]["task"].copy()
        task["board"] = board or "Lifeismoney"
        task["days"] = days
        task["weekend"] = is_weekend
        return {"task": task, "summary": "超商 × 咖啡/飲料 雙關鍵字組掃描"}

    # 情境二：一般關鍵字掃描
    cleaned = raw
    if board_alias:
        cleaned = cleaned.replace(board_alias, " ")
    if days_hit:
        cleaned = cleaned.replace(days_hit, " ")
    for w in WEEKEND_HINTS:
        cleaned = cleaned.replace(w, " ")
    for w in sorted(FILLER_WORDS, key=len, reverse=True):
        cleaned = re.sub(re.escape(w), " ", cleaned, flags=re.I)
    parts = re.split(r"[或、,，/\s]+", cleaned)
    keywords = []
    for p in parts:
        p = p.strip(" 的了嗎呢？?！!。.")
        if len(p) >= 2 and p not in keywords:
            keywords.append(p)
    keywords = keywords[:6]

    task = {
        "board": board or "Lifeismoney",
        "queries": keywords,
        "scan_latest_pages": 3 if keywords else 5,
        "search_pages": 3,
        "must_groups": [keywords] if keywords else [],
        "exclude": [],
        "days": days,
        "read_body": True,
        "max_body_reads": 20,
        "weekend": is_weekend,
    }
    return {"task": task, "summary": "一般關鍵字掃描"}


# ---------------------------------------------------------------- 掃描引擎


def parse_list_date(date_text: str, today: datetime) -> datetime | None:
    """板面列表的 M/DD 推回完整日期；比今天晚就視為去年。"""
    m = re.match(r"\s*(\d{1,2})/\s*(\d{1,2})", date_text or "")
    if not m:
        return None
    month, day = int(m.group(1)), int(m.group(2))
    try:
        dt = datetime(today.year, month, day)
    except ValueError:
        return None
    if dt > today + timedelta(days=1):
        try:
            dt = dt.replace(year=today.year - 1)
        except ValueError:
            return None
    return dt


def _word_hit(text_lower: str, word: str) -> bool:
    """短英數詞（如 OK、茶類縮寫）用字詞邊界比對，避免命中內文裡隨口的 ok。"""
    wl = word.lower()
    if re.fullmatch(r"[a-z0-9]{1,3}", wl):
        return re.search(rf"(?<![a-z0-9]){re.escape(wl)}(?![a-z0-9])", text_lower) is not None
    return wl in text_lower


def match_groups(text: str, groups: list[list[str]]) -> tuple[bool, list[str]]:
    """每一組至少命中一詞才算通過；回 (是否通過, 全部命中詞)。"""
    lower = text.lower()
    matched: list[str] = []
    ok = True
    for group in groups:
        hits = [w for w in group if w and _word_hit(lower, w)]
        if hits:
            matched.extend(hits)
        else:
            ok = False
    return ok, list(dict.fromkeys(matched))


def hits_any(text: str, groups: list[list[str]]) -> bool:
    lower = text.lower()
    return any(_word_hit(lower, w) for group in groups for w in group if w)


def classify(title: str) -> list[str]:
    """依 CATEGORY_RULES 幫標題貼分類標籤（可多類；全沒中＝空 list，UI 歸「其他」）。"""
    lower = title.lower()
    return [name for name, words in CATEGORY_RULES if any(_word_hit(lower, w) for w in words)]


def push_score(push: str) -> int:
    """板面推文數欄位轉分數：爆=100、X 開頭（噓）為負、空白=0。"""
    push = (push or "").strip()
    if not push:
        return 0
    if push == "爆":
        return 100
    if push.startswith(("X", "x")):
        digits = re.sub(r"\D", "", push)
        return -(int(digits) * 10 if digits else 100)
    try:
        return int(push)
    except ValueError:
        return 0


# 熱門文章的分類走「看板主題」，跟省錢優惠的通路標籤是兩套。
# 可在 config.json 以 "hot_board_categories": {"板名": "分類"} 覆蓋/擴充。
HOT_BOARD_CATEGORY: dict[str, str] = {
    "Gossiping": "八卦時事", "HatePolitics": "政黑", "Militarylife": "軍旅",
    "Stock": "股票理財", "home-sale": "房產", "creditcard": "信用卡", "Finance": "股票理財",
    "Baseball": "棒球", "Elephants": "棒球", "Lions": "棒球", "Monkeys": "棒球", "Dragons": "棒球",
    "basketballTW": "籃球", "NBA": "籃球", "SportLottery": "運彩", "FITNESS": "健身",
    "LoL": "遊戲電競", "Steam": "遊戲電競", "PlayStation": "遊戲電競", "NSwitch": "遊戲電競",
    "C_Chat": "動漫遊戲", "miHoYo": "遊戲電競", "TypeMoon": "動漫遊戲",
    "movie": "影視", "KoreaDrama": "影視", "TaiwanDrama": "影視", "China-Drama": "影視",
    "KR_ENTERTAIN": "影視", "KoreaStar": "影視", "Japandrama": "影視", "EAseries": "影視",
    "Lifeismoney": "省錢消費", "e-shopping": "省錢消費", "e-coupon": "省錢消費",
    "MobileComm": "3C", "PC_Shopping": "3C", "iOS": "3C", "Android": "3C",
    "Boy-Girl": "感情", "marriage": "感情", "WomenTalk": "閒聊", "Tech_Job": "工作職場",
    "Salary": "工作職場", "Soft_Job": "工作職場",
    "sex": "西斯", "Beauty": "表特", "joke": "笑話", "StupidClown": "笨版", "marvel": "媽佛",
    "car": "汽機車", "biker": "汽機車", "MakeUp": "美妝", "BabyMother": "親子",
    "Japan_Travel": "旅遊", "Food": "美食", "cookclub": "美食",
}
HOT_BOARD_CATEGORY.update({
    str(k): str(v) for k, v in (CONFIG.get("hot_board_categories") or {}).items()
})


def hot_cats(board: str) -> list[str]:
    """熱門文的分類＝看板主題；沒對照到的板直接用板名當分類。"""
    return [HOT_BOARD_CATEGORY.get(board, board)]


_MONTHS = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
           "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}


def _parse_article_dt(s: str) -> datetime | None:
    """文章頁的時間字串（例：Wed Aug 20 12:34:56 2026）。
    不用 strptime %a/%b：那依賴 LC_TIME，哪天有人 setlocale 就整批解析失敗。"""
    m = re.search(r"([A-Z][a-z]{2})\s+(\d{1,2})\s+(\d{1,2}):(\d{2}):(\d{2})\s+(\d{4})", s or "")
    if not m:
        return None
    mon = _MONTHS.get(m.group(1))
    if not mon:
        return None
    try:
        return datetime(int(m.group(6)), mon, int(m.group(2)),
                        int(m.group(3)), int(m.group(4)), int(m.group(5)))
    except ValueError:
        return None


def _thread_key(title: str) -> str:
    """Re:/Fw: 與 [分類] 去掉後的標題，當討論串聚合鍵。"""
    t = re.sub(r"^\s*(?:Re|Fw)\s*:\s*", "", title, flags=re.I)
    t = re.sub(r"^\s*\[[^\]]+\]\s*", "", t)
    return re.sub(r"\s+", "", t).lower()


JOBS: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def job_log(job: dict, msg: str) -> None:
    with _jobs_lock:
        job["log"].append(f"{now_tw():%H:%M:%S} {msg}")


def run_task(task: dict, job: dict) -> None:
    try:
        client = PTTClient(delay=float(task.get("delay", 0.4)))
        board = (task.get("board") or "Lifeismoney").strip()
        queries = [q for q in (task.get("queries") or []) if q.strip()]
        must_groups = [
            [w for w in g if str(w).strip()]
            for g in (task.get("must_groups") or [])
        ]
        must_groups = [g for g in must_groups if g]
        exclude = [w for w in (task.get("exclude") or []) if str(w).strip()]
        days = int(task.get("days") or 0)
        read_body = bool(task.get("read_body", True))
        max_body_reads = int(task.get("max_body_reads", 25))
        today = now_tw()

        seen: dict[str, object] = {}
        for q in queries:
            if job["cancel"]:
                raise InterruptedError
            job_log(job, f"搜尋 {board}：{q}")
            try:
                for it in client.search(
                    board, q,
                    max_pages=int(task.get("search_pages", 3)),
                    max_posts=120,
                ):
                    seen[it.url] = it
            except Exception as exc:
                job_log(job, f"搜尋「{q}」失敗：{exc}")

        latest_pages = int(task.get("scan_latest_pages", 0))
        if latest_pages > 0:
            if job["cancel"]:
                raise InterruptedError
            job_log(job, f"掃描 {board} 最新 {latest_pages} 頁列表")
            try:
                for it in client.latest_board_posts(board, pages=latest_pages, max_posts=150):
                    seen[it.url] = it
            except Exception as exc:
                job_log(job, f"掃描列表失敗：{exc}")

        if not seen:
            raise RuntimeError(f"在 {board} 板抓不到任何文章，請確認板名是否正確。")

        # 日期過濾 + 排除詞
        cands: list[tuple[object, datetime | None]] = []
        for it in seen.values():
            if exclude and any(w.lower() in it.title.lower() for w in exclude):
                continue
            dt = parse_list_date(it.date_text, today)
            if days and dt and (today - dt).days > days:
                continue
            cands.append((it, dt))
        cands.sort(key=lambda x: (x[1] is None, -(x[1].timestamp() if x[1] else 0)))
        job_log(job, f"候選 {len(cands)} 篇（去重＋{days} 天內），開始比對關鍵字")

        results: list[dict] = []
        body_reads = 0
        checked = 0
        for it, dt in cands:
            if job["cancel"]:
                raise InterruptedError
            checked += 1
            with _jobs_lock:
                job["progress"] = {"done": checked, "total": len(cands)}

            title = it.title
            preview = ""
            if must_groups:
                ok, matched = match_groups(title, must_groups)
                if not ok:
                    # 標題至少沾到一組才值得花時間讀內文
                    if not (read_body and body_reads < max_body_reads and hits_any(title, must_groups)):
                        continue
                    try:
                        art = client.article(it.url)
                        body_reads += 1
                    except Exception:
                        continue
                    ok, matched = match_groups(f"{title}\n{art.body}", must_groups)
                    if not ok:
                        continue
                    preview = art.body
                elif read_body and body_reads < max_body_reads:
                    try:
                        art = client.article(it.url)
                        body_reads += 1
                        preview = art.body
                    except Exception:
                        pass
            else:
                matched = []
                if read_body and body_reads < max_body_reads:
                    try:
                        art = client.article(it.url)
                        body_reads += 1
                        preview = art.body
                    except Exception:
                        pass

            preview = re.sub(r"\n{3,}", "\n\n", preview).strip()
            if len(preview) > 1500:
                preview = preview[:1500].rstrip() + "\n……（已截短，請開原文）"
            results.append({
                "title": title,
                "author": getattr(it, "author", ""),
                "date": f"{dt:%Y-%m-%d}" if dt else (it.date_text or "").strip(),
                "url": it.url,
                "matched": matched,
                "preview": preview,
                "push": getattr(it, "push", ""),
                "cats": classify(title),
            })

        note = ""
        if task.get("weekend"):
            fri, sun = this_weekend_window(today)
            note = f"目標週末：{fri:%Y-%m-%d}（五）～ {sun:%Y-%m-%d}（日）；貼文常提前公告，優惠以官方為準。"

        job_log(job, f"完成：{len(results)} 篇符合（讀取內文 {body_reads} 篇）")
        with _jobs_lock:
            job["results"] = results
            job["note"] = note
            job["status"] = "done"
    except InterruptedError:
        job_log(job, "已取消")
        with _jobs_lock:
            job["status"] = "cancelled"
    except Exception as exc:
        job_log(job, f"錯誤：{exc}")
        with _jobs_lock:
            job["status"] = "error"
            job["error"] = str(exc)


def run_author_export(task: dict, job: dict) -> None:
    """作者文章匯出 TXT（♻️ 調用 ptt_tool.export_author_creations，加進度回報與取消）。"""
    try:
        client = PTTClient(delay=float(task.get("delay", 0.4)))
        board = (task.get("board") or "").strip()
        author = (task.get("author") or "").strip()
        if not board or not author:
            raise RuntimeError("作者匯出需要板名與作者帳號。")
        tag = task.get("tag", "[創作]")

        def on_progress(msg: str) -> None:
            if job["cancel"]:
                raise InterruptedError
            job_log(job, msg)
            m = re.match(r"\[(\d+)/(\d+)\]", msg)
            if m:
                with _jobs_lock:
                    job["progress"] = {"done": int(m.group(1)), "total": int(m.group(2))}

        job_log(job, f"搜尋 {board} 板作者 {author} 的文章（篩選：{tag or '不篩'}）")
        collected: list = []
        path = export_author_creations(
            client, board, author, OUTPUT_DIR,
            max_pages=int(task.get("max_pages", 20)),
            tag=tag, on_progress=on_progress, collect=collected,
        )
        results = [{
            "title": it.title,
            "author": it.author or author,
            "date": (it.date_text or "").strip(),
            "url": it.url,
            "matched": [],
            "preview": "",
            "push": getattr(it, "push", ""),
            "cats": [],
        } for it in collected]
        note = f"已匯出 TXT（{len(collected)} 篇，依集數排序）：{path.resolve()}"
        job_log(job, f"完成：{note}")
        with _jobs_lock:
            job["results"] = results
            job["note"] = note
            job["file"] = path.name
            job["status"] = "done"
    except InterruptedError:
        job_log(job, "已取消")
        with _jobs_lock:
            job["status"] = "cancelled"
    except Exception as exc:
        job_log(job, f"錯誤：{exc}")
        with _jobs_lock:
            job["status"] = "error"
            job["error"] = str(exc)


def run_hot(task: dict, job: dict) -> None:
    """熱門討論 v2：
    - 候選用 PTT 原生 recommend: 搜尋（快板如八卦板的熱文會沉到深頁，掃最新頁抓不到）
    - Re:/Fw: 同主題聚合成討論串，取最高推那篇當代表
    - 前 max_detail 篇進文章頁統計總留言數，算「衝火速度」＝留言數/(小時+2)^1.6
    - 分類＝看板主題（hot_cats），與省錢優惠的通路標籤是兩套
    """
    try:
        client = PTTClient(delay=float(task.get("delay", 0.4)))
        board = (task.get("board") or "").strip()
        # H4：PTT 對 recommend:0 / 負值會直接忽略條件，server 端夾住下限並在收集時複驗
        min_push = max(1, int(task.get("min_push", 30)))
        days = int(task.get("days") or 0)
        max_detail = int(task.get("max_detail", 40))
        search_pages = max(1, int(task.get("search_pages", 2)))
        today = now_tw()

        if board:
            boards = [board]
            note = f"{board} 板熱門文章（推文數 ≥ {min_push}，爆=100）"
        else:
            job_log(job, "抓取 PTT 即時熱門看板排行")
            hot = client.hotboards(top=int(task.get("hot_boards", 10)))
            if not hot:
                raise RuntimeError("抓不到熱門看板排行。")
            boards = [b["board"] for b in hot]
            job_log(job, f"人氣前 {len(boards)} 板：{'、'.join(boards)}")
            note = f"全站人氣前 {len(boards)} 板，推文數 ≥ {min_push}"

        # 候選收集：recommend 搜尋
        candidates: list[dict] = []
        seen: set[str] = set()
        ok_boards = 0
        for i, b in enumerate(boards, 1):
            if job["cancel"]:
                raise InterruptedError
            with _jobs_lock:
                job["progress"] = {"done": i, "total": len(boards)}
            job_log(job, f"搜尋 {b} 推文數 ≥ {min_push} 的文章")
            try:
                items = client.search(b, f"recommend:{min_push}",
                                      max_pages=search_pages, max_posts=60)
                ok_boards += 1
            except Exception as exc:
                job_log(job, f"搜尋 {b} 失敗：{exc}")
                continue
            for it in items:
                if it.url in seen:
                    continue
                seen.add(it.url)
                if push_score(it.push) < min_push:  # 不信任 PTT 一定有套用 recommend 條件
                    continue
                dt = parse_list_date(it.date_text, today)
                if days and dt and (today - dt).days > days:
                    continue
                candidates.append({
                    "title": it.title,
                    "author": it.author,
                    "date": f"{dt:%Y-%m-%d}" if dt else (it.date_text or "").strip(),
                    "url": it.url,
                    "push": it.push,
                    "score": push_score(it.push),
                    "board": b,
                })

        if ok_boards == 0:
            raise RuntimeError("所有看板都掃描失敗，請確認網路或板名。")

        # 討論串聚合：同板同主題取最高推那篇當代表（key 帶板名，跨板同名文不誤併）
        threads: dict[str, list[dict]] = {}
        for c in candidates:
            threads.setdefault(f"{c['board']}|{_thread_key(c['title'])}", []).append(c)
        reps: list[dict] = []
        for group in threads.values():
            rep = max(group, key=lambda c: c["score"])
            rep["thread"] = len(group)
            reps.append(rep)
        reps.sort(key=lambda c: c["score"], reverse=True)
        detail = reps[:max_detail]
        job_log(job, f"候選 {len(candidates)} 篇／{len(reps)} 個討論串，讀取前 {len(detail)} 篇留言統計")

        results: list[dict] = []
        now = now_tw()
        fetch_fail = 0
        dt_fail = 0
        for i, c in enumerate(detail, 1):
            if job["cancel"]:
                raise InterruptedError
            with _jobs_lock:
                job["progress"] = {"done": i, "total": len(detail)}
            try:
                art = client.article(c["url"])
            except Exception as exc:
                # H2：讀取失敗仍保留該篇（無留言統計），不讓熱文無聲消失
                job_log(job, f"讀取失敗（保留無統計）：{c['title'][:30]}（{exc}）")
                fetch_fail += 1
                results.append({**c, "matched": [], "preview": "",
                                "cats": hot_cats(c["board"]), "rising": 0.0})
                continue
            ps = art.push_summary or {}
            comments = int(ps.get("total", 0))
            dt = _parse_article_dt(art.date_text)
            if dt is None:
                dt_fail += 1
            age_h = max((now - dt).total_seconds() / 3600.0, 0.1) if dt else None
            results.append({
                **c,
                "date": f"{dt:%m-%d %H:%M}" if dt else c["date"],
                "matched": [],
                "preview": "",
                "cats": hot_cats(c["board"]),
                "comments": comments,
                "users": ps.get("users", 0),
                "boo": ps.get("噓", 0),
                "per_hour": round(comments / age_h, 1) if age_h else None,
                "rising": round(comments / ((age_h + 2) ** 1.6), 2) if age_h else 0.0,
                # ts 只能拿來「排序」：naive 台灣時間取 timestamp，在 UTC 主機上
                # 不是真 epoch（偏 8 小時）。前端絕不可拿它跟 Date.now() 算相對時間。
                "ts": dt.timestamp() if dt else None,
            })

        # H3 哨兵：時間解析大量失敗時排序等於壞掉，要出聲不能靜默
        if results and dt_fail > len(results) / 2:
            job_log(job, f"警告：{dt_fail}/{len(results)} 篇文章時間解析失敗，衝火速度排序可能失效")
        results.sort(key=lambda r: r.get("rising") or 0, reverse=True)
        note += "；預設依衝火速度排序（留言數÷時間衰減），可切換總留言數"
        if fetch_fail:
            note += f"；{fetch_fail} 篇未取得留言統計"
        job_log(job, f"完成：{len(results)} 篇（含留言統計）")
        with _jobs_lock:
            job["results"] = results
            job["note"] = note
            job["status"] = "done"
    except InterruptedError:
        job_log(job, "已取消")
        with _jobs_lock:
            job["status"] = "cancelled"
    except Exception as exc:
        job_log(job, f"錯誤：{exc}")
        with _jobs_lock:
            job["status"] = "error"
            job["error"] = str(exc)


def run_download(task: dict, job: dict) -> None:
    """批次下載：把指定的文章網址逐篇抓全文（可含留言）合併成一個 TXT。"""
    try:
        urls = [u for u in (task.get("urls") or [])
                if isinstance(u, str) and u.startswith("https://www.ptt.cc/bbs/")][:300]
        if not urls:
            raise RuntimeError("沒有可下載的文章網址。")
        include_comments = bool(task.get("include_comments"))
        name = (task.get("name") or "PTT文章合集").strip() or "PTT文章合集"
        client = PTTClient(delay=float(task.get("delay", 0.4)))

        chunks = [
            f"PTT Assistant 批次下載｜{name}",
            f"整理時間：{now_tw():%Y-%m-%d %H:%M:%S}",
            f"共 {len(urls)} 篇｜{'含留言' if include_comments else '僅文章'}",
            "=" * 72,
            "",
        ]
        ok = 0
        for idx, url in enumerate(urls, 1):
            if job["cancel"]:
                raise InterruptedError
            with _jobs_lock:
                job["progress"] = {"done": idx, "total": len(urls)}
            try:
                art = client.article(url, include_comments=include_comments)
                ok += 1
                job_log(job, f"[{idx}/{len(urls)}] {art.title or url}")
                chunks.extend([
                    "#" * 72,
                    art.title or "(無標題)",
                    f"作者：{art.author}｜時間：{art.date_text}",
                    f"網址：{url}",
                    "#" * 72,
                    "",
                    art.body,
                    "",
                ])
            except Exception as exc:
                job_log(job, f"[{idx}/{len(urls)}] 讀取失敗：{exc}")
                chunks.extend([f"【讀取失敗】{url}（{exc}）", ""])

        if ok == 0:
            raise RuntimeError("所有文章都讀取失敗，未產生檔案。")
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = now_tw().strftime("%Y%m%d_%H%M")
        suffix = "含留言" if include_comments else "文章"
        path = OUTPUT_DIR / f"{safe_filename(name)}_{suffix}_{stamp}.txt"
        path.write_text("\n".join(chunks), encoding="utf-8-sig")
        job_log(job, f"完成：{ok}/{len(urls)} 篇 → {path.name}")
        with _jobs_lock:
            job["results"] = []
            job["note"] = f"已產生 TXT（{ok} 篇，{suffix}）：{path.resolve()}"
            job["file"] = path.name
            job["status"] = "done"
    except InterruptedError:
        job_log(job, "已取消")
        with _jobs_lock:
            job["status"] = "cancelled"
    except Exception as exc:
        job_log(job, f"錯誤：{exc}")
        with _jobs_lock:
            job["status"] = "error"
            job["error"] = str(exc)


def run_job(task: dict, job: dict) -> None:
    intent = (task.get("intent") or "scan").strip()
    if intent == "author_export":
        run_author_export(task, job)
    elif intent == "hot":
        run_hot(task, job)
    elif intent == "download":
        run_download(task, job)
    else:
        run_task(task, job)
    write_cache_if_track(job)


def start_job(task: dict, track_id: str | None = None) -> str:
    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "status": "running",
        "log": [],
        "progress": {"done": 0, "total": 0},
        "results": [],
        "note": "",
        "error": None,
        "cancel": False,
        "task": task,
        "track_id": track_id,
        "kind": (task.get("intent") or "scan").strip(),
        "file": None,
    }
    with _jobs_lock:
        JOBS[job_id] = job
        # 只保留最近 20 個 job，避免長開整天吃記憶體
        if len(JOBS) > 20:
            for old_id in list(JOBS)[:-20]:
                if JOBS[old_id]["status"] != "running":
                    JOBS.pop(old_id, None)
    threading.Thread(target=run_job, args=(task, job), daemon=True).start()
    return job_id


# ---------------------------------------------------------------- 快取與自動更新

CACHE_DIR = ROOT / "data" / "cache"
AUTO_REFRESH_HOURS = float(CONFIG.get("auto_refresh_hours", 6))
_TRACK_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def cache_path(track_id: str) -> Path:
    return CACHE_DIR / f"{track_id}.json"


def read_cache(track_id: str) -> dict | None:
    if not _TRACK_ID_RE.match(track_id or ""):
        return None
    p = cache_path(track_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_cache_if_track(job: dict) -> None:
    """追蹤項的掃描完成後把結果寫進快取，開頁即看不用重掃。"""
    with _jobs_lock:
        track_id = job.get("track_id") or ""
        if job["status"] != "done" or not track_id:
            return
        payload = {
            "track_id": track_id,
            "updated_at": now_tw().strftime("%Y-%m-%d %H:%M"),
            "results": job["results"],
            "note": job["note"],
        }
    if not _TRACK_ID_RE.match(track_id):
        return
    tmp = None
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        # tmp 檔名加 pid+隨機碼：同一 track 兩個寫入者（自動更新 vs 手動掃描）不共用暫存檔
        tmp = CACHE_DIR / f"{track_id}.{os.getpid()}.{uuid.uuid4().hex[:6]}.json.tmp"
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(cache_path(track_id))
        with _jobs_lock:
            job["cache_written"] = True
    except Exception as exc:
        print(f"寫入快取失敗（{track_id}）：{exc}")
    finally:
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)  # replace 失敗時清掉孤兒暫存檔
            except Exception:
                pass


def cache_summary(track_id: str) -> dict | None:
    c = read_cache(track_id)
    if not c:
        return None
    return {"updated_at": c.get("updated_at"), "count": len(c.get("results") or [])}


def cache_age_hours(track_id: str) -> float | None:
    if not _TRACK_ID_RE.match(track_id or ""):
        return None
    p = cache_path(track_id)
    if not p.exists():
        return None
    return (time.time() - p.stat().st_mtime) / 3600.0


def _refresh_log(line: str) -> None:
    """自動更新結果留檔（pythonw 排程沒 console，這是唯一的稽核痕跡）。"""
    try:
        log_file = ROOT / "data" / "refresh.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as f:
            f.write(f"{now_tw():%Y-%m-%d %H:%M:%S} {line}\n")
    except Exception:
        pass


def refresh_auto_tracks(force: bool = False) -> bool:
    """依序重掃標了 auto 的追蹤項（快取超過 AUTO_REFRESH_HOURS 才掃；force=全部重掃）。
    回傳是否全部成功。快取檔壞掉（讀不出）視同過期，避免壞檔六小時不自癒。"""
    all_ok = True
    for t in load_tracks():
        if not t.get("auto"):
            continue
        tid = t.get("id") or ""
        age = cache_age_hours(tid)
        if not force and age is not None and age < AUTO_REFRESH_HOURS and read_cache(tid) is not None:
            continue
        age_text = "無快取" if age is None else f"{age:.1f} 小時前"
        print(f"自動更新：{t.get('name')}（上次：{age_text}）")
        jid = start_job(dict(t.get("task") or {}), track_id=tid)
        with _jobs_lock:
            job = JOBS[jid]
        while True:
            with _jobs_lock:
                status = job["status"]
            if status != "running":
                break
            time.sleep(1)
        with _jobs_lock:
            cache_written = bool(job.get("cache_written"))
        if status == "done" and not cache_written:
            status_text = "done（但快取寫入失敗）"
            all_ok = False
        else:
            status_text = status
            if status != "done":
                all_ok = False
        print(f"自動更新完成：{t.get('name')}（{status_text}）")
        _refresh_log(f"{t.get('name')} -> {status_text}" + (f"（{job.get('error')}）" if status == "error" else ""))
    return all_ok


def auto_refresh_loop() -> None:
    while True:
        try:
            refresh_auto_tracks()
        except Exception as exc:
            print(f"自動更新迴圈錯誤：{exc}")
        time.sleep(900)  # 每 15 分鐘檢查一次是否有快取過期


# ---------------------------------------------------------------- 匯出


def export_results_txt(name: str, results: list[dict], note: str = "") -> Path:
    results = [r for r in results if isinstance(r, dict)]
    if not results:
        raise ValueError("結果格式不正確，沒有可匯出的項目")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = now_tw().strftime("%Y%m%d_%H%M")
    out_file = OUTPUT_DIR / f"{safe_filename(name)}_{stamp}.txt"
    chunks = [
        f"PTT Assistant 匯出｜{name}",
        f"整理時間：{now_tw():%Y-%m-%d %H:%M:%S}",
        f"共 {len(results)} 篇",
    ]
    if note:
        chunks.append(note)
    chunks.extend(["=" * 72, ""])
    for r in results:
        meta_line = f"作者：{r.get('author', '')}｜日期：{r.get('date', '')}"
        if r.get("board"):
            meta_line += f"｜看板：{r['board']}"
        if r.get("push"):
            meta_line += f"｜推文：{r['push']}"
        chunks.extend([
            f"【{r.get('title', '')}】",
            meta_line,
            f"網址：{r.get('url', '')}",
        ])
        if r.get("matched"):
            chunks.append(f"命中：{'、'.join(r['matched'])}")
        if r.get("preview"):
            chunks.extend(["", r["preview"]])
        chunks.extend(["", "-" * 72, ""])
    out_file.write_text("\n".join(chunks), encoding="utf-8-sig")
    return out_file


# ---------------------------------------------------------------- HTTP


class Handler(BaseHTTPRequestHandler):
    server_version = "PTTAssistant/2.0"

    def log_message(self, fmt, *args):  # 安靜一點，只留錯誤
        if args and str(args[1]) not in ("200", "204"):
            super().log_message(fmt, *args)

    # -- helpers --
    def _json(self, obj, status: int = 200) -> None:
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    def _file(self, path: Path, ctype: str) -> None:
        if not path.exists():
            self._json({"error": "not found"}, 404)
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # -- routes --
    def do_GET(self):
        try:
            self._route_get()
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass
        except Exception as exc:
            try:
                self._json({"error": f"伺服器錯誤：{exc}"}, 500)
            except Exception:
                pass

    def do_POST(self):
        try:
            self._route_post()
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass
        except Exception as exc:
            try:
                self._json({"error": f"伺服器錯誤：{exc}"}, 500)
            except Exception:
                pass

    def _route_get(self):
        parsed = urlparse(self.path)
        route = parsed.path

        if route in ("/", "/index.html"):
            self._file(WEB_DIR / "index.html", "text/html; charset=utf-8")
        elif route == "/api/meta":
            tracks = load_tracks()
            for t in tracks:
                t["cache"] = cache_summary(t.get("id") or "")
            self._json({
                "tracks": tracks,
                "store_words": STORE_WORDS,
                "drink_words": DRINK_WORDS,
                "boards": sorted(set(ALIAS_TO_BOARD.values())),
                "categories": CATEGORY_NAMES,
                "auto_refresh_hours": AUTO_REFRESH_HOURS,
            })
        elif route.startswith("/files/"):
            # 提供 output/ 內的 TXT 讓瀏覽器直接下載；只取 basename，擋路徑跳脫
            fname = Path(unquote(route[len("/files/"):])).name
            target = OUTPUT_DIR / fname
            if (not fname.lower().endswith(".txt") or not target.exists()
                    or target.resolve().parent != OUTPUT_DIR.resolve()):
                self._json({"error": "not found"}, 404)
                return
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(fname)}")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif route.startswith("/api/cache/"):
            track_id = route.rsplit("/", 1)[-1]
            cached = read_cache(track_id)
            if cached is None:
                self._json({"error": "尚無快取"}, 404)
            else:
                self._json(cached)
        elif route == "/api/article":
            qs = parse_qs(parsed.query)
            url = (qs.get("url") or [""])[0]
            if not url.startswith("https://www.ptt.cc/bbs/"):
                self._json({"error": "只接受 ptt.cc 文章網址"}, 400)
                return
            try:
                art = PTTClient(delay=0.2).article(url)
                self._json({"title": art.title, "body": art.body[:6000]})
            except Exception as exc:
                self._json({"error": str(exc)}, 502)
        elif route.startswith("/api/jobs/"):
            job_id = route.rsplit("/", 1)[-1]
            # 先在鎖內做快照，JSON 序列化與網路傳送放到鎖外，慢速 client 才不會卡住其他請求
            with _jobs_lock:
                job = JOBS.get(job_id)
                payload = None if not job else {
                    "id": job["id"],
                    "status": job["status"],
                    "log": job["log"][-40:],
                    "progress": dict(job["progress"]),
                    "results": job["results"] if job["status"] == "done" else [],
                    "note": job["note"],
                    "error": job["error"],
                    "kind": job.get("kind", "scan"),
                    "file": job.get("file"),
                }
            if payload is None:
                self._json({"error": "job not found"}, 404)
            else:
                self._json(payload)
        else:
            self._json({"error": "not found"}, 404)

    def _route_post(self):
        route = urlparse(self.path).path
        body = self._body()

        if route == "/api/parse":
            text = (body.get("text") or "").strip()
            if not text:
                self._json({"error": "請輸入要求"}, 400)
                return
            self._json(parse_request(text))
        elif route == "/api/run":
            task = body.get("task") or {}
            intent = (task.get("intent") or "scan").strip()
            if intent != "hot" and not (task.get("board") or "").strip():
                self._json({"error": "缺少板名"}, 400)
                return
            if intent == "author_export" and not (task.get("author") or "").strip():
                self._json({"error": "作者匯出需要作者帳號"}, 400)
                return
            track_id = body.get("track_id")
            if track_id and not _TRACK_ID_RE.match(str(track_id)):
                track_id = None
            self._json({"job_id": start_job(task, track_id=track_id)})
        elif route.startswith("/api/jobs/") and route.endswith("/cancel"):
            job_id = route.split("/")[3]
            with _jobs_lock:
                job = JOBS.get(job_id)
                if job:
                    job["cancel"] = True
            self._json({"ok": True})
        elif route == "/api/download":
            urls = body.get("urls") or []
            if not urls:
                self._json({"error": "沒有可下載的文章"}, 400)
                return
            task = {
                "intent": "download",
                "urls": urls,
                "include_comments": bool(body.get("include_comments")),
                "name": body.get("name") or "PTT文章合集",
            }
            self._json({"job_id": start_job(task)})
        elif route == "/api/export":
            results = body.get("results") or []
            if not results:
                self._json({"error": "沒有可匯出的結果"}, 400)
                return
            path = export_results_txt(
                body.get("name") or "PTT掃描結果", results, body.get("note") or ""
            )
            self._json({"path": str(path)})
        elif route == "/api/tracks":
            action = body.get("action")
            tracks = load_tracks()
            if action == "save":
                track = body.get("track") or {}
                if not track.get("name") or not (track.get("task") or {}).get("board"):
                    self._json({"error": "追蹤項需要名稱與板名"}, 400)
                    return
                track.setdefault("id", uuid.uuid4().hex[:8])
                tracks = [t for t in tracks if t.get("id") != track["id"]]
                tracks.append(track)
                save_tracks(tracks)
                self._json({"ok": True, "tracks": tracks})
            elif action == "delete":
                tracks = [t for t in tracks if t.get("id") != body.get("id")]
                save_tracks(tracks)
                self._json({"ok": True, "tracks": tracks})
            else:
                self._json({"error": "未知動作"}, 400)
        else:
            self._json({"error": "not found"}, 404)


def main():
    parser = argparse.ArgumentParser(description="PTT Assistant 網頁伺服器")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true", help="啟動時不自動開瀏覽器")
    parser.add_argument("--refresh-only", action="store_true",
                        help="不開伺服器，只重掃 auto 追蹤項並更新快取後結束（給每日排程用）")
    args = parser.parse_args()

    load_tracks()  # 確保 tracks.json 存在

    if args.refresh_only:
        print("每日快取更新開始")
        ok = refresh_auto_tracks(force=True)
        print("每日快取更新結束")
        raise SystemExit(0 if ok else 1)

    # Windows 的 SO_REUSEADDR 會讓同一埠被靜默重複綁定（兩個 server 搶請求），必須關掉
    class Server(ThreadingHTTPServer):
        allow_reuse_address = False

    try:
        server = Server(("127.0.0.1", args.port), Handler)
    except OSError as exc:
        print(f"啟動失敗：port {args.port} 已被占用（可能已經有一個 PTT Assistant 在執行）。")
        print(f"請直接開 http://127.0.0.1:{args.port}，或用 --port 改用其他埠。（{exc}）")
        raise SystemExit(1)

    url = f"http://127.0.0.1:{args.port}"
    print(f"PTT Assistant 網頁介面：{url}（Ctrl+C 結束）")
    # 背景自動更新：啟動先補掃過期快取，之後每 15 分鐘檢查一次
    threading.Thread(target=auto_refresh_loop, daemon=True).start()
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已結束。")


if __name__ == "__main__":
    main()
