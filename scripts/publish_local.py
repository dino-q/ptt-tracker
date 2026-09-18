#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本機每日工作：更新網頁 UI 快取 → 產線上版資料 → 推上 GitHub。

為什麼改成本機跑（2026-09-18 Dino 拍板）：
PTT 從 2026-09-16 18:50 UTC 起對 GitHub Actions 的機房 IP 回 403 Forbidden，
`update-site` 連續 7 次全掛；同一天同一支程式從本機出去是 200。封鎖是認來源 IP
（整段機房），改浮動 IP 或換 Cloudflare 都試過照樣 403，所以抓取整個搬回本機，
GitHub 只留「把 site/ 部署到 Pages」這一步（部署不需要連 PTT，不受封鎖影響）。

排程 `PTT_Assistant_DailyCache` 呼叫（pythonw 無視窗）；稽核一律看 data/refresh.log。
手動測：.venv\\Scripts\\python.exe scripts\\publish_local.py
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

# ♻️ 沿用 server.py 的每日快取更新與 log（CODE_MAP：refresh_auto_tracks / _refresh_log）
from server import _refresh_log, now_tw, refresh_auto_tracks
# ♻️ 沿用 scripts/build_site.py 的線上資料產生器（原本由 Actions 呼叫，內容一字未改）
import build_site

DATA_PATHS = ["site/data"]


def git(*args: str) -> subprocess.CompletedProcess:
    """跑 git 並把輸出收起來（pythonw 沒有 console，錯誤要自己記進 log）。"""
    return subprocess.run(
        ["git", *args], cwd=str(ROOT), capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )


def publish_site_data() -> bool:
    """把 site/data 的變動 commit 並推上 master。沒有變動就不 commit（避免空 commit 洗歷史）。"""
    add = git("add", "--", *DATA_PATHS)
    if add.returncode != 0:
        _refresh_log(f"線上發佈 -> git add 失敗（{add.stderr.strip()[:200]}）")
        return False

    # --quiet 的 returncode：0＝沒差異、1＝有差異
    if git("diff", "--cached", "--quiet", "--", *DATA_PATHS).returncode == 0:
        _refresh_log("線上發佈 -> 資料無變動，不推送")
        return True

    msg = f"chore(data): 本機更新線上資料 {now_tw():%Y-%m-%d %H:%M}"
    commit = git("commit", "-m", msg, "--", *DATA_PATHS)
    if commit.returncode != 0:
        _refresh_log(f"線上發佈 -> git commit 失敗（{commit.stderr.strip()[:200]}）")
        return False

    push = git("push", "origin", "HEAD:master")
    if push.returncode != 0:
        # 推不上去時 commit 留在本機，下次排程會一起推，不會掉資料
        _refresh_log(f"線上發佈 -> git push 失敗（{push.stderr.strip()[:200]}）")
        return False

    _refresh_log("線上發佈 -> 已推送，GitHub Pages 開始部署")
    return True


def main() -> None:
    ok = True

    print("步驟 1／3：更新本機網頁快取")
    try:
        if not refresh_auto_tracks(force=True):
            ok = False
    except Exception as exc:                                  # noqa: BLE001
        ok = False
        _refresh_log(f"本機快取 -> 例外（{type(exc).__name__}: {exc}）")

    print("步驟 2／3：產生線上版資料")
    try:
        build_site.main()
        _refresh_log("線上資料 -> done")
    except SystemExit as exc:
        # build_site 的守門（沒留言統計、rising 全 0 等）走 SystemExit，
        # 這種情況寧可不發佈，保留上一版線上資料。
        ok = False
        _refresh_log(f"線上資料 -> 拒絕發佈（{exc}）")
        print("線上資料產生被守門擋下，跳過發佈")
        raise SystemExit(1)
    except Exception as exc:                                  # noqa: BLE001
        ok = False
        _refresh_log(f"線上資料 -> 失敗（{type(exc).__name__}: {exc}）")
        print("線上資料產生失敗，跳過發佈")
        raise SystemExit(1)

    print("步驟 3／3：推上 GitHub")
    if not publish_site_data():
        ok = False

    print("本機每日工作結束")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
