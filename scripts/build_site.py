#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
產生線上版靜態資料：跑省錢版總覽＋全站熱門兩個掃描，輸出 site/data/*.json。
GitHub Actions 排程呼叫；本機也可測：.venv\\Scripts\\python.exe scripts\\build_site.py
"""
import json
import re
import sys
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
from ptt_tool import PTTClient
from server import CATEGORY_NAMES, default_tracks, mark_new_results, run_hot, run_task

LIVE_BASE = "https://dino-q.github.io/ptt-tracker/data"


def fetch_old(name: str) -> dict | None:
    """抓上一版線上資料：標「新」與沿用摘要用。抓不到（首次/斷網）就當沒有。"""
    try:
        with urllib.request.urlopen(f"{LIVE_BASE}/{name}.json", timeout=15) as r:
            data = json.loads(r.read().decode())
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def fill_previews(results: list[dict], old: dict | None, budget: int = 60) -> tuple[int, int]:
    """摘要差異式補齊：舊資料有的直接沿用，只對新文章實際爬（省請求）。"""
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
                body = re.sub(r"\n{3,}", "\n\n", client.article(r["url"]).body).strip()
                if len(body) > 900:
                    body = body[:900].rstrip() + "\n……（已截短，請開原文）"
                r["preview"] = body
                fetched += 1
            except Exception:
                pass
    return reused, fetched


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

    money = run(run_task, dict(tracks["lifeismoney-browse"]["task"]))
    old_money = fetch_old("money")
    mark_new_results(money["results"], (old_money or {}).get("results"))
    reused, fetched = fill_previews(money["results"], old_money)
    print(f"money 摘要：沿用 {reused} 篇、新抓 {fetched} 篇")
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
        "results": hot["results"],
    }, ensure_ascii=False), encoding="utf-8")
    # 登記簿拆獨立檔：只有 build 需要，不跟著頁面資料送給每個訪客
    (out_dir / "hot_ledger.json").write_text(json.dumps({
        "updated_at": now,
        "ledger": hot.get("ledger") or {},
    }, ensure_ascii=False), encoding="utf-8")
    print(f"hot.json：{len(hot['results'])} 篇")


if __name__ == "__main__":
    main()
