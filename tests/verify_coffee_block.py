#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""咖啡置頂區塊驗收（真實瀏覽器，手機視窗）。

守什麼：
  省錢頁最上方要有一塊「本週咖啡優惠」，依通路分組、可用捷徑跳到該通路、
  顯示期間與優惠商品；熱門頁不該出現；沒有 coffee.json 時整塊不出現（不留空殼）。

斷言全部對著行為寫：
  ①省錢頁看得到、熱門頁看不到（切過去要真的消失）
  ②通路捷徑數量＝實際通路數，且點了會捲動到對應區段
  ③每個通路顯示自己的期間與優惠列
  ④收合鈕真的把內容藏起來，且狀態記得住（重載後仍收合）
  ⑤區塊本身不製造內捲軸（跟閱讀器同一個原則：手機上只留頁面一個捲軸）
"""
import argparse
import sys

from playwright.sync_api import sync_playwright

DEFAULT_URL = "http://127.0.0.1:8879/"


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

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 390, "height": 844})
        page = ctx.new_page()
        page.goto(args.url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2500)

        st = page.evaluate("""() => {
          const box = document.getElementById('coffee');
          if (!box || box.hidden) return {顯示: false};
          const jump = [...box.querySelectorAll('.coffee-jump button')].map(b => b.textContent);
          const secs = [...box.querySelectorAll('.coffee-ch')].map(s => ({
            名稱: s.querySelector('h3') ? s.querySelector('h3').firstChild.textContent : '',
            期間: s.querySelector('.ch-period') ? s.querySelector('.ch-period').textContent : '',
            筆數: s.querySelectorAll('.coffee-deal').length,
          }));
          const cs = getComputedStyle(box);
          return {
            顯示: true,
            標題: box.querySelector('h2') ? box.querySelector('h2').textContent : '',
            活動期間: box.querySelector('.coffee-period')
                      ? box.querySelector('.coffee-period').textContent : '',
            捷徑: jump, 區段: secs,
            內捲: box.scrollHeight > box.clientHeight + 4,
            overflowY: cs.overflowY,
            來源連結: !!box.querySelector('.coffee-meta a'),
          };
        }""")
        chk("省錢頁看得到咖啡區塊", st.get("顯示") is True)
        # Tor 2026-09-04 必要修正：第一次造訪應該是收合的，54 筆優惠不該擋在文章清單前面
        first = page.evaluate("""() => {
          const b = document.getElementById('coffee');
          if (!b || b.hidden) return null;
          const c = b.querySelector('#coffee-collapsible');
          return {收合: b.dataset.collapsed,
                  清單可見: !!(c && (c.offsetWidth || c.offsetHeight)),
                  捷徑可見: !!b.querySelector('.coffee-jump button').offsetWidth,
                  期間可見: !!(b.querySelector('.coffee-period') || {}).offsetWidth,
                  期間文字: (b.querySelector('.coffee-period') || {}).textContent || ''};
        }""")
        chk("首次造訪預設收合", first and first["收合"] == "1", str(first))
        chk("收合時清單藏起來", first and first["清單可見"] is False)
        chk("收合時通路捷徑仍看得到", first and first["捷徑可見"] is True)
        # 有些文章沒寫總期間，這時前端會從各通路期間合成一個範圍；
        # 兩種情況都必須顯示日期——收合態看不到日期等於沒回答「優惠到什麼時候」
        chk("收合時仍看得到活動期間", first and first["期間可見"] is True,
            f"期間文字={first.get('期間文字') if first else None}")
        # 收合狀態下點捷徑要自動展開，否則會捲到一個被藏起來的區段
        page.evaluate("() => document.querySelectorAll('.coffee-jump button')[1].click()")
        page.wait_for_timeout(900)
        after_chip = page.evaluate(
            "() => document.getElementById('coffee').dataset.collapsed")
        chk("收合時點捷徑會自動展開", after_chip == "0", f"collapsed={after_chip}")
        if not st.get("顯示"):
            browser.close()
            print("\n結果：區塊沒出現，後面不用測了")
            return 1

        print(f"      標題: {st['標題']}")
        print(f"      活動期間: {st['活動期間']}")
        print(f"      捷徑({len(st['捷徑'])}): {st['捷徑']}")
        for sec in st["區段"][:4]:
            print(f"        {sec['名稱']} | {sec['期間']} | {sec['筆數']} 筆")

        chk("有標題與來源連結", "咖啡" in st["標題"] and st["來源連結"])
        chk("捷徑數 = 通路區段數", len(st["捷徑"]) == len(st["區段"]),
            f"{len(st['捷徑'])} vs {len(st['區段'])}")
        chk("每個通路都有優惠列", all(s["筆數"] > 0 for s in st["區段"]))
        chk("至少一個通路標了自己的期間", any(s["期間"] for s in st["區段"]))
        chk("區塊本身不製造內捲軸", st["內捲"] is False, f"overflow-y={st['overflowY']}")
        h = page.evaluate("() => Math.round(document.querySelector"
                          "('.coffee-jump button').getBoundingClientRect().height)")
        chk("捷徑鈕觸控高度 >= 36px", h >= 36, f"{h}px（Tor 量到舊版只有 30px）")

        # 捷徑真的會捲動
        y0 = page.evaluate("() => window.scrollY")
        page.evaluate("() => document.querySelectorAll('.coffee-jump button')[3].click()")
        page.wait_for_timeout(1200)
        y1 = page.evaluate("() => window.scrollY")
        chk("點捷徑會捲動到該通路", y1 != y0, f"scrollY {y0} -> {y1}")

        # 收合
        page.evaluate("() => document.querySelector('.coffee-toggle').click()")
        page.wait_for_timeout(400)
        collapsed = page.evaluate("""() => {
          const box = document.getElementById('coffee');
          const body = box.querySelector('.coffee-body');
          return {旗標: box.dataset.collapsed,
                  內容可見: !!(body.offsetWidth || body.offsetHeight)};
        }""")
        chk("收合後內容真的藏起來", collapsed["內容可見"] is False, str(collapsed))

        # 記憶狀態
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(2500)
        remembered = page.evaluate(
            "() => { const b = document.getElementById('coffee');"
            " return b && !b.hidden ? b.dataset.collapsed : null; }")
        chk("重載後仍記得收合狀態", remembered == "1", f"dataset.collapsed={remembered}")

        # 熱門頁不該出現
        page.evaluate("() => document.querySelector('.coffee-toggle') && "
                      "document.querySelector('.coffee-toggle').click()")
        page.click('.viewbtn[data-view="hot"]')
        page.wait_for_timeout(1800)
        hidden_on_hot = page.evaluate(
            "() => { const b = document.getElementById('coffee'); return !b || b.hidden; }")
        chk("切到熱門頁時消失", hidden_on_hot is True)

        page.click('.viewbtn[data-view="money"]')
        page.wait_for_timeout(1500)
        back = page.evaluate(
            "() => { const b = document.getElementById('coffee'); return !!b && !b.hidden; }")
        chk("切回省錢頁時又出現", back is True)

        if args.shot:
            page.screenshot(path=args.shot, full_page=False)
        browser.close()

    print("\n結果：" + ("全過" if not fails else f"{len(fails)} 項失敗 -> {fails}"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
