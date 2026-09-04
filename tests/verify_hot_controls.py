#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""熱門頁控制項驗收（真實瀏覽器）。

守什麼（2026-09-04 Dino 三項要求）：
  ①「不限天數」分類已移除——它跟篩選面板的「含回鍋（不分期間）」做同一件事，
    兩個入口只會讓人搞混。含回鍋仍要能把舊文全部放出來。
  ②新增「依時間」排序：用**發文時間**，不是收錄時間。
    兩者不同——三週前的文今天才被收錄，在「最新熱門」排很前面、在「依時間」要落到後面。
  ③看板順序可編輯，且會記住。

斷言全部對著行為寫：不驗「按鈕在不在」，驗「順序/筆數真的變了」。
"""
import argparse
import sys

# cp950 主控台印不出 ◀▶ 會 UnicodeEncodeError 讓測試自己崩潰
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

from playwright.sync_api import sync_playwright

DEFAULT_URL = "http://127.0.0.1:8879/"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    args = ap.parse_args()

    fails: list[str] = []

    def chk(name, cond, detail=""):
        print(("  PASS " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
        if not cond:
            fails.append(name)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 900, "height": 900})
        page = ctx.new_page()
        page.goto(args.url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(1500)
        page.click('.viewbtn[data-view="hot"]')
        page.wait_for_timeout(1800)

        # ⓪ 固定收錄板（女板/BG）預設就要看得到——原本由已移除的「不限天數」分類守，
        #    現在改由 always_boards 豁免天數窗達成，斷言搬到這裡。
        items = page.inner_text("#items")
        for b in ("Boy-Girl", "WomenTalk"):
            chk(f"預設就看得到 {b}（固定收錄板豁免天數窗）", b in items)
        c0 = page.evaluate("() => +document.getElementById('count').textContent.match(/\d+/)[0]")
        tot0 = page.evaluate("() => DATA.hot.results.length")
        chk("其他板仍受天數窗限制（沒有變成全放）", c0 < tot0, f"{c0} / {tot0}")

        # ① 「不限天數」分類必須不存在
        tabs = page.inner_text("#cat-tabs")
        chk("分類列已無「不限天數」", "不限天數" not in tabs, tabs.replace("\n", " ")[:90])

        page.click("#filter-btn")
        page.wait_for_timeout(400)

        # 含回鍋要能取代它：切過去筆數要變成全集
        total = page.evaluate("() => DATA.hot.results.length")
        before = page.evaluate("() => +document.getElementById('count').textContent.match(/\\d+/)[0]")
        page.click('#mode-toggle .tab[data-mode="all"]')
        page.wait_for_timeout(900)
        after = page.evaluate("() => +document.getElementById('count').textContent.match(/\\d+/)[0]")
        chk("「含回鍋」把舊文全放出來（＝原本不限天數的作用）",
            after > before and after == total, f"{before} -> {after} / 全集 {total}")
        page.click('#mode-toggle .tab[data-mode="recent"]')
        page.wait_for_timeout(700)

        # ② 依時間排序
        has_posted = page.evaluate(
            "() => !!document.querySelector('#sort-toggle .tab[data-sort=\"posted\"]')")
        chk("排序多了「依時間」", has_posted)
        if has_posted:
            def order_of(sort_key):
                page.click(f'#sort-toggle .tab[data-sort="{sort_key}"]')
                page.wait_for_timeout(900)
                return page.evaluate("""() => {
                  const map = Object.fromEntries(
                    DATA.hot.results.map(r => [r.url, {p: r.post_ts || 0, a: r.accepted_at || 0}]));
                  return [...document.querySelectorAll('#items a[href*="ptt.cc"]')]
                    .map(a => map[a.href]).filter(Boolean).slice(0, 40);
                }""")

            posted = order_of("posted")
            desc_p = all(posted[i]["p"] >= posted[i + 1]["p"] for i in range(len(posted) - 1))
            chk("「依時間」確實照發文時間新→舊", desc_p and len(posted) > 5,
                f"取樣 {len(posted)} 筆")

            newest = order_of("time")
            desc_a = all(newest[i]["a"] >= newest[i + 1]["a"] for i in range(len(newest) - 1))
            chk("「最新熱門」仍照收錄時間排", desc_a and len(newest) > 5)
            # 兩者必須是不同的排序結果，否則新增這個選項沒有意義
            chk("兩種排序結果確實不同",
                [x["p"] for x in posted] != [x["p"] for x in newest])

        # ③ 看板排序可編輯
        page.click("#board-filter .bf-toggle")
        page.wait_for_timeout(500)
        if not page.query_selector("#board-filter .bf-edit"):
            page.click("#board-filter .bf-toggle")   # 本來是展開的話再點一次
            page.wait_for_timeout(500)

        def board_names():
            return page.evaluate("""() => [...document.querySelectorAll(
              '#board-filter .tab:not(.bf-toggle):not(.bf-edit):not(.bf-reset), #board-filter .bf-name')]
              .map(e => e.textContent.trim().split(' ')[0])""")

        chk("有「調整順序」入口", bool(page.query_selector("#board-filter .bf-edit")))
        page.click("#board-filter .bf-edit")
        page.wait_for_timeout(500)
        before_order = board_names()
        print(f"      編輯前: {before_order[:6]}")
        # 把第 3 個往前移兩次
        page.evaluate("""() => {
          const items = [...document.querySelectorAll('#board-filter .bf-item')];
          items[2].querySelector('.bf-move').click();
        }""")
        page.wait_for_timeout(400)
        after_order = board_names()
        print(f"      移動後: {after_order[:6]}")
        chk("按左移鈕之後順序真的改變", before_order != after_order,
            f"{before_order[:4]} -> {after_order[:4]}")
        chk("被移動的板往前了",
            len(before_order) > 2 and after_order.index(before_order[2]) < 2,
            f"{before_order[2]} 從 index 2 -> {after_order.index(before_order[2])}")

        # 記憶：重載後仍是自訂順序
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(2000)
        page.click('.viewbtn[data-view="hot"]')
        page.wait_for_timeout(1500)
        page.click("#filter-btn")
        page.wait_for_timeout(400)
        reloaded = board_names()
        print(f"      重載後: {reloaded[:6]}")
        chk("重載後仍記得自訂順序",
            reloaded[:4] == [n for n in after_order if n in reloaded][:4],
            f"{reloaded[:4]}")

        browser.close()

    print("\n結果：" + ("全過" if not fails else f"{len(fails)} 項失敗 -> {fails}"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
