#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""閱讀器「漸進展開」驗收（真實瀏覽器，手機視窗）。

守什麼：
  2026-09-04 之前 .preview 是 `max-height:72vh; overflow-y:auto` 的內捲框。
  手機實測內容 4075px 塞進 608px 視窗（6.7 倍），頁面與卡片兩個捲軸互搶，
  滑動會卡住。改成「展開更多」漸進式展開後，卡片內**不可以再有捲軸**。

斷言全部對著行為寫（不是「按鈕存在」這種存在性斷言）：
  ①展開後卡片內沒有內捲軸
  ②長文一開始被裁切，且有「展開更多」
  ③按一次之後可見高度確實變高
  ④一路按到底之後裁切解除、按鈕消失、內容完整露出
  ⑤圖片仍然自動顯示（這件事本來就好的，不能被改壞）

跑法（需先起站台）：
    <venv>/python scripts/preview_site.py --no-browser
    <playwright venv>/python tests/verify_reader_expand.py
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
        page = browser.new_page(viewport={"width": 390, "height": 844})   # iPhone
        page.goto(args.url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(1500)

        # 挑一篇夠長、而且有圖的省錢文
        target = page.evaluate("""() => {
          const rs = (DATA.money && DATA.money.results) || [];
          const hit = rs.find(r => (r.image_urls || []).length) || rs[0];
          return hit ? hit.url : null;
        }""")
        if not target:
            print("找不到可測的文章"); browser.close(); return 1

        opened = page.evaluate("""(u) => {
          for (const c of document.querySelectorAll('#items .card')) {
            const a = c.querySelector('a[href*="ptt.cc"]');
            if (a && a.href === u) { c.querySelector('button.toggle').click(); return true; }
          }
          return false;
        }""", target)
        chk("能展開文章", opened)
        page.wait_for_timeout(4000)

        st = page.evaluate("""() => {
          const pre = document.querySelector('#items .card.open .preview');
          const clip = pre && pre.querySelector('.art-clip');
          const more = pre && pre.querySelector('.art-more');
          const cs = pre ? getComputedStyle(pre) : null;
          return {
            有preview: !!pre,
            preview內捲: pre ? pre.scrollHeight > pre.clientHeight + 4 : null,
            overflowY: cs ? cs.overflowY : null,
            maxHeight: cs ? cs.maxHeight : null,
            有clip: !!clip,
            被裁切: clip ? clip.dataset.clipped === '1' : null,
            可見高: clip ? clip.clientHeight : null,
            完整高: clip ? clip.scrollHeight : null,
            有展開鈕: !!more,
            鈕文字: more ? more.textContent : '',
            圖片數: pre ? pre.querySelectorAll('img.art-img').length : 0,
            圖片壞掉: pre ? [...pre.querySelectorAll('img.art-img')]
                            .filter(i => i.complete && i.naturalWidth === 0).length : 0,
          };
        }""")
        for k, v in st.items():
            print(f"      {k}: {v}")

        chk("卡片內沒有內捲軸", st["preview內捲"] is False,
            f"overflow-y={st['overflowY']} max-height={st['maxHeight']}")
        chk("長文一開始被裁切", st["被裁切"] is True)
        chk("有展開更多按鈕", st["有展開鈕"], st["鈕文字"])
        if st["圖片數"]:
            # loading=lazy：畫面外的圖本來就還沒載，只能斷言「沒有壞掉的」
            chk("圖片沒有壞掉的", st["圖片壞掉"] == 0, f"壞 {st['圖片壞掉']}/{st['圖片數']}")

        before = st["可見高"] or 0
        page.click("#items .card.open .art-more")
        page.wait_for_timeout(600)
        after = page.evaluate(
            "() => { const c = document.querySelector('#items .card.open .art-clip');"
            " return c ? c.clientHeight : 0; }")
        chk("按一次之後高度變高", after > before, f"{before} -> {after}")

        for _ in range(30):
            if not page.query_selector("#items .card.open .art-more"):
                break
            page.click("#items .card.open .art-more")
            page.wait_for_timeout(220)
        end = page.evaluate("""() => {
          const pre = document.querySelector('#items .card.open .preview');
          const clip = pre.querySelector('.art-clip');
          return {
            still裁切: clip.dataset.clipped === '1',
            還有鈕: !!pre.querySelector('.art-more'),
            可見高: clip.clientHeight, 完整高: clip.scrollHeight,
            preview內捲: pre.scrollHeight > pre.clientHeight + 4,
          };
        }""")
        chk("全部展開後不再裁切", end["still裁切"] is False)
        chk("全部展開後按鈕消失", end["還有鈕"] is False)
        chk("全部展開後內容完整露出",
            abs(end["可見高"] - end["完整高"]) <= 4,
            f"{end['可見高']} vs {end['完整高']}")
        chk("全程都沒有出現內捲軸", end["preview內捲"] is False)

        if args.shot:
            page.screenshot(path=args.shot, full_page=False)
        browser.close()

    print("\n結果：" + ("全過" if not fails else f"{len(fails)} 項失敗 -> {fails}"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
