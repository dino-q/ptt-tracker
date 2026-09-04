"""image_ocr 單元測試。

2026-09-04 換引擎（Tesseract → Gemini）後重寫。網址擷取、白名單、SSRF 防護、
下載限制那一層跟引擎無關，測試原樣保留；引擎相關的改測新行為。
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import image_ocr


class ImageUrlTests(unittest.TestCase):
    """擷取與下載層——這層跟用哪個引擎無關，換引擎不該動到它。"""

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
        """重點是「跟 redirect 之前就先驗」——等 requests 跟完才檢查，SSRF 已經發生了。"""
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


    def test_no_referer_header_imgur_blocks_hotlinking(self):
        """⚠️ 迴歸守門：帶 Referer 時 i.imgur.com 一律回 403（防盜連），
        而 imgur 是 PTT 最常用的圖床。2026-09-04 實測 11 張圖 0 成功，拿掉後 11/11。
        有人日後「順手補個 Referer 比較像瀏覽器」就會再把它弄壞。"""
        self.assertNotIn("Referer", image_ocr._REQUEST_HEADERS)
        self.assertNotIn("referer", {k.lower() for k in image_ocr._REQUEST_HEADERS})

        seen = {}

        class Resp:
            is_redirect = is_permanent_redirect = False
            headers = {"Content-Type": "image/png", "Content-Length": "4"}

            def raise_for_status(self):
                pass

            def iter_content(self, n):
                return [b"fake-image-bytes"]

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        class Client:
            def get(self, url, **kw):
                seen.update(kw.get("headers") or {})
                return Resp()

        with tempfile.TemporaryDirectory() as tmp,              patch("image_ocr._is_public_url", return_value=True):
            image_ocr._download_image("https://i.imgur.com/a.png",
                                      Path(tmp) / "a.png", session=Client())
        self.assertNotIn("Referer", seen)
        self.assertIn("User-Agent", seen)


class MimeSniffTests(unittest.TestCase):
    def test_sniffs_by_magic_bytes_not_extension(self):
        """副檔名是 PTT 文章作者寫的，不能信；型別要靠檔頭判。"""
        self.assertEqual(image_ocr._sniff_mime(b"\x89PNG\r\n\x1a\n....."), "image/png")
        self.assertEqual(image_ocr._sniff_mime(b"\xff\xd8\xff\xe0...."), "image/jpeg")
        self.assertEqual(image_ocr._sniff_mime(b"RIFF\x00\x00\x00\x00WEBPVP8 "), "image/webp")
        self.assertEqual(image_ocr._sniff_mime(b"GIF89a..."), "image/gif")


class TextBlockTests(unittest.TestCase):
    def test_clean_collapses_whitespace_and_caps_length(self):
        self.assertEqual(image_ocr.clean_ocr_text("  拿鐵   買一送一 \n\n\n  期間 9/1 "),
                         "拿鐵 買一送一\n期間 9/1")
        long = "字" * 5000
        out = image_ocr.clean_ocr_text(long, max_chars=100)
        self.assertEqual(len(out), 101)          # 100 字 + 省略號
        self.assertTrue(out.endswith("…"))

    def test_append_ocr_block_is_idempotent(self):
        first = image_ocr.append_ocr_block("原文", "拿鐵買一送一")
        second = image_ocr.append_ocr_block(first, "拿鐵買一送一")
        self.assertEqual(first, second)
        self.assertEqual(first.count(image_ocr.MARKER), 1)

    def test_append_empty_removes_existing_block(self):
        with_block = image_ocr.append_ocr_block("原文", "舊結果")
        self.assertEqual(image_ocr.append_ocr_block(with_block, ""), "原文")

    def test_strip_removes_legacy_tesseract_block(self):
        """換引擎的關鍵：舊版標題也要認得，否則 Tesseract 亂碼會留在線上資料裡。"""
        legacy = ("優惠原文\n\n【圖片文字辨識（自動 OCR，請以原圖為準）】\n"
                  "2 1 20 0 0 0 219 509 254 78 -1\n看 影片 拿 點 數")
        self.assertEqual(image_ocr.strip_ocr_block(legacy), "優惠原文")

    def test_strip_removes_current_block(self):
        cur = image_ocr.append_ocr_block("優惠原文", "拿鐵買一送一")
        self.assertEqual(image_ocr.strip_ocr_block(cur), "優惠原文")


class ArticleReadTests(unittest.TestCase):
    def test_no_images_is_checked_and_costs_nothing(self):
        """沒有圖片就不該打 API——這是每小時排程，白打錢就白花了。"""
        with patch("image_ocr.gemini_client.available", return_value=True) as avail, \
             patch("image_ocr.read_image_url") as read:
            out = image_ocr.ocr_article_images("純文字文章，沒有任何圖片連結")
        self.assertTrue(out["checked"])
        self.assertEqual(out["image_urls"], [])
        self.assertEqual(out["engine"], image_ocr.OCR_ENGINE)
        read.assert_not_called()
        avail.assert_not_called()

    def test_unavailable_gemini_stays_unchecked_for_retry(self):
        """沒金鑰不能標 checked，否則這篇會被永久當成「讀過了、沒東西」。"""
        body = "https://i.imgur.com/a.jpg"
        with patch("image_ocr.gemini_client.available", return_value=False):
            out = image_ocr.ocr_article_images(body)
        self.assertFalse(out["checked"])
        self.assertEqual(out["image_urls"], ["https://i.imgur.com/a.jpg"])
        self.assertEqual(out["text"], "")

    def test_partial_failure_keeps_good_result_but_stays_retryable(self):
        body = "https://i.imgur.com/a.jpg https://i.ibb.co/b.png"
        with patch("image_ocr.gemini_client.available", return_value=True), \
             patch("image_ocr.read_image_url",
                   side_effect=["拿鐵買一送一", RuntimeError("timeout")]):
            out = image_ocr.ocr_article_images(body)
        self.assertIn("拿鐵買一送一", out["text"])
        self.assertIn("【圖片 1】", out["text"])
        # 有一張失敗 → 不標 checked，下一輪整篇重讀
        self.assertFalse(out["checked"])
        self.assertEqual(len(out["errors"]), 1)

    def test_all_success_is_checked(self):
        body = "https://i.imgur.com/a.jpg"
        with patch("image_ocr.gemini_client.available", return_value=True), \
             patch("image_ocr.read_image_url", return_value="全家 9/3 買一送一"):
            out = image_ocr.ocr_article_images(body)
        self.assertTrue(out["checked"])
        self.assertEqual(out["engine"], image_ocr.OCR_ENGINE)


class ReadImageUrlTests(unittest.TestCase):
    def _fake_download(self, data):
        def _dl(url, path, session=None):
            Path(path).write_bytes(data)
        return _dl

    def test_no_content_answer_becomes_empty_string(self):
        """模型說「無相關資訊」時不能把這四個字塞進使用者的優惠摘要。"""
        class Resp:
            text = "無相關資訊"
        with patch("image_ocr._download_image", self._fake_download(b"\x89PNG\r\n\x1a\n")), \
             patch("image_ocr.gemini_client.parts") as parts, \
             patch("image_ocr.gemini_client.generate", return_value=Resp()):
            parts.return_value.Part.from_bytes.return_value = object()
            parts.return_value.Part.from_text.return_value = object()
            self.assertEqual(image_ocr.read_image_url("https://i.imgur.com/a.jpg"), "")

    def test_gemini_unavailable_raises_so_caller_can_retry(self):
        with patch("image_ocr._download_image", self._fake_download(b"\x89PNG\r\n\x1a\n")), \
             patch("image_ocr.gemini_client.parts"), \
             patch("image_ocr.gemini_client.generate", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "Gemini 不可用"):
                image_ocr.read_image_url("https://i.imgur.com/a.jpg")

    def test_passes_sniffed_mime_not_extension(self):
        """網址寫 .jpg 但內容是 PNG → 要送 image/png。"""
        class Resp:
            text = "拿鐵買一送一"
        with patch("image_ocr._download_image", self._fake_download(b"\x89PNG\r\n\x1a\nrest")), \
             patch("image_ocr.gemini_client.parts") as parts, \
             patch("image_ocr.gemini_client.generate", return_value=Resp()):
            image_ocr.read_image_url("https://i.imgur.com/a.jpg")
        kwargs = parts.return_value.Part.from_bytes.call_args.kwargs
        self.assertEqual(kwargs["mime_type"], "image/png")


if __name__ == "__main__":
    unittest.main()
