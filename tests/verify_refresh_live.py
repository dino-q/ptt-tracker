#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
「立即更新」真 API 端對端實測：對已部署的線上頁，用真 token 走完整流程
（CORS preflight、dispatch、帶 token 輪詢、資料換新、自動 reload）。
token 從環境變數 GH_TOKEN 讀（例：$env:GH_TOKEN = gh auth token），絕不寫檔、絕不印出。
會真的觸發一次雲端爬取（順便更新線上資料），全程約 3～5 分鐘。
"""
import os
import sys

from playwright.sync_api import sync_playwright

URL = "https://dino-q.github.io/ptt-tracker/"


def main() -> None:
    token = os.environ.get("GH_TOKEN", "").strip()
    if not token:
        sys.exit("需要環境變數 GH_TOKEN（例：先跑 $env:GH_TOKEN = gh auth token）")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context()
        page = ctx.new_page()
        page.add_init_script(f"localStorage.setItem('ptt_gh_token', {token!r})")
        alerts = []
        page.on("dialog", lambda d: (alerts.append(d.message), d.dismiss()))
        page.goto(URL)
        page.wait_for_selector("#refresh-btn", state="visible", timeout=20_000)
        before = page.locator("#note-text").inner_text()
        print(f"觸發前：{before}")
        page.click("#refresh-btn")
        page.wait_for_function(
            "document.getElementById('refresh-btn').textContent.includes('更新中')", timeout=15_000)
        print("dispatch 成功（CORS＋權限 OK），等待雲端跑完…")
        page.wait_for_function(
            f"document.getElementById('note-text') && document.getElementById('note-text').textContent !== {before!r}",
            timeout=8 * 60_000)
        after = page.locator("#note-text").inner_text()
        assert after != before, (before, after)
        assert not alerts, f"不應出現任何錯誤彈窗：{alerts}"
        assert page.locator("#refresh-btn").inner_text() == "立即更新"
        print(f"觸發後：{after}")
        browser.close()
    print("LIVE PASS：真 API 全流程（dispatch→輪詢→換新→自動 reload）")


if __name__ == "__main__":
    main()
