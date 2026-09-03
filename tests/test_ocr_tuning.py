#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OCR 收緊參數（OcrTuning）的回歸測試。

背景：2026-09-04 量到線上省錢板 OCR 雜訊率 46%（最差一篇 73%），
Dino 反映「效果差到不行」。收緊分兩處——
  ① 字級信心門檻 15 → 50（海報裝飾字/logo 在 15-40 幾乎全是噪音）
  ② 雙 PSM 擇優計分：舊式 `字數 × 平均信心` 讓「字多但髒」的那版系統性勝出

這幾條守的是「收緊沒有矯枉過正」，特別是高信心數字列不可以被砍。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import image_ocr  # noqa: E402

TAB = chr(9)
NL = chr(10)
COLUMNS = ("level page_num block_num par_num line_num word_num "
           "left top width height conf text").split()


def tsv(rows: list[list]) -> str:
    """把列組成 Tesseract TSV 文字（欄位順序固定，見 COLUMNS）。"""
    head = TAB.join(COLUMNS)
    body = NL.join(TAB.join(str(cell) for cell in row) for row in rows)
    return head + NL + body + NL


TIGHT = image_ocr.TIGHTENED_TUNING
LOOSE = image_ocr.OcrTuning(min_word_conf=15, drop_junk_lines=False)
LEGACY = image_ocr.OcrTuning(min_word_conf=15, drop_junk_lines=False, legacy_score=True)


class LineUsefulnessTests(unittest.TestCase):
    def test_obvious_noise_is_not_useful(self):
        for fragment in ("Qrx", "et", "==", "n+ 2", "SS", "mw", "當"):
            self.assertFalse(image_ocr._line_is_useful(fragment), fragment)

    def test_real_content_is_useful(self):
        for line in ("原價 49 元", "9/3 限定", "百吉", "買 2 送 2",
                     "eclipse", "$650", "10:03"):
            self.assertTrue(image_ocr._line_is_useful(line), line)


class TsvTuningTests(unittest.TestCase):
    def test_low_confidence_fragment_is_dropped(self):
        """海報裝飾字（信心低、無中文無數量詞）不該進結果。"""
        rows = [
            [5, 1, 1, 1, 1, 1, 20, 10, 40, 20, 92, "買一送一"],
            [5, 1, 1, 1, 2, 1, 20, 40, 30, 20, 28, "Qrx"],
        ]
        text, _ = image_ocr._layout_text_from_tsv(tsv(rows), TIGHT)
        self.assertIn("買一送一", text)
        self.assertNotIn("Qrx", text)

    def test_high_confidence_numeric_line_is_kept(self):
        """⚠️ 高信心的純數字列是真的優惠序號，不可以因為「看起來像亂碼」被砍。

        對應 2026-09-03 Angus 抓到的過度刪除（當時是用「11 個數字」當規則）。
        junk_conf_ceiling 就是為了擋這種誤刪而存在，改參數前先想清楚。
        """
        rows = [[5, 1, 1, 1, 1, i + 1, 20 + i * 30, 10, 25, 20, 93, str(n)]
                for i, n in enumerate(range(1, 12))]
        text, _ = image_ocr._layout_text_from_tsv(tsv(rows), TIGHT)
        self.assertIn("1 2 3 4 5 6 7 8 9 10 11", text)

    def test_min_word_conf_is_tunable(self):
        """A/B 要能用同一份 pipeline 跑舊設定，而不是複製一套實作出去改。"""
        rows = [[5, 1, 1, 1, 1, 1, 20, 10, 60, 20, 30, "限時優惠"]]
        strict, _ = image_ocr._layout_text_from_tsv(tsv(rows), TIGHT)
        loose, _ = image_ocr._layout_text_from_tsv(tsv(rows), LOOSE)
        self.assertEqual(strict, "")
        self.assertIn("限時優惠", loose)

    def test_new_score_prefers_clean_over_noisy(self):
        """舊計分讓「字多但髒」勝出，新計分要反過來——這是雙 PSM 選錯版的根因。"""
        clean = [[5, 1, 1, 1, 1, 1, 20, 10, 60, 20, 88, "全家買一送一"]]
        noisy = [[5, 1, 1, 1, i + 1, 1, 20, 10 + i * 30, 60, 20, 52, word]
                 for i, word in enumerate(
                     ["超值優惠活動", "限定商品清單", "會員專屬價格",
                      "指定門市適用", "數量有限售完", "詳情見官網"])]
        _, clean_new = image_ocr._layout_text_from_tsv(tsv(clean), LOOSE)
        _, noisy_new = image_ocr._layout_text_from_tsv(tsv(noisy), LOOSE)
        _, clean_old = image_ocr._layout_text_from_tsv(tsv(clean), LEGACY)
        _, noisy_old = image_ocr._layout_text_from_tsv(tsv(noisy), LEGACY)
        self.assertGreater(noisy_old, clean_old)   # 舊行為：字多的贏（這就是問題本身）
        self.assertGreater(clean_new, noisy_new)   # 新行為：信心高的贏

    def test_clean_ocr_text_untouched_by_junk_filter(self):
        """已部署文字的清理走 clean_ocr_text，不吃碎片過濾——否則會回頭誤刪舊資料。"""
        self.assertEqual(
            image_ocr.clean_ocr_text("1 2 3 4 5 6 7 8 9 10 11"),
            "1 2 3 4 5 6 7 8 9 10 11",
        )


if __name__ == "__main__":
    unittest.main()
