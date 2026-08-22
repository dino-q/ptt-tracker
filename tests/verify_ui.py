#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""進階掃描流程驗收（v2.2 分頁式 IA）：白話解析導向、真實掃描、過濾、內文展開。"""
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

        # 白話解析：一般關鍵字 → 自動切到進階掃描頁並填好條件
        page.fill("#ask-input", "追蹤股版最近3天 台積電")
        page.click("#btn-parse")
        expect(page.locator("#view-advanced")).to_be_visible()
        expect(page.locator("#f-board")).to_have_value("Stock")
        print("PASS 白話解析：導向進階掃描頁，板名 Stock")

        # 縮小條件真實掃描
        page.fill("#f-queries", "台積電")
        page.fill("#f-groups", "台積電")
        page.fill("#f-days", "3")
        page.fill("#f-pages", "1")
        if page.is_checked("#f-body"):
            page.click("#f-body")
        page.click("#btn-run")
        expect(page.locator("#btn-run")).to_be_disabled()
        expect(page.locator("#btn-run")).to_be_enabled(timeout=120_000)
        expect(page.locator("#results")).to_be_visible()
        items = page.locator("#items .item")
        n = items.count()
        assert n > 0, "掃描結果應至少 1 篇"
        print(f"PASS 真實掃描：Stock 板 3 天內台積電 {n} 篇")

        # 過濾行為
        page.fill("#filter-box", "zzz_不會命中的字串_zzz")
        expect(page.locator("#items .item")).to_have_count(0)
        page.fill("#filter-box", "")
        expect(page.locator("#items .item")).to_have_count(n)
        print("PASS 結果過濾：筆數降為 0，清除後還原")

        # 內文摘要展開
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
