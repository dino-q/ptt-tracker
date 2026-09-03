#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
熱門「不限天數」分類驗收（真實瀏覽器 ＋ 本機靜態站台）。

守什麼：
  低流量板（WomenTalk / Boy-Girl）能過留言門檻的文常已 1-3 週，會被熱門頁預設的
  3 天窗（dayOk 用發文時間過濾）整批濾掉——資料在 hot.json 裡，畫面上卻一篇都沒有。
  「不限天數」分類就是為此而加，這支測試守的是它真的改變行為，而不只是「按鈕存在」。

斷言全部對著行為寫：
  ①預設仍受天數窗限制（筆數少於全集）且兩板看不到
  ②分類列出現「不限天數」
  ③點下去筆數變多、兩板出得來、沒被濾成空清單
  ④依收錄時間新→舊排序
  ⑤期間／排序控制項在此分類下隱藏（不留按了沒反應的鈕）
  ⑥切回「全部」會還原成天數窗，兩板重新消失

⚠️ 兩個踩過的坑，改這支時別退回去：
  - 斷言只能量 #items（結果清單）。量整頁 body 會把「看板篩選」晶片上的板名一起算進去，
    導致「畫面上看得到 Boy-Girl」永遠成立、測試假通過。
  - 分頁要用 .viewbtn[data-view="hot"] 點。用 text=熱門 不保證命中分頁鈕，
    會停在省錢版上量到別的數字。

跑法（需先起站台）：
    python -m http.server 8891 --directory site
    <playwright venv>/python tests/verify_alltime_tab.py [--url http://127.0.0.1:8891/]
"""
import argparse
import re
import sys

from playwright.sync_api import sync_playwright

DEFAULT_URL = "http://127.0.0.1:8891/"
BOARDS = ("Boy-Girl", "WomenTalk")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--shot", default="")
    args = ap.parse_args()

    fails: list[str] = []

    def chk(name: str, cond: bool, detail: str = "") -> None:
        print(("  PASS " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""))
        if not cond:
            fails.append(name)

    def count_of(page) -> int:
        return int(re.search(r"\d+", page.inner_text("#count")).group())

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(args.url, wait_until="networkidle")
        page.click('.viewbtn[data-view="hot"]')
        page.wait_for_timeout(1500)

        total = page.evaluate("DATA.hot.results.length")
        default_count = count_of(page)
        items_default = page.inner_text("#items")
        print(f"[預設] 共 {default_count} 篇（全集 {total}）")
        chk("預設仍受天數窗限制（少於全集）", default_count < total,
            f"{default_count} / {total}")
        for b in BOARDS:
            chk(f"預設看不到 {b}", b not in items_default)

        tabs = page.inner_text("#cat-tabs")
        chk("分類列出現「不限天數」", "不限天數" in tabs, tabs.replace("\n", " ")[:160])

        page.click('#cat-tabs button:has-text("不限天數")')
        page.wait_for_timeout(1200)
        all_count = count_of(page)
        items_all = page.inner_text("#items")
        print(f"[不限天數] 共 {all_count} 篇")
        chk("筆數確實變多", all_count > default_count, f"{default_count} → {all_count}")
        for b in BOARDS:
            chk(f"{b} 出得來", b in items_all)
        chk("沒有被濾成空清單", all_count > 0)

        order_ok = page.evaluate("""() => {
          const rows = [...document.querySelectorAll('#items a[href*="ptt.cc"]')].map(a => a.href);
          const map = Object.fromEntries(DATA.hot.results.map(r => [r.url, r.accepted_at || 0]));
          const seq = rows.map(u => map[u]).filter(v => v !== undefined);
          for (let i = 1; i < seq.length; i++) if (seq[i] > seq[i - 1]) return false;
          return seq.length > 5;
        }""")
        chk("依收錄時間新→舊排序", order_ok)

        page.click("#filter-btn")
        page.wait_for_timeout(400)
        chk("排序鈕在此分類下隱藏", not page.is_visible("#sort-toggle"))
        chk("天數鈕在此分類下隱藏", not page.is_visible("#day-filter"))

        page.click('#cat-tabs button:has-text("全部")')
        page.wait_for_timeout(1200)
        back_count = count_of(page)
        chk("切回「全部」還原成天數窗", back_count == default_count,
            f"{back_count} vs {default_count}")
        chk("切回後又看不到 Boy-Girl", "Boy-Girl" not in page.inner_text("#items"))

        if args.shot:
            page.screenshot(path=args.shot)
        browser.close()

    print("\n結果：" + ("全過" if not fails else f"{len(fails)} 項失敗 -> {fails}"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
