#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""咖啡區塊「已結束檔期」驗收（真實瀏覽器）。

守什麼（2026-09-04）：
  同一篇咖啡優惠文常一次列好幾波檔期，其中有些今天已經結束了。
  ①「活動期間：」的總範圍不可以被過期檔期拉開
    （實際踩到：8/10～9/1 的過期活動把總範圍變成「8/10～9/29」，
     看起來像這波優惠三週前就開始了）
  ② 過期的區塊要標「已結束」，而且排在同一家的後面
  ③ 捷徑上的數字只能算還領得到的筆數

斷言全部對著行為寫，而且**餵可控的假資料**：真站台的資料每天在變，
拿它當基準的話今天過、明天就無故紅燈。
"""
import argparse
import json
import sys

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

from playwright.sync_api import sync_playwright

DEFAULT_URL = "http://127.0.0.1:8879/"

# 相對「今天」造資料，測試才不會過幾天自己爛掉
FIXTURE_JS = """(() => {
  const d = new Date();
  const md = n => {
    const x = new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
    return `${x.getMonth() + 1}月${x.getDate()}日`;
  };
  COFFEE = {
    updated_at: "2026-01-01 00:00",
    article: {title: "測試", url: "https://example.com/", source: "測試來源"},
    活動期間: "",
    通路: [
      {名稱: "甲超商", 管道: "門市",
       期間: `${md(-30)}至${md(-3)}`,          // 已結束
       優惠: [{品項: "過期A", 說明: "買一送一"}, {品項: "過期B", 說明: "買一送一"}]},
      {名稱: "甲超商", 管道: "APP",
       期間: `${md(-1)}至${md(6)}`,            // 進行中
       優惠: [{品項: "現行A", 說明: "第二杯半價"}]},
      {名稱: "乙超商", 管道: "LINE禮物",
       期間: `${md(0)}至${md(2)}`,             // 今天是最後一天＝仍有效
       優惠: [{品項: "現行B", 說明: "寄杯"}]}
    ]
  };
  renderCoffee();
  const box = document.getElementById("coffee");
  if (box) box.dataset.collapsed = "0";
  return {起: md(-30), 訖: md(6)};
})()"""


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
        page = browser.new_context(viewport={"width": 900, "height": 1000}).new_page()
        page.goto(args.url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(1500)

        page.evaluate(FIXTURE_JS)
        page.wait_for_timeout(400)

        got = page.evaluate("""() => {
          const box = document.getElementById("coffee");
          return {
            期間: (box.querySelector(".coffee-period") || {}).textContent || "",
            捷徑: [...box.querySelectorAll(".coffee-jump button")]
                    .map(b => ({字: b.textContent, 灰: b.classList.contains("jump-dead")})),
            區塊: [...box.querySelectorAll(".coffee-ch")].map(sec => ({
              家: sec.querySelector("h3").firstChild.textContent,
              塊: [...sec.querySelectorAll(".coffee-block")].map(b => ({
                過期: b.classList.contains("blk-expired"),
                標: !!b.querySelector(".blk-over"),
                頭: (b.querySelector(".blk-head") || {}).textContent || "",
              })),
            })),
            過期品項顏色: (() => {
              const el = document.querySelector(".blk-expired .d-item");
              return el ? getComputedStyle(el).opacity : null;
            })(),
          };
        }""")
        print("      " + json.dumps(got, ensure_ascii=False)[:400])

        # ① 總期間不含過期檔期
        chk("總期間有顯示", "活動期間" in got["期間"], got["期間"])
        m = page.evaluate("() => {"
                          "const t=new Date();"
                          "const a=new Date(t.getFullYear(),t.getMonth(),t.getDate()-30);"
                          "return `${a.getMonth()+1}/${a.getDate()}`;}")
        chk("總期間不是從已結束那波算起", m not in got["期間"],
            f"不該出現 {m}｜實際 {got['期間']}")

        # ② 過期標記與排序
        jia = next((s for s in got["區塊"] if s["家"] == "甲超商"), None)
        chk("甲超商有兩塊", jia is not None and len(jia["塊"]) == 2)
        if jia and len(jia["塊"]) == 2:
            chk("進行中的排在前面", jia["塊"][0]["過期"] is False, jia["塊"][0]["頭"])
            chk("已結束的排在後面", jia["塊"][1]["過期"] is True, jia["塊"][1]["頭"])
            chk("已結束的有「已結束」標籤", jia["塊"][1]["標"] is True)
            chk("進行中的沒有「已結束」標籤", jia["塊"][0]["標"] is False)

        yi = next((s for s in got["區塊"] if s["家"] == "乙超商"), None)
        chk("今天到期仍算有效（不標已結束）",
            yi is not None and yi["塊"] and yi["塊"][0]["過期"] is False)

        # ③ 捷徑數字只算有效的：甲超商 3 筆裡只有 1 筆還在
        jb = next((b for b in got["捷徑"] if b["字"].startswith("甲超商")), None)
        chk("捷徑數字只算還領得到的", jb is not None and jb["字"].strip() == "甲超商 1",
            jb["字"] if jb else "找不到")
        chk("甲超商還有有效檔期，不該打灰", jb is not None and jb["灰"] is False)

        # 壓灰不可以用 opacity（會連帶壓掉對比度）
        chk("過期樣式不是用 opacity 壓的",
            got["過期品項顏色"] in (None, "1"), str(got["過期品項顏色"]))

        # 全部過期時要退回顯示全範圍，不能整行消失
        page.evaluate("""() => {
          const d = new Date();
          const md = n => { const x = new Date(d.getFullYear(), d.getMonth(), d.getDate()+n);
                            return `${x.getMonth()+1}月${x.getDate()}日`; };
          COFFEE.通路 = [{名稱:"甲", 管道:"門市", 期間:`${md(-20)}至${md(-5)}`,
                        優惠:[{品項:"x", 說明:"y"}]}];
          renderCoffee();
        }""")
        page.wait_for_timeout(300)
        allover = page.evaluate(
            "() => (document.querySelector('#coffee .coffee-period')||{}).textContent || ''")
        chk("全部過期時仍顯示期間（不留空白）", "活動期間" in allover, allover)

        browser.close()

    print("\n結果：" + ("全過" if not fails else f"{len(fails)} 項失敗 -> {fails}"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
