#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""併發防護回歸（v2.2 分頁式 IA）：掃描進行中，其他執行按鈕全部擋下、原掃描照常完成。"""
from playwright.sync_api import expect, sync_playwright

BASE = "http://127.0.0.1:8877"


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(BASE)

        # 進階掃描頁：小條件啟動第一個掃描
        page.locator('.viewbtn[data-view="advanced"]').click()
        page.fill("#f-board", "Stock")
        page.fill("#f-queries", "台積電")
        page.fill("#f-groups", "台積電")
        page.fill("#f-days", "3")
        page.fill("#f-pages", "1")
        if page.is_checked("#f-body"):
            page.click("#f-body")
        page.click("#btn-run")
        expect(page.locator("#progress")).to_be_visible()

        # 掃描中：所有 runbtn 都應 disabled；切到省錢頁按更新也要被擋
        assert page.locator("#btn-run").is_disabled()
        page.locator('.viewbtn[data-view="money"]').click()
        assert page.locator("#btn-m-run").is_disabled(), "掃描中省錢頁按鈕應停用"
        print("PASS 掃描中所有執行按鈕停用")

        # 原掃描要正常完成（完成會自動切回進階頁）
        expect(page.locator("#btn-run")).to_be_enabled(timeout=120_000)
        expect(page.locator("#view-advanced")).to_be_visible()
        n = page.locator("#items .item").count()
        assert n > 0, "原掃描應正常完成且有結果"
        print(f"PASS 原掃描不受影響，完成 {n} 篇並自動切回進階頁")
        browser.close()
    print("ALL PASS")


if __name__ == "__main__":
    main()
