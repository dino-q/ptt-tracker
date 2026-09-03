#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OCR 收緊前後 A/B 對照報告（在 GitHub Actions 上跑，用正式環境的 tesseract）。

為什麼在 Actions 跑：正式 OCR 跑在 Ubuntu runner 的 tesseract + chi_tra 語言包上。
本機 Windows 裝另一版比出來的結果不代表線上，等於白比。

用法：
    python scripts/ocr_ab_compare.py --out out/ocr_ab
    python scripts/ocr_ab_compare.py --out out/ocr_ab --limit 6

輸出：
    <out>/report.html   人看的並排對照（自足單檔，可直接開）
    <out>/report.json   機器可讀的統計

⚠️ 評分口徑的坑（2026-09-04）：
    不要用 image_ocr._line_is_useful 來算新設定的「雜訊率」。那條規則就是收緊時
    用來砍字的依據，拿它當尺會讓新設定必然得到 0% 雜訊——量的是自己的規則，
    不是辨識品質。這裡只輸出「與過濾規則無關」的客觀統計（字數、中文字佔比、
    行數、Tesseract 自報平均信心），品質好壞請直接看並排全文。
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.request
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import image_ocr  # noqa: E402

LIVE_MONEY = "https://dino-q.github.io/ptt-tracker/data/money.json"

# 對照組：舊 = 線上目前的行為；新 = 本次收緊。中間兩檔給 Dino 看門檻的斜率。
VARIANTS: list[tuple[str, image_ocr.OcrTuning]] = [
    ("舊（線上現況）", image_ocr.OcrTuning(min_word_conf=15, drop_junk_lines=False,
                                     legacy_score=True)),
    ("只改計分", image_ocr.OcrTuning(min_word_conf=15, drop_junk_lines=False,
                                 legacy_score=False)),
    ("conf 50＋碎片過濾（建議）", image_ocr.OcrTuning()),
    ("conf 65＋碎片過濾（更嚴）", image_ocr.OcrTuning(min_word_conf=65.0)),
]

CJK = re.compile(r"[㐀-鿿]")


def objective_stats(text: str) -> dict:
    """與過濾規則無關的統計。刻意不呼叫 _line_is_useful，理由見模組 docstring。"""
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    chars = re.sub(r"\s", "", text or "")
    cjk = CJK.findall(text or "")
    return {
        "chars": len(chars),
        "lines": len(lines),
        "cjk_chars": len(cjk),
        "cjk_ratio": round(len(cjk) / len(chars), 3) if chars else 0.0,
        # 平均行長：雜訊多的輸出會出現大量 1-3 字的碎片行，這個數字會明顯偏低
        "avg_line_len": round(len(chars) / len(lines), 1) if lines else 0.0,
    }


