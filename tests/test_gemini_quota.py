"""Gemini 額度處理的迴歸測試（2026-09-04）。

背景：這把金鑰是免費層，**每個模型每天只有 20 次**呼叫
（`429 RESOURCE_EXHAUSTED … GenerateRequestsPerDayPerProjectPerModel-FreeTier`）。

「每日額度用完」跟「尖峰塞車」長得很像（都是 429 / RESOURCE_EXHAUSTED），
但處理方式必須相反：
  · 尖峰塞車 → 等一下重試，多半會好
  · 每日額度 → 同一輪內**不可能**恢復，重試只是把時間與剩餘額度一起燒掉

實測過的代價：額度耗盡那一輪，2 篇文章 4 張圖打了 16 次全部 429。
"""
import unittest
from unittest.mock import patch

import gemini_client
from image_ocr import OCR_ENGINE
from scripts import build_site

DAILY = ("429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your "
         "current quota', 'details': [{'quotaId': "
         "'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaValue': '20'}]}}")
BUSY = "503 UNAVAILABLE. The model is overloaded. Please try again later."
PER_MINUTE = "429 RESOURCE_EXHAUSTED quotaId: 'GenerateRequestsPerMinutePerProject'"


class DailyQuotaDetectionTests(unittest.TestCase):
    def test_recognises_daily_quota(self):
        self.assertTrue(gemini_client.is_daily_quota_error(DAILY))

    def test_does_not_confuse_transient_overload_with_daily_quota(self):
        """尖峰塞車要照常重試——誤判成每日額度會讓功能在該重試時放棄。"""
        self.assertFalse(gemini_client.is_daily_quota_error(BUSY))

    def test_per_minute_limit_is_still_retryable(self):
        """每分鐘限流等幾秒就好，不該當成每日額度。"""
        self.assertFalse(gemini_client.is_daily_quota_error(PER_MINUTE))

    def test_empty_and_unrelated_messages(self):
        for msg in ("", None, "ValueError: bad image"):
            self.assertFalse(gemini_client.is_daily_quota_error(msg))


class RetryBehaviourTests(unittest.TestCase):
    """斷言呼叫次數，不是斷言「有沒有回錯誤」——重點在於**別再打**。"""

    def _run(self, error_message, attempts=3):
        calls = []

        class FakeModels:
            def generate_content(self, *, model, contents, config):
                calls.append(model)
                raise RuntimeError(error_message)

        class FakeClient:
            def __init__(self, **kw):
                self.models = FakeModels()

        fake_genai = type("m", (), {"Client": FakeClient})
        fake_types = type("t", (), {"HttpOptions": lambda **kw: None})

        with patch.dict("sys.modules", {"google": type("g", (), {"genai": fake_genai}),
                                        "google.genai": fake_genai}), \
             patch("gemini_client.api_key", return_value="k"), \
             patch("gemini_client._wait_turn"), \
             patch("gemini_client.time.sleep"):
            fake_genai.types = fake_types
            with patch.dict("sys.modules", {"google.genai.types": fake_types}):
                resp, err = gemini_client.generate_ex(
                    ["x"], quiet=True, attempts=attempts, min_interval=0)
        return calls, resp, err

    def test_daily_quota_tries_each_model_once_only(self):
        """額度是「每個模型」各自算 → 還是要換模型試；但同一個模型不再重試。"""
        calls, resp, err = self._run(DAILY, attempts=3)
        self.assertIsNone(resp)
        self.assertEqual(len(calls), 2, f"應該只打 2 次（兩個模型各一次），實際 {calls}")
        self.assertEqual(calls, [gemini_client.MODEL, gemini_client.FALLBACK_MODEL])

    def test_transient_error_still_retries_fully(self):
        """對照組：尖峰塞車要用滿重試次數，否則等於把重試機制拆掉。"""
        calls, resp, err = self._run(BUSY, attempts=3)
        self.assertIsNone(resp)
        self.assertEqual(len(calls), 6, f"兩個模型各 3 次＝6，實際 {len(calls)}")


class RoundStopsOnQuotaTests(unittest.TestCase):
    def test_quota_error_stops_the_whole_round(self):
        """撞到每日額度後，這一輪剩下的文章一篇都不該再讀。"""
        results = [{"url": f"https://www.ptt.cc/bbs/Lifeismoney/M.{i}.A.X.html",
                    "title": "[情報]", "preview": "原文", "cats": []} for i in range(5)]
        quota_outcome = {"checked": False, "image_urls": ["https://i.imgur.com/a.jpg"],
                         "text": "", "errors": [DAILY], "engine": OCR_ENGINE}
        with patch("scripts.build_site.gemini_client.available", return_value=True), \
             patch("scripts.build_site.article_package"), \
             patch("scripts.build_site.PTTClient"), \
             patch("scripts.build_site.ocr_article_images",
                   return_value=quota_outcome) as read:
            _, processed, _ = build_site.fill_image_ocr(results, None, {}, budget=5)
        self.assertEqual(read.call_count, 1, "撞額度後不該再讀第二篇")
        self.assertEqual(processed, 1)

    def test_ordinary_failure_does_not_stop_the_round(self):
        """對照組：一般失敗要繼續跑，只有連續失敗到門檻才熔斷。"""
        results = [{"url": f"https://www.ptt.cc/bbs/Lifeismoney/M.{i}.A.X.html",
                    "title": "[情報]", "preview": "原文", "cats": []} for i in range(3)]
        outcome = {"checked": False, "image_urls": ["https://i.imgur.com/a.jpg"],
                   "text": "", "errors": ["timeout"], "engine": OCR_ENGINE}
        with patch("scripts.build_site.gemini_client.available", return_value=True), \
             patch("scripts.build_site.article_package"), \
             patch("scripts.build_site.PTTClient"), \
             patch("scripts.build_site.ocr_article_images", return_value=outcome) as read:
            _, processed, _ = build_site.fill_image_ocr(results, None, {}, budget=3)
        self.assertEqual(read.call_count, 3)
        self.assertEqual(processed, 3)


class CoffeeBeforeImagesTests(unittest.TestCase):
    def test_coffee_runs_before_image_reading_in_main(self):
        """順序反過來的話，圖片會把當天額度吃光、置頂區塊直接開天窗。

        用原始碼位置斷言：這是「誰先花掉額度」的問題，跑一次 main 太重。
        """
        src = (build_site.__file__)
        with open(src, encoding="utf-8") as fh:
            text = fh.read()
        body = text.split("def main(", 1)[1]
        self.assertLess(body.index("build_coffee"), body.index("fill_image_ocr"),
                        "咖啡情報必須排在 fill_image_ocr 之前")


if __name__ == "__main__":
    unittest.main()
