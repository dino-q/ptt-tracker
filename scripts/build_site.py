#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
產生線上版靜態資料：跑省錢版總覽＋全站熱門兩個掃描，輸出 site/data/*.json。
GitHub Actions 排程呼叫；本機也可測：.venv\\Scripts\\python.exe scripts\\build_site.py
"""
import json
import sys
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
from server import CATEGORY_NAMES, default_tracks, run_hot, run_task


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
    (out_dir / "money.json").write_text(json.dumps({
        "updated_at": now,
        "note": money["note"],
        "categories": CATEGORY_NAMES,
        "results": money["results"],
    }, ensure_ascii=False), encoding="utf-8")
    print(f"money.json：{len(money['results'])} 篇")

    hot = run(run_hot, dict(tracks["hot-now"]["task"]))
    # 哨兵：時間計算壞掉時寧可讓 Action 紅燈，不要安靜發佈壞資料（2026-08-22 UTC 時區事故的教訓）
    stats = [r for r in hot["results"] if r.get("comments") is not None]
    if stats and all((r.get("rising") or 0) == 0 for r in stats):
        raise SystemExit("rising 全為 0：文章時間解析疑似失敗，拒絕發佈")
    per_hours = sorted(r["per_hour"] for r in stats if r.get("per_hour"))
    if per_hours and per_hours[len(per_hours) // 2] > 2000:
        raise SystemExit(f"per_hour 中位數異常（{per_hours[len(per_hours) // 2]}）：疑似時區/年齡計算錯誤，拒絕發佈")
    (out_dir / "hot.json").write_text(json.dumps({
        "updated_at": now,
        "note": hot["note"],
        "categories": CATEGORY_NAMES,
        "results": hot["results"],
    }, ensure_ascii=False), encoding="utf-8")
    print(f"hot.json：{len(hot['results'])} 篇")


if __name__ == "__main__":
    main()
