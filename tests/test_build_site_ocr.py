import unittest
from unittest.mock import patch

from scripts import build_site


class BuildSiteOcrTests(unittest.TestCase):
    def test_reuses_checked_ocr_and_reclassifies_from_image_text(self):
        result = {"url": "https://www.ptt.cc/bbs/Lifeismoney/M.1.A.AAA.html",
                  "title": "[情報] 今日活動", "preview": "原文", "cats": []}
        old = {"results": [{
            "url": result["url"], "ocr_checked": True,
            "image_urls": ["https://i.imgur.com/a.jpg"],
            "ocr_text": "全家會員買一送一",
        }]}
        with patch("scripts.build_site.tesseract_command", return_value="tesseract"):
            reused, processed, recognized = build_site.fill_image_ocr([result], old, {})
        self.assertEqual((reused, processed, recognized), (1, 0, 0))
        self.assertIn("全家會員買一送一", result["preview"])
        self.assertIn("四大超商", result["cats"])

    def test_reuses_old_ocr_without_local_tesseract_and_updates_reader(self):
        url = "https://www.ptt.cc/bbs/Lifeismoney/M.3.A.CCC.html"
        aid = build_site.article_id(url)
        result = {"url": url, "title": "[情報] 活動", "preview": "原文", "cats": []}
        old = {"results": [{
            "url": url, "ocr_checked": True,
            "image_urls": ["https://i.imgur.com/a.jpg"], "ocr_text": "全家 9/3 優惠",
        }]}
        articles = {aid: {"body": "文章與圖片網址", "comments": []}}
        with patch("scripts.build_site.tesseract_command", return_value=None):
            reused, processed, recognized = build_site.fill_image_ocr([result], old, articles)
        self.assertEqual((reused, processed, recognized), (1, 0, 0))
        self.assertIn("全家 9/3 優惠", result["preview"])
        self.assertIn("全家 9/3 優惠", articles[aid]["body"])

    def test_write_articles_cleans_carried_reader_ocr(self):
        url = "https://www.ptt.cc/bbs/Lifeismoney/M.4.A.DDD.html"
        item = {"url": url}
        package = {"body": build_site.append_ocr_block(
            "原文", "會員 限定\n2 1 20 0 0 0 219 509 254 78 -1"
        )}
        with patch("scripts.build_site.fetch_old_article", return_value=package):
            import tempfile
            from pathlib import Path
            with tempfile.TemporaryDirectory() as tmp:
                written, carried, fetched = build_site.write_articles(
                    Path(tmp), [item], {}, carry_cap=1, fetch_budget=0
                )
                body = next((Path(tmp) / "articles").glob("*.json")).read_text(encoding="utf-8")
        self.assertEqual((written, carried, fetched), (1, 1, 0))
        self.assertIn("會員限定", body)
        self.assertNotIn("219 509", body)

    def test_new_article_keeps_layout_ocr_in_preview_and_reader(self):
        url = "https://www.ptt.cc/bbs/Lifeismoney/M.2.A.BBB.html"
        result = {"url": url, "title": "[情報] 圖片活動", "preview": "原文", "cats": []}
        aid = build_site.article_id(url)
        articles = {aid: {"body": "https://i.imgur.com/deal.jpg", "comments": []}}
        outcome = {
            "checked": True, "image_urls": ["https://i.imgur.com/deal.jpg"],
            "text": "【圖片 1】\n商品 A 99 元\n9/3 會員限定", "errors": [],
        }
        with patch("scripts.build_site.tesseract_command", return_value="tesseract"), patch(
            "scripts.build_site.ocr_article_images", return_value=outcome
        ):
            reused, processed, recognized = build_site.fill_image_ocr([result], None, articles)
        self.assertEqual((reused, processed, recognized), (0, 1, 1))
        self.assertIn("商品 A 99 元\n9/3 會員限定", result["preview"])
        self.assertIn("商品 A 99 元\n9/3 會員限定", articles[aid]["body"])


if __name__ == "__main__":
    unittest.main()
