"""build_site 的圖片辨識沿用邏輯。

2026-09-04 換引擎（Tesseract → Gemini）後重寫。這裡最重要的是**引擎版本閘門**：
線上 money.json 裡有一批 Tesseract 時代的 ocr_text（實測 46% 是雜訊）。
如果照舊「checked 就沿用」，那批雜訊會永遠留在使用者眼前，換引擎等於白做。
"""
import unittest
from unittest.mock import patch

from image_ocr import OCR_ENGINE
from scripts import build_site

URL = "https://www.ptt.cc/bbs/Lifeismoney/M.1.A.AAA.html"


def _old(**kw):
    base = {"url": URL, "ocr_checked": True,
            "image_urls": ["https://i.imgur.com/a.jpg"], "ocr_text": "全家會員買一送一"}
    base.update(kw)
    return {"results": [base]}


class EngineGateTests(unittest.TestCase):
    """換引擎後，舊資料必須重讀而不是沿用。"""

    def test_same_engine_is_reused_without_calling_api(self):
        result = {"url": URL, "title": "[情報] 今日活動", "preview": "原文", "cats": []}
        with patch("scripts.build_site.gemini_client.available", return_value=True), \
             patch("scripts.build_site.ocr_article_images") as read:
            reused, processed, recognized = build_site.fill_image_ocr(
                [result], _old(ocr_engine=OCR_ENGINE), {})
        self.assertEqual((reused, processed, recognized), (1, 0, 0))
        read.assert_not_called()                       # 沿用就不該再花錢打 API
        self.assertIn("全家會員買一送一", result["preview"])
        self.assertEqual(result["ocr_engine"], OCR_ENGINE)
        self.assertIn("四大超商", result["cats"])       # 圖片文字要參與分類

    def test_legacy_tesseract_result_is_not_reused(self):
        """沒有 ocr_engine 欄位＝Tesseract 時代的資料，必須重讀。"""
        result = {"url": URL, "title": "[情報] 今日活動", "preview": "原文", "cats": []}
        articles = {build_site.article_id(URL): {"body": "文章內容", "comments": []}}
        with patch("scripts.build_site.gemini_client.available", return_value=True), \
             patch("scripts.build_site.ocr_article_images",
                   return_value={"checked": True, "image_urls": ["https://i.imgur.com/a.jpg"],
                                 "text": "全家 9/3 大杯拿鐵買一送一", "errors": [],
                                 "engine": OCR_ENGINE}) as read:
            reused, processed, recognized = build_site.fill_image_ocr(
                [result], _old(), articles)                # 刻意不給 ocr_engine
        self.assertEqual((reused, processed, recognized), (0, 1, 1))
        read.assert_called_once()
        self.assertIn("大杯拿鐵買一送一", result["preview"])
        self.assertNotIn("全家會員買一送一", result["preview"])   # 舊結果不該殘留
        self.assertEqual(result["ocr_engine"], OCR_ENGINE)

    def test_legacy_block_is_stripped_even_when_reread_is_skipped(self):
        """超出本輪額度／沒金鑰時也不能把上一代的亂碼留給使用者看。"""
        legacy_noise = ("優惠原文\n\n【圖片文字辨識（自動 OCR，請以原圖為準）】\n"
                        "2 1 20 0 0 0 219 509 254 78 -1\n看 影片 拿 點 數")
        aid = build_site.article_id(URL)
        result = {"url": URL, "title": "[情報] 活動", "preview": legacy_noise, "cats": []}
        articles = {aid: {"body": legacy_noise, "comments": []}}
        with patch("scripts.build_site.gemini_client.available", return_value=False):
            reused, processed, _ = build_site.fill_image_ocr([result], _old(), articles)
        self.assertEqual((reused, processed), (0, 0))
        self.assertNotIn("219 509", result["preview"])
        self.assertNotIn("看 影片 拿 點 數", result["preview"])
        self.assertNotIn("219 509", articles[aid]["body"])
        self.assertEqual(result["preview"], "優惠原文")

    def test_budget_limits_api_calls_per_round(self):
        """每輪有上限，否則一次補完 100 多篇會既慢又貴。"""
        results = [{"url": f"https://www.ptt.cc/bbs/Lifeismoney/M.{i}.A.X.html",
                    "title": "[情報]", "preview": "原文", "cats": []} for i in range(10)]
        with patch("scripts.build_site.gemini_client.available", return_value=True), \
             patch("scripts.build_site.article_package"), \
             patch("scripts.build_site.PTTClient"), \
             patch("scripts.build_site.ocr_article_images",
                   return_value={"checked": True, "image_urls": [], "text": "",
                                 "errors": [], "engine": OCR_ENGINE}) as read:
            _, processed, _ = build_site.fill_image_ocr(results, None, {}, budget=3)
        self.assertEqual(processed, 3)
        self.assertEqual(read.call_count, 3)


class ReaderSyncTests(unittest.TestCase):
    def test_reused_text_also_lands_in_reader_body(self):
        """摘要有、閱讀器沒有的話，點進去會看不到圖片內容。"""
        aid = build_site.article_id(URL)
        result = {"url": URL, "title": "[情報] 活動", "preview": "原文", "cats": []}
        articles = {aid: {"body": "文章與圖片網址", "comments": []}}
        with patch("scripts.build_site.gemini_client.available", return_value=True):
            build_site.fill_image_ocr([result], _old(ocr_engine=OCR_ENGINE), articles)
        self.assertIn("全家會員買一送一", result["preview"])
        self.assertIn("全家會員買一送一", articles[aid]["body"])

    def test_unchecked_result_stays_retryable(self):
        """暫時性失敗不能標 checked，否則這篇永遠不會再被讀。"""
        result = {"url": URL, "title": "[情報]", "preview": "原文", "cats": []}
        articles = {build_site.article_id(URL): {"body": "圖片", "comments": []}}
        with patch("scripts.build_site.gemini_client.available", return_value=True), \
             patch("scripts.build_site.ocr_article_images",
                   return_value={"checked": False, "image_urls": ["https://i.imgur.com/a.jpg"],
                                 "text": "", "errors": ["timeout"], "engine": OCR_ENGINE}):
            build_site.fill_image_ocr([result], None, articles)
        self.assertFalse(result["ocr_checked"])


if __name__ == "__main__":
    unittest.main()
