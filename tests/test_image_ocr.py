import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

import image_ocr
from PIL import Image


class ImageOcrTests(unittest.TestCase):
    def test_extracts_direct_images_and_normalizes_imgur_page(self):
        body = """文字 https://i.ibb.co/deal.png?x=1
        https://imgur.com/AbC123 不是圖 https://example.com/page
        重複 https://i.ibb.co/deal.png?x=1"""
        self.assertEqual(image_ocr.extract_image_urls(body), [
            "https://i.ibb.co/deal.png?x=1",
            "https://i.imgur.com/AbC123.jpg",
        ])
        self.assertEqual(image_ocr.extract_image_urls(body, max_images=0), [])
        self.assertEqual(image_ocr.extract_image_urls("https://attacker.example/deal.png"), [])

    def test_rejects_private_network_target(self):
        fake = [(None, None, None, None, ("127.0.0.1", 443))]
        with patch("image_ocr.socket.getaddrinfo", return_value=fake):
            self.assertFalse(image_ocr._is_public_url("https://localhost/a.png"))

    def test_redirect_is_validated_before_second_request(self):
        class RedirectResponse:
            is_redirect = True
            is_permanent_redirect = False
            headers = {"Location": "http://127.0.0.1/secret.png"}

            def close(self):
                pass

        class Client:
            def __init__(self):
                self.calls = 0

            def get(self, *args, **kwargs):
                self.calls += 1
                return RedirectResponse()

        client = Client()
        with tempfile.TemporaryDirectory() as tmp, patch(
            "image_ocr._is_public_url", side_effect=[True, False]
        ):
            with self.assertRaisesRegex(ValueError, "不是公開網路位址"):
                image_ocr._download_image(
                    "https://public.test/a.png", Path(tmp) / "a.png", session=client
                )
        self.assertEqual(client.calls, 1)

    def test_clean_ocr_drops_noise(self):
        self.assertEqual(image_ocr.clean_ocr_text("| . - _"), "")
        self.assertEqual(image_ocr.clean_ocr_text("  買一送一  \n  9/3 限定 "), "買一送一\n9/3 限定")

    def test_clean_ocr_removes_leaked_tsv_rows_and_cjk_word_spaces(self):
        dirty = """看 影片 拿 點 數
2 1 20 0 0 0 219 509 254 78 -1
5 1 20 1 1 1 219 513 204 74 12.969475 BEREEE
會員 限定 $500"""
        self.assertEqual(image_ocr.clean_ocr_text(dirty), "看影片拿點數\n會員限定 $500")
        self.assertEqual(
            image_ocr.clean_ocr_text("1 2 3 4 5 6 7 8 9 10 11"),
            "1 2 3 4 5 6 7 8 9 10 11",
        )

    def test_article_ocr_keeps_partial_success_retryable(self):
        with patch("image_ocr.tesseract_command", return_value="tesseract"), patch(
            "image_ocr.ocr_image_url", side_effect=["優惠 99 元", RuntimeError("逾時")]
        ):
            got = image_ocr.ocr_article_images(
                "https://i.ibb.co/a.jpg https://i.ibb.co/b.png", max_images=2
            )
        self.assertFalse(got["checked"])
        self.assertIn("優惠 99 元", got["text"])
        self.assertEqual(len(got["errors"]), 1)

    def test_append_ocr_block_is_idempotent(self):
        once = image_ocr.append_ocr_block("原文", "優惠內容")
        self.assertEqual(image_ocr.append_ocr_block(once, "優惠內容"), once)
        replaced = image_ocr.append_ocr_block(once, "更新後優惠")
        self.assertNotIn("優惠內容", replaced)
        self.assertIn("更新後優惠", replaced)

    def test_normalize_existing_block_cleans_already_deployed_text(self):
        dirty = image_ocr.append_ocr_block(
            "原文", "看 影片 拿 點 數\n2 1 20 0 0 0 219 509 254 78 -1"
        )
        got = image_ocr.normalize_existing_ocr_block(dirty)
        self.assertIn("看影片拿點數", got)
        self.assertNotIn("219 509", got)

    def test_tsv_layout_preserves_lines_and_blocks(self):
        tsv = """level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext
5\t1\t1\t1\t1\t1\t20\t10\t40\t20\t95\t全家
5\t1\t1\t1\t1\t2\t70\t10\t80\t20\t93\t買一送一
5\t1\t1\t1\t2\t1\t20\t40\t90\t20\t91\t9/3限定
5\t1\t2\t1\t1\t1\t250\t15\t80\t20\t90\t會員限定
"""
        text, score = image_ocr._layout_text_from_tsv(tsv)
        self.assertEqual(text, "全家買一送一\n9/3限定\n\n會員限定")
        self.assertGreater(score, 0)

    def test_prepare_image_upscales_small_poster(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.png"
            target = Path(tmp) / "prepared.png"
            Image.new("RGB", (400, 800), "white").save(source)
            got = image_ocr._prepare_image(source, target)
            with Image.open(got) as prepared:
                self.assertEqual(prepared.mode, "L")
                self.assertGreaterEqual(max(prepared.size), 2200)

    def test_one_layout_mode_failure_does_not_discard_other_mode(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "image_ocr.tesseract_command", return_value="tesseract"
        ), patch("image_ocr._download_image"), patch(
            "image_ocr._prepare_image", side_effect=lambda source, target: source
        ), patch(
            "image_ocr._run_layout_ocr",
            side_effect=[RuntimeError("psm11 failed"), ("會員價 99 元", 100)],
        ):
            got = image_ocr.ocr_image_url("https://public.test/deal.png")
        self.assertEqual(got, "會員價 99 元")


if __name__ == "__main__":
    unittest.main()
