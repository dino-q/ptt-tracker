#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在本機預覽「線上版」靜態頁（site/），用來驗收 GitHub Pages 那個頁面的改動。

為什麼需要這支：`啟動.bat` 的 [1] 起的是 server.py（本機掃描工具，用 web/index.html），
跟部署到 GitHub Pages 的 `site/index.html` **是兩個不同的頁面**。改了 site/ 卻用 [1] 去看，
會看不到任何差別。

資料來源：site/data/ 是產物（.gitignore 擋掉），本機通常是空的。
這支會自動去抓線上已部署的 JSON 當樣本，不重跑爬蟲（爬一輪要好幾分鐘）。

用法：
    python scripts/preview_site.py              # 缺資料才抓，然後開瀏覽器
    python scripts/preview_site.py --refresh    # 強制重抓線上資料
    python scripts/preview_site.py --port 8879
"""
from __future__ import annotations

import argparse
import functools
import http.server
import socketserver
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
DATA = SITE / "data"
LIVE_BASE = "https://dino-q.github.io/ptt-tracker/data"
FILES = ("money.json", "hot.json", "hot_ledger.json")


def fetch_live_data(refresh: bool) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        target = DATA / name
        if target.exists() and not refresh:
            print(f"  沿用既有 {name}（要換成最新的加 --refresh）")
            continue
        url = f"{LIVE_BASE}/{name}"
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                target.write_bytes(resp.read())
            print(f"  已抓 {name}（{target.stat().st_size // 1024} KB）")
        except Exception as exc:                              # noqa: BLE001
            # hot_ledger 之類缺了也能看，不要因此擋住預覽
            print(f"  ! {name} 抓不到：{exc}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8879)
    ap.add_argument("--refresh", action="store_true", help="強制重抓線上 JSON")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    if not (SITE / "index.html").exists():
        print(f"找不到 {SITE / 'index.html'}", file=sys.stderr)
        return 1

    print("準備線上版預覽資料：")
    fetch_live_data(args.refresh)

    class Handler(http.server.SimpleHTTPRequestHandler):
        """本機沒有的檔案就代理到線上版。

        為什麼要這樣（2026-09-04 踩到）：`site/data/articles/*.json` 是產物，
        本機幾乎是空的。少了它，前端會走「抓不到全文」的退路顯示純摘要，
        `fillArticle` 根本不會執行——驗收就會在驗一個沒被觸發的程式路徑，
        看起來過了其實什麼都沒測到。代理之後本機預覽才等於線上行為。
        """

        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(SITE), **kw)

        def do_GET(self):                                  # noqa: N802
            rel = self.path.split("?", 1)[0].lstrip("/")
            local = SITE / rel
            if rel and not local.exists():
                try:
                    with urllib.request.urlopen(f"{LIVE_BASE.rsplit('/', 1)[0]}/{rel}",
                                                timeout=20) as resp:
                        body = resp.read()
                        ctype = resp.headers.get("Content-Type", "application/octet-stream")
                    self.send_response(200)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                except Exception:                          # noqa: BLE001
                    pass          # 線上也沒有就照原本的流程回 404
            super().do_GET()

    handler = Handler
    socketserver.TCPServer.allow_reuse_address = True
    try:
        httpd = socketserver.TCPServer(("127.0.0.1", args.port), handler)
    except OSError as exc:
        print(f"\n連接埠 {args.port} 起不來：{exc}\n改用 --port 換一個。", file=sys.stderr)
        return 1

    url = f"http://127.0.0.1:{args.port}/"
    print(f"\n預覽網址：{url}")
    print("要看熱門那個改動：點上方「熱門文章」→ 分類列選「不限天數」")
    print("按 Ctrl+C 結束。\n")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已結束預覽。")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
