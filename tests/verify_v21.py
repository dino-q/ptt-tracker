#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v2.2 分頁式 IA 驗收：開頁即看快取、三功能頁、分類頁籤、批次下載全文。
需要 server 在 127.0.0.1:8877 且 lifeismoney-browse / hot-now 快取已存在。
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

        # 1) 開頁＝省錢優惠頁＋快取結果，不用按掃描
        expect(page.locator('.viewbtn[data-view="money"]')).to_have_class(r"viewbtn active")
        expect(page.locator("#results")).to_be_visible(timeout=15_000)
        n_all = page.locator("#items .item").count()
        assert n_all > 0, "開頁應直接顯示省錢版快取"
        expect(page.locator("#note")).to_contain_text("快取更新於")
        print(f"PASS 開頁即看省錢快取：{n_all} 篇")

        # 2) 分類頁籤行為
        store_tab = page.locator("#cat-tabs .tab", has_text="四大超商")
        store_tab.click()
        n_store = page.locator("#items .item").count()
        assert 0 < n_store < n_all, f"分類過濾應讓筆數下降（{n_all} -> {n_store}）"
        page.locator("#cat-tabs .tab", has_text="全部").click()
        assert page.locator("#items .item").count() == n_all
        print(f"PASS 分類頁籤：全部 {n_all} -> 四大超商 {n_store} -> 還原")

        # 2b) 天數篩選：預設 3 天，切 10 天筆數應增加、切 1 天應減少
        expect(page.locator("#day-filter")).to_be_visible()
        page.locator('#day-filter .tab[data-days="10"]').click()
        n10 = page.locator("#items .item").count()
        page.locator('#day-filter .tab[data-days="1"]').click()
        n1 = page.locator("#items .item").count()
        page.locator('#day-filter .tab[data-days="3"]').click()
        assert n1 <= n_all <= n10 and n10 > n_all, f"天數視窗應單調（1天{n1} <= 3天{n_all} <= 10天{n10}）"
        print(f"PASS 天數篩選：1天 {n1} / 3天 {n_all} / 10天 {n10}")

        # 2c) 置頂：把第 2 篇置頂後應跳到第 1 位並帶「置頂」徽章；取消後還原
        second_title = page.locator("#items .item h3 a").nth(1).inner_text()
        page.locator("#items .item").nth(1).locator(".act", has_text="置頂").first.click()
        expect(page.locator("#items .item").first.locator("h3 a")).to_have_text(second_title)
        expect(page.locator("#items .item").first.locator(".badge-pin")).to_be_visible()
        page.locator("#items .item").first.locator(".act", has_text="取消置頂").click()
        expect(page.locator("#items .item").first.locator(".badge-pin")).to_have_count(0)
        print(f"PASS 置頂：{second_title[:20]}… 置頂→跳首位→取消還原")

        # 2d) 回到最上方：捲到底出現按鈕，點了回頂
        page.mouse.wheel(0, 20000)
        expect(page.locator("#to-top")).to_be_visible()
        page.locator("#to-top").click()
        page.wait_for_function("window.scrollY < 50")
        print("PASS 回到最上方")

        # 3) 熱門文章頁：快取即看＋看板標示＋排序切換行為
        page.locator('.viewbtn[data-view="hot"]').click()
        expect(page.locator("#note")).to_contain_text("人氣前", timeout=10_000)
        metas = page.locator("#items .item .meta").all_inner_texts()
        assert any("板" in m for m in metas), "熱門結果應標示來源看板"
        assert any("留言" in m for m in metas), "熱門結果應顯示留言數"
        print(f"PASS 熱門頁快取即看：{page.locator('#items .item').count()} 篇（含留言統計）")

        import re as _re
        expect(page.locator("#sort-toggle")).to_be_visible()
        page.locator("#sort-toggle .tab", has_text="總留言數").click()
        nums = []
        for m in page.locator("#items .item .meta").all_inner_texts():
            mm = _re.search(r"留言 (\d+)", m)
            if mm:
                nums.append(int(mm.group(1)))
        assert nums and nums == sorted(nums, reverse=True), f"總留言排序應遞減：{nums[:6]}"
        print("PASS 排序切換：總留言數遞減")

        # 3b) 看板自選：隱藏第一個看板 chip → 該板卡片消失，再點回還原
        expect(page.locator("#board-filter")).to_be_visible()
        first_chip = page.locator("#board-filter .tab").first
        chip_board = first_chip.inner_text().rsplit(" ", 1)[0]
        n_before = page.locator("#items .item").count()
        first_chip.click()
        metas_after = page.locator("#items .item .meta").all_inner_texts()
        assert not any(chip_board + " 板" in m for m in metas_after), f"{chip_board} 應被隱藏"
        assert page.locator("#items .item").count() < n_before
        page.locator("#board-filter .tab", has_text=chip_board).first.click()
        assert page.locator("#items .item").count() == n_before
        print(f"PASS 看板自選：{chip_board} 隱藏→還原（{n_before} 篇）")
        # 回省錢頁排序切換要隱藏
        page.locator('.viewbtn[data-view="money"]').click()
        expect(page.locator("#sort-toggle")).to_be_hidden()
        page.locator('.viewbtn[data-view="hot"]').click()

        # 4) 白話解析導向作者下載頁
        page.fill("#ask-input", "幫我上PTT的marvel版找abc123這個作者，並且把他的創作做成txt檔")
        page.click("#btn-parse")
        expect(page.locator("#view-author")).to_be_visible()
        expect(page.locator("#f-a-author")).to_have_value("abc123")
        expect(page.locator("#f-a-board")).to_have_value("marvel")
        print("PASS 白話解析：導向作者下載頁並填好欄位")

        # 5) 批次下載全文（省錢頁 -> 四大超商子集 -> 含留言）
        page.locator('.viewbtn[data-view="money"]').click()
        page.locator("#cat-tabs .tab", has_text="四大超商").click()
        n_dl = page.locator("#items .item").count()
        page.check("#dl-comments")
        page.click("#btn-export")
        expect(page.locator("#progress")).to_be_visible()
        link = page.locator("#export-path a")
        expect(link).to_be_visible(timeout=180_000)
        href = link.get_attribute("href")
        assert href and href.startswith("/files/"), href
        resp = page.request.get(BASE + href)
        assert resp.status == 200, resp.status
        body = resp.text()
        assert "留言" in body and "#" * 72 in body, "TXT 應含全文與留言區塊"
        print(f"PASS 批次下載：{n_dl} 篇含留言 TXT 可由瀏覽器下載（{href}）")

        page.screenshot(path=str(SHOT_DIR / "verify_v21.png"), full_page=True)
        browser.close()
    print("ALL PASS")


if __name__ == "__main__":
    main()
