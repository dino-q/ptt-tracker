#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
產生線上版靜態資料：跑省錢版總覽＋全站熱門兩個掃描，輸出 site/data/*.json。
GitHub Actions 排程呼叫；本機也可測：.venv\\Scripts\\python.exe scripts\\build_site.py
"""
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    TAIPEI = ZoneInfo("Asia/Taipei")
except Exception:  # Windows 無 tzdata 時退固定 UTC+8（台灣無夏令時間）
    TAIPEI = timezone(timedelta(hours=8))

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ♻️ 沿用 server.py 的掃描引擎與內建追蹤項定義
import gemini_client
from ptt_tool import PTTClient
from image_ocr import (OCR_ENGINE, append_ocr_block, clean_ocr_text,
                       ocr_article_images, strip_ocr_block)
from server import (ALWAYS_INCLUDE_HOT_BOARDS, CATEGORY_NAMES, article_id,
                    article_package, default_tracks,
                    classify, mark_new_results, run_hot, run_task)

LIVE_BASE = "https://dino-q.github.io/ptt-tracker/data"


def fetch_old(name: str) -> dict | None:
    """抓上一版線上資料：標「新」與沿用摘要用。抓不到（首次/斷網）就當沒有。"""
    try:
        with urllib.request.urlopen(f"{LIVE_BASE}/{name}.json", timeout=15) as r:
            data = json.loads(r.read().decode())
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def fill_previews(results: list[dict], old: dict | None, articles: dict,
                  budget: int = 60) -> tuple[int, int]:
    """摘要差異式補齊：舊資料有的直接沿用，只對新文章實際爬（省請求）；
    實際爬的順手收進 articles（閱讀器文章包）。"""
    old_prev = {r.get("url"): r.get("preview")
                for r in (old or {}).get("results", []) if r.get("preview")}
    client = None
    reused = fetched = 0
    for r in results:
        if r.get("preview"):
            continue
        if r.get("url") in old_prev:
            r["preview"] = old_prev[r["url"]]
            reused += 1
        elif fetched < budget:
            try:
                if client is None:
                    client = PTTClient(delay=0.4)
                art = client.article(r["url"])
                articles[article_id(r["url"])] = article_package(art)
                body = re.sub(r"\n{3,}", "\n\n", art.body).strip()
                if len(body) > 900:
                    body = body[:900].rstrip() + "\n……（已截短，請開原文）"
                r["preview"] = body
                fetched += 1
            except Exception:
                pass
    return reused, fetched


# 圖片辨識最多佔用多久。整個 Actions job 上限 30 分鐘，PTT 掃描本身要 2 分鐘，
# 留足夠餘裕給後面的熱門掃描與部署。超時就把剩下的留給下一輪。
IMAGE_PHASE_SECONDS = 480
# 連續幾篇整篇讀失敗就停手。Gemini 掛掉或撞額度時，硬跑完剩下的只是把
# job 時間和額度一起燒掉，一篇也救不回來。
MAX_CONSECUTIVE_FAILURES = 4


# 每輪最多讀幾篇。⚠️ 這個數字受 Gemini 免費層「每個模型每天 20 次」限制
# （2026-09-04 實測）：一篇最多 2 張圖＝2 次呼叫，一天 16 輪。
# 開通付費之後把 PTT_IMAGE_BUDGET 調大（12 以上）才有辦法在幾小時內補完。
IMAGE_BUDGET = int(os.environ.get("PTT_IMAGE_BUDGET", "2"))


def fill_image_ocr(results: list[dict], old: dict | None, articles: dict,
                   budget: int | None = None) -> tuple[int, int, int]:
    """為省錢文補圖片文字。

    已部署資料的 checked/text 直接沿用；每輪只處理有限篇，讓舊資料逐輪補齊、
    新文章優先處理，也避免 Actions 一次耗時過長。

    ⚠️ 沿用要看 `ocr_engine`：2026-09-04 從 Tesseract 換成 Gemini，舊資料裡
    那批 46% 雜訊如果照樣沿用，就會永遠留在線上。引擎對不上的一律當成沒讀過，
    並先把舊區塊從 preview／body 清掉再重讀。
    """
    budget = IMAGE_BUDGET if budget is None else budget
    ocr_available = gemini_client.available()
    old_map = {
        r.get("url"): r for r in (old or {}).get("results", [])
        if isinstance(r, dict) and r.get("url")
    }
    client = None
    reused = processed = recognized = 0
    started = time.monotonic()
    consecutive_failures = 0
    stopped = ""
    quota_hit = False
    for result in results:
        previous = old_map.get(result.get("url")) or {}
        # 沒有 ocr_engine 欄位的＝Tesseract 時代的舊資料，一律重讀
        same_engine = previous.get("ocr_engine") == OCR_ENGINE
        if previous.get("ocr_checked") and same_engine:
            result["ocr_checked"] = True
            result["image_urls"] = previous.get("image_urls") or []
            result["ocr_text"] = clean_ocr_text(previous.get("ocr_text") or "")
            result["ocr_engine"] = OCR_ENGINE
            result["preview"] = append_ocr_block(result.get("preview", ""), result["ocr_text"])
            aid = article_id(result.get("url") or "")
            if aid in articles:
                articles[aid]["body"] = append_ocr_block(
                    articles[aid].get("body", ""), result["ocr_text"]
                )
            result["cats"] = classify(f"{result.get('title', '')}\n{result.get('preview', '')}")
            reused += 1
            continue
        # 舊引擎讀過的殘留區塊先清掉。就算這輪輪不到重讀（超出額度或沒金鑰），
        # 使用者看到的也是乾淨原文，而不是上一代的亂碼。
        if previous.get("ocr_checked") and not same_engine:
            result["preview"] = strip_ocr_block(result.get("preview", ""))
            aid = article_id(result.get("url") or "")
            if aid in articles:
                articles[aid]["body"] = strip_ocr_block(articles[aid].get("body", ""))
        if not ocr_available:
            continue
        if processed >= budget or stopped:
            continue
        if time.monotonic() - started > IMAGE_PHASE_SECONDS:
            stopped = f"超過 {IMAGE_PHASE_SECONDS} 秒上限"
            continue
        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            stopped = f"連續 {consecutive_failures} 篇讀失敗"
            continue
        aid = article_id(result.get("url") or "")
        package = articles.get(aid)
        if not package:
            try:
                if client is None:
                    client = PTTClient(delay=0.4)
                package = article_package(client.article(result["url"]))
            except Exception:
                continue
        processed += 1
        outcome = ocr_article_images(package.get("body", ""), max_images=2)
        # 無圖片或完整跑完才永久記為 checked；網路暫時失敗者留給下輪重試。
        result["ocr_checked"] = bool(outcome["checked"])
        result["ocr_engine"] = outcome["engine"]
        result["image_urls"] = outcome["image_urls"]
        result["ocr_text"] = outcome["text"]
        result["preview"] = append_ocr_block(result.get("preview", ""), outcome["text"])
        package["body"] = append_ocr_block(package.get("body", ""), outcome["text"])
        if outcome["text"]:
            recognized += 1
        # 只有「整篇都沒讀成功」才算一次失敗；部分成功代表 Gemini 還活著
        if outcome["errors"] and not outcome["text"]:
            consecutive_failures += 1
        else:
            consecutive_failures = 0
        # 失敗要印出來。2026-09-04 踩到：6 篇讀失敗但 log 一個字都沒有，
        # 只能靠比對線上 JSON 才發現 imgur 全數 403——別再讓失敗變黑盒。
        for err in outcome["errors"][:3]:
            # 額度訊息很長，截斷才不會把 log 洗掉
            print(f"  圖片讀取失敗 {err[:160]}")
        if any("RESOURCE_EXHAUSTED" in e or "429" in e for e in outcome["errors"]):
            quota_hit = True
        result["cats"] = classify(f"{result.get('title', '')}\n{result.get('preview', '')}")
        articles[aid] = package
    if not ocr_available:
        print("圖片辨識：Gemini 不可用（缺 GEMINI_API_KEY 或 google-genai）；本輪不讀新圖片")
    if stopped:
        print(f"圖片辨識：本輪提早停手（{stopped}），剩下的留給下一輪")
    if quota_hit:
        print("圖片辨識：⚠️ 撞到 Gemini 免費層每日額度（每個模型 20 次／天）。"
              "要讓圖片辨識實際可用需要開通付費，或把 PTT_IMAGE_BUDGET 壓更低。")
    return reused, processed, recognized


def fetch_old_article(aid: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"{LIVE_BASE}/articles/{aid}.json", timeout=4) as r:
            d = json.loads(r.read().decode())
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def write_articles(out_dir: Path, items: list[dict], fresh: dict,
                   carry_cap: int = 320, fetch_budget: int = 40) -> tuple[int, int, int]:
    """為清單內每篇文寫 articles/{aid}.json：本輪剛抓的直接寫、其次從上一版部署搬運、
    都沒有的用補抓預算慢慢補齊（覆蓋率逐輪爬滿後補抓自然歸零）。"""
    art_dir = out_dir / "articles"
    art_dir.mkdir(parents=True, exist_ok=True)
    written = carried = fetched = 0
    client = None
    seen: set[str] = set()
    for r in items:
        aid = article_id(r.get("url") or "")
        if not aid or aid in seen:
            continue
        seen.add(aid)
        pkg = fresh.get(aid)
        if pkg is None and carried < carry_cap:
            carried += 1  # R2：計「嘗試數」不是成功數——CDN 大量 404/變慢時 build 不會拖到天荒地老
            pkg = fetch_old_article(aid)
        if pkg is None and fetched < fetch_budget:
            try:
                if client is None:
                    client = PTTClient(delay=0.4)
                pkg = article_package(client.article(r["url"]))
                fetched += 1
            except Exception:
                pkg = None
        if pkg is None:
            continue  # 沒有文章包：前端會退回顯示摘要＋原文連結
        (art_dir / f"{aid}.json").write_text(json.dumps(pkg, ensure_ascii=False), encoding="utf-8")
        written += 1
    return written, carried, fetched


def run(fn, task: dict) -> dict:
    job = {
        "id": "ci", "status": "running", "log": [], "progress": {},
        "results": [], "note": "", "error": None, "cancel": False,
        "task": task, "track_id": None, "kind": "", "file": None,
    }
    fn(task, job)
    if job["status"] != "done":
        tail = "\n".join(job["log"][-10:])
        raise SystemExit(f"掃描失敗：{job.get('error')}\n{tail}")
    return job


def main() -> None:
    now = datetime.now(TAIPEI).strftime("%Y-%m-%d %H:%M")
    tracks = {t["id"]: t for t in default_tracks()}
    out_dir = ROOT / "site" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    fresh_articles: dict = {}
    money = run(run_task, dict(tracks["lifeismoney-browse"]["task"]))
    old_money = fetch_old("money")
    mark_new_results(money["results"], (old_money or {}).get("results"))
    reused, fetched = fill_previews(money["results"], old_money, fresh_articles)
    print(f"money 摘要：沿用 {reused} 篇、新抓 {fetched} 篇")

    # ⚠️ 咖啡情報要排在圖片辨識**前面**。Gemini 免費層是「每個模型每天 20 次」
    # （2026-09-04 實測 429：GenerateRequestsPerDayPerProjectPerModel-FreeTier）。
    # 圖片辨識一輪就能把整天的額度吃光，先跑它的話置頂區塊會直接開天窗——
    # 而置頂區塊是使用者一進站就看到的東西，優先權比逐輪補圖高。
    # 咖啡那段只有「發現新文章」時才會真的呼叫，平常沿用不花額度。
    try:
        from coffee_news import build as build_coffee
        coffee = build_coffee(fetch_old("coffee"))
        if coffee:
            (out_dir / "coffee.json").write_text(
                json.dumps(coffee, ensure_ascii=False), encoding="utf-8")
            channels = coffee.get("通路") or []
            deals = sum(len(c.get("優惠") or []) for c in channels)
            print(f"coffee.json：{len(channels)} 個通路、{deals} 筆優惠"
                  f"（{coffee.get('article', {}).get('title', '')[:24]}）")
        else:
            print("coffee.json：這輪沒有可用的咖啡情報，略過")
    except Exception as exc:                                  # noqa: BLE001
        print(f"咖啡情報整段失敗（{type(exc).__name__}: {exc}），不影響其他資料")

    ocr_reused, ocr_processed, ocr_recognized = fill_image_ocr(
        money["results"], old_money, fresh_articles,
    )
    print(
        f"money 圖片辨識（{OCR_ENGINE}）：沿用 {ocr_reused} 篇、"
        f"讀 {ocr_processed} 篇、讀到內容 {ocr_recognized} 篇"
    )
    (out_dir / "money.json").write_text(json.dumps({
        "updated_at": now,
        "note": money["note"],
        "categories": CATEGORY_NAMES,
        "results": money["results"],
    }, ensure_ascii=False), encoding="utf-8")
    print(f"money.json：{len(money['results'])} 篇")

    old_hot = fetch_old("hot")
    hot_task = dict(tracks["hot-now"]["task"])
    # moptt 式收錄登記簿：上一版結果＋獨立 ledger 檔一起傳入，收錄時間才能跨輪持久
    hot_task["prev_results"] = (old_hot or {}).get("results") or []
    hot_task["prev_ledger"] = ((fetch_old("hot_ledger") or {}).get("ledger")
                               or (old_hot or {}).get("ledger"))  # 相容舊格式（曾內嵌於 hot.json）
    hot = run(run_hot, hot_task)
    mark_new_results(hot["results"], (old_hot or {}).get("results"))
    # 哨兵只看「本輪新收錄」（fresh_urls）：carried 舊統計不可讓守門失效（V2 修正）
    stats = [r for r in hot["results"] if r.get("comments") is not None]
    if hot["results"] and not stats:
        raise SystemExit("全部文章都沒取得留言統計，拒絕發佈沒有數字的清單")
    fresh_set = set(hot.get("fresh_urls") or [])
    fresh = [r for r in stats if r.get("url") in fresh_set]
    if fresh and all((r.get("rising") or 0) == 0 for r in fresh):
        raise SystemExit("本輪新收錄 rising 全 0：文章時間解析疑似失敗，拒絕發佈")
    per_hours = sorted(r["per_hour"] for r in fresh if r.get("per_hour"))
    if per_hours and per_hours[len(per_hours) // 2] > 2000:
        raise SystemExit(f"新收錄 per_hour 中位數異常（{per_hours[len(per_hours) // 2]}）：疑似時區/年齡計算錯誤，拒絕發佈")
    (out_dir / "hot.json").write_text(json.dumps({
        "updated_at": now,
        "note": hot["note"],
        "categories": CATEGORY_NAMES,
        # 固定收錄的低流量板（女板/BG）。這些板的文要累積到過留言門檻常常已經 1-3 週，
        # 但「討論度高」是現在才發生的事（留言持續在累積），用發文時間去擋等於永遠看不到。
        # 前端據此讓它們豁免天數窗——Dino 2026-09-04：「不然熱門文章很無聊」。
        "always_boards": ALWAYS_INCLUDE_HOT_BOARDS,
        "results": hot["results"],
    }, ensure_ascii=False), encoding="utf-8")
    # 登記簿拆獨立檔：只有 build 需要，不跟著頁面資料送給每個訪客
    (out_dir / "hot_ledger.json").write_text(json.dumps({
        "updated_at": now,
        "ledger": hot.get("ledger") or {},
    }, ensure_ascii=False), encoding="utf-8")

    # 閱讀器文章檔：每篇一個小 JSON，前端點「閱讀全文」才載入
    fresh_articles.update(hot.get("articles") or {})
    reader_items = money["results"] + hot["results"][:200]  # 熱門只維護最新 200 篇的全文
    written, carried_a, topup = write_articles(out_dir, reader_items, fresh_articles)
    print(f"文章檔：{written} 篇（掃描時抓 {len(fresh_articles)}、搬運 {carried_a}、補抓 {topup}）")
    print(f"hot.json：{len(hot['results'])} 篇")


if __name__ == "__main__":
    main()
