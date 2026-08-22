#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PTT Assistant 網頁 UI 真瀏覽器驗收（Playwright）
用集中安裝的 Playwright venv 執行：
  C:/Users/AG_Di/Desktop/automation/Playwright/.venv/Scripts/python.exe tests/verify_ui.py

驗收原則：斷言「行為改變」而非元素存在（篩選後筆數下降、切板後欄位變更）。
需要 server.py 已在 127.0.0.1:8877 執行中。
"""
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = "http://127.0.0.1:8877"
SHOT_DIR = Path(__file__).resolve().parent / "screenshots"


def main() -> None:
    SHOT_DIR.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(BASE)

        # 1) 內建追蹤項有載入
        expect(page.locator(".track .name").first).to_contain_text("省錢版")

        # 2) 白話解析 → 板名欄位「行為改變」（Lifeismoney → Stock）
        board = page.locator("#f-board")
        before = board.input_value()
        assert before == "Lifeismoney", f"預設板名應為 Lifeismoney，實際 {before}"
        page.fill("#ask-input", "追蹤股版最近3天 台積電")
        page.click("#btn-parse")
        expect(board).to_have_value("Stock")
        print("PASS 白話解析：板名 Lifeismoney -> Stock")

        # 3) 縮小條件做一次真實掃描（1 頁、不讀內文，快）
        page.fill("#f-queries", "台積電")
        page.fill("#f-groups", "台積電")
        page.fill("#f-days", "3")
        page.fill("#f-pages", "1")
        if page.is_checked("#f-body"):
            page.click("#f-body")
        page.click("#btn-run")
        expect(page.locator("#results")).to_be_visible(timeout=120_000)
        items = page.locator("#items .item")
        n = items.count()
        assert n > 0, "掃描結果應至少 1 篇"
        print(f"PASS 真實掃描：Stock 板 3 天內台積電 {n} 篇")

        # 4) 結果過濾 → 筆數下降，清除 → 還原
        page.fill("#filter-box", "zzz_不會命中的字串_zzz")
        expect(page.locator("#items .item")).to_have_count(0)
        page.fill("#filter-box", "")
        expect(page.locator("#items .item")).to_have_count(n)
        print("PASS 結果過濾：筆數降為 0，清除後還原")

        # 5) 展開第一篇內文摘要（行為：preview 從隱藏變可見且有文字）
        first = items.first
        first.locator(".toggle").click()
        expect(first.locator(".preview")).to_be_visible(timeout=30_000)
        assert len(first.locator(".preview").inner_text().strip()) > 0
        print("PASS 內文摘要展開")

        page.screenshot(path=str(SHOT_DIR / "verify_ui.png"), full_page=True)
        browser.close()
    print("ALL PASS")


if __name__ == "__main__":
    main()