def fetch_targets(limit: int) -> list[dict]:
    with urllib.request.urlopen(LIVE_MONEY, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    targets = []
    for item in data.get("results", []):
        urls = item.get("image_urls") or []
        if not urls:
            continue
        targets.append({"title": item.get("title", ""), "url": item.get("url", ""),
                        "image_urls": urls[:2],
                        "deployed_text": item.get("ocr_text") or ""})
        if len(targets) >= limit:
            break
    return targets


def run_one(image_urls: list[str], tuning: image_ocr.OcrTuning) -> tuple[str, list[str]]:
    blocks, errors = [], []
    for index, url in enumerate(image_urls, 1):
        try:
            text = image_ocr.ocr_image_url(url, tuning)
            if text:
                blocks.append(f"【圖片 {index}】\n{text}")
        except Exception as exc:                              # noqa: BLE001
            errors.append(f"{url}：{exc}")
    return "\n\n".join(blocks), errors


def build_html(report: dict) -> str:
    esc = html.escape
    names = [v["name"] for v in report["variants"]]
    head = "".join(f"<th>{esc(n)}</th>" for n in names)
    rows = []
    for art in report["articles"]:
        cells = []
        for name in names:
            r = art["results"][name]
            s = r["stats"]
            cells.append(
                "<td><div class='meta'>"
                f"{s['chars']} 字／{s['lines']} 行／中文 {int(s['cjk_ratio'] * 100)}%"
                f"／平均行長 {s['avg_line_len']}</div>"
                f"<pre>{esc(r['text']) or '<span class=empty>（空）</span>'}</pre></td>")
        rows.append(
            f"<tr><th class='rowhead'><a href='{esc(art['url'])}'>{esc(art['title'])}</a>"
            f"<div class='meta'>{len(art['image_urls'])} 張圖</div></th>"
            + "".join(cells) + "</tr>")
    summary = "".join(
        f"<tr><td>{esc(v['name'])}</td><td>{v['total_chars']}</td>"
        f"<td>{v['total_lines']}</td><td>{int(v['cjk_ratio'] * 100)}%</td>"
        f"<td>{v['avg_line_len']}</td></tr>"
        for v in report["variants"])
    return f"""<!doctype html><meta charset="utf-8">
<title>OCR 收緊 A/B 對照</title>
<style>
 body{{font:14px/1.6 system-ui,"Noto Sans TC",sans-serif;margin:24px;color:#1a1a1a;background:#fafafa}}
 h1{{font-size:1.3rem}} table{{border-collapse:collapse;width:100%;margin-bottom:28px}}
 th,td{{border:1px solid #ddd;padding:8px;vertical-align:top;text-align:left}}
 th{{background:#f0f0f0}} .rowhead{{width:180px;font-weight:600}}
 pre{{white-space:pre-wrap;word-break:break-word;font:12px/1.5 ui-monospace,monospace;
      max-height:420px;overflow:auto;margin:0;background:#fff;padding:8px;border-radius:4px}}
 .meta{{font-size:11px;color:#666;margin-bottom:4px}} .empty{{color:#999}}
 .note{{background:#fff8e1;border-left:3px solid #f0b400;padding:10px 14px;margin-bottom:20px}}
</style>
<h1>OCR 收緊 A/B 對照</h1>
<div class="note">
 <b>怎麼看：</b>「舊（線上現況）」是目前線上跑的設定，右邊三欄是收緊後的效果。<br>
 <b>評分口徑：</b>表格裡只放與過濾規則無關的客觀統計。刻意<b>不</b>用收緊時砍字的那條規則
 去算「雜訊率」——拿自己的規則當尺，新設定必然得到 0% 雜訊，那個數字沒有意義。
 品質請直接看並排全文。<br>
 <b>「平均行長」怎麼用：</b>雜訊多的輸出會有一堆 1-3 字的碎片行，這個數字會明顯偏低。
</div>
<h2>整體</h2>
<table><tr><th>設定</th><th>總字數</th><th>總行數</th><th>中文佔比</th><th>平均行長</th></tr>
{summary}</table>
<h2>逐篇並排</h2>
<table><tr><th class="rowhead">文章</th>{head}</tr>{"".join(rows)}</table>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out/ocr_ab")
    ap.add_argument("--limit", type=int, default=6)
    args = ap.parse_args()

    if not image_ocr.tesseract_command():
        print("找不到 Tesseract：這支要在有安裝 tesseract 的環境跑（見 .github/workflows/ocr-ab.yml）",
              file=sys.stderr)
        return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    targets = fetch_targets(args.limit)
    print(f"取到 {len(targets)} 篇有圖的文章")

    articles = []
    for i, target in enumerate(targets, 1):
        print(f"[{i}/{len(targets)}] {target['title'][:40]}")
        results = {}
        for name, tuning in VARIANTS:
            text, errors = run_one(target["image_urls"], tuning)
            results[name] = {"text": text, "errors": errors,
                             "stats": objective_stats(text),
                             "tuning": asdict(tuning)}
            print(f"    {name}: {results[name]['stats']}")
        articles.append({**target, "results": results})

    variants = []
    for name, _ in VARIANTS:
        texts = [a["results"][name]["text"] for a in articles]
        merged = objective_stats("\n".join(texts))
        variants.append({"name": name, "total_chars": merged["chars"],
                         "total_lines": merged["lines"],
                         "cjk_ratio": merged["cjk_ratio"],
                         "avg_line_len": merged["avg_line_len"]})

    report = {"variants": variants, "articles": articles}
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
    (out / "report.html").write_text(build_html(report), encoding="utf-8")
    print(f"\n報告：{out / 'report.html'}")
    for v in variants:
        print(f"  {v['name']}: {v['total_chars']} 字／{v['total_lines']} 行／"
              f"中文 {int(v['cjk_ratio'] * 100)}%／平均行長 {v['avg_line_len']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
