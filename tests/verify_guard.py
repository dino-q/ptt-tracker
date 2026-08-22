#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B1 回歸：掃描進行中再啟動第二個掃描必須被擋下（行為斷言：出現錯誤訊息、原掃描照常完成）。"""
from playwright.sync_api import expect, sync_playwright

BASE = "http://127.0.0.1:8877"


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(BASE)
        expect(page.locator(".track .name").first).to_contain_text("省錢版")

        # 用小條件啟動第一個掃描
        page.fill("#f-board", "Stock")
        page.fill("#f-queries", "台積電")
        page.fill("#f-groups", "台積電")
        page.fill("#f-days", "3")
        page.fill("#f-pages", "1")
        if page.is_checked("#f-body"):
            page.click("#f-body")
        page.click("#btn-run")
        expect(page.locator("#progress")).to_be_visible()

        # 掃描中：再按追蹤項「掃描」與「開始掃描」都要被擋
        page.locator(".track button.run").first.click()
        expect(page.locator("#form-error")).to_contain_text("已有掃描進行中")
        assert page.locator("#btn-run").is_disabled()
        print("PASS 掃描中重複啟動被擋下")

        # 第一個掃描仍要正常完成
        expect(page.locator("#results")).to_be_visible(timeout=120_000)
        n = page.locator("#items .item").count()
        assert n > 0, "原掃描應正常完成且有結果"
        print(f"PASS 原掃描不受影響，完成 {n} 篇")
        browser.close()
    print("ALL PASS")


if __name__ == "__main__":
    main()
