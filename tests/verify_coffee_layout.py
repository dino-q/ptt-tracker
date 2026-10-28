"""真實 Chromium：咖啡長條件、手機／桌機／大字級邊界與共同欄位對齊。"""
from pathlib import Path
import argparse
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://127.0.0.1:8879/')
args = parser.parse_args()
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto(args.url, wait_until="networkidle")
    page.wait_for_function("COFFEE && COFFEE.通路.length > 0")
    page.evaluate("""() => {
      // 以真實星巴克長條件，加上 85 度 C 長品項測試同一份共用排版。
      COFFEE.通路.push({名稱:'85度C', 管道:'門市', 期間:'10月31日', 優惠:[{
        品項:'大杯咖啡系列（美式咖啡／招牌咖啡／拿鐵咖啡）',
        說明:'第二杯4折，限同品項、同容量、冰熱一致，每人每次至多購買兩組',
        原價:'依門市標示價格', 優惠價:'第二杯優惠價依所選品項計算'}]});
      renderCoffee(); setCoffeeCollapsed(false);
      document.getElementById('coffee').dataset.collapsed='0';
    }""")
    for width, height, font in [(320, 740, 16), (375, 812, 16), (390, 844, 16),
                                 (844, 390, 16), (1280, 900, 16), (375, 812, 24)]:
        page.set_viewport_size({"width": width, "height": height})
        page.evaluate("size => document.documentElement.style.fontSize=size+'px'", font)
        result = page.evaluate("""() => {
          const box = document.getElementById('coffee');
          const edge = box.getBoundingClientRect();
          const nodes = [...box.querySelectorAll('.coffee-deal, .coffee-deal > span, .blk-head')];
          const overflow = nodes.filter(n => {
            const r=n.getBoundingClientRect();
            return r.left < edge.left-1 || r.right > edge.right+1 || n.scrollWidth>n.clientWidth+1;
          }).map(n=>n.className);
          const rows=[...box.querySelectorAll('.coffee-deal')];
          const starts=rows.map(r=>r.querySelector('.d-item').getBoundingClientRect().left);
          const columns=['d-item','d-rule','d-price'].map(c => rows.map(r=>r.querySelector('.'+c))
            .filter(Boolean).map(n=>n.getBoundingClientRect().left));
          return {overflow, aligned: columns.every(xs=>Math.max(...xs)-Math.min(...xs)<1),
                  left:Math.max(...starts)-Math.min(...starts),
                  pageOverflow:document.documentElement.scrollWidth>innerWidth};
        }""")
        assert not result["overflow"] and not result["pageOverflow"], (width, font, result)
        assert result["aligned"] and result["left"] < 1, (width, font, result)
        print(f"PASS {width}x{height}, font={font}: no overflow; all channels aligned")
        if width in (390, 1280) and font == 16:
            page.screenshot(path=str(ROOT / "output" / f"coffee-layout-{width}.png"))
            page.locator('.coffee-ch').first.screenshot(path=str(ROOT / "output" / f"coffee-brand-{width}.png"))
    browser.close()
