"""咖啡來源被首頁洗出、標籤換行及舊文回退的回歸測試。"""
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import coffee_news as c


class CoffeeNewsTests(unittest.TestCase):
    def test_old_or_undated_articles_are_not_extracted(self):
        for raw in ['<article>咖啡優惠</article>', '"datePublished":"2025-10-25T08:00:00+08:00"']:
            with patch.object(c, "_get", return_value=raw.encode()):
                self.assertIsNone(c.article_document("https://www.nownews.com/news/6886284"))
        stamp = (datetime.now(c.TAIPEI) - timedelta(days=2)).isoformat()
        with patch.object(c, "_get", return_value=f'"datePublished":"{stamp}"<article><p>咖啡優惠</p></article>'.encode("utf-8")):
            result = c.article_document("https://www.nownews.com/news/6886284")
        self.assertEqual(result["text"], "咖啡優惠")
        self.assertEqual(result["published"], stamp)

    def test_tag_multiline_and_attribute_order(self):
        page = '''<a aria-label="咖啡優惠 &amp; 買1送1\n"
        class="card" href="https://www.nownews.com/news/6885855\n"><div>圖片</div></a>
        <a href="https://evil.test/news/9999999" aria-label="咖啡優惠">忽略</a>'''
        with patch.object(c, "_get", return_value=page.encode()), patch.object(c, "_refresh_log"):
            rows = c._from_tags()
        self.assertEqual(len(rows), 2)  # 兩個標籤，各一筆；合併時才去重。
        self.assertEqual(rows[0]["url"], "https://www.nownews.com/news/6885855")
        self.assertEqual(rows[0]["title"], "咖啡優惠 & 買1送1")

    def test_one_broken_tag_does_not_hide_other_tag(self):
        page = b'<a href="https://www.nownews.com/news/6885855" aria-label="coffee">'
        with patch.object(c, "_get", side_effect=[OSError("offline"), page]), patch.object(c, "_refresh_log") as log:
            self.assertEqual(len(c._from_tags()), 1)
            log.assert_called_once()

    def test_empty_tag_is_logged(self):
        with patch.object(c, "_get", return_value=b"<html>changed</html>"), patch.object(c, "_refresh_log") as log:
            self.assertEqual(c._from_tags(), [])
            self.assertEqual(log.call_count, 2)

    def test_tags_find_news_missing_from_homepages_and_deduplicate(self):
        older = {"title": "咖啡優惠", "url": "https://www.nownews.com/news/6882560"}
        newer = {"title": "全家咖啡買2送2", "url": "https://www.nownews.com/news/6885855"}
        with patch.object(c, "_from_rss", return_value=[]), patch.object(c, "_from_category", return_value=[]), patch.object(c, "_from_tags", return_value=[older, newer, newer]):
            self.assertEqual(c.find_latest(), newer)

    def test_same_article_does_not_spend_api_calls(self):
        previous = {"article": {"url": "https://www.nownews.com/news/6885855"}}
        with patch.object(c, "find_articles", return_value=[previous["article"]]), patch.object(c, "extract") as extract:
            self.assertIs(c.build(previous), previous)
            extract.assert_not_called()

    def test_new_article_updates_but_extraction_failure_keeps_previous(self):
        previous = {"article": {"url": "https://www.nownews.com/news/6882560"}}
        latest = {"title": "咖啡優惠", "url": "https://www.nownews.com/news/6885855"}
        with patch.object(c, "find_articles", return_value=[latest]), patch.object(c, "article_document", return_value={"text": "source", "published": "2026-10-25T08:00:00+08:00"}), patch.object(c, "extract", return_value={"活動期間": "10/23-10/27", "通路": [{"名稱": "全家", "優惠": [{"品項": "拿鐵"}]}]}), patch.object(c, "_refresh_log"):
            result = c.build(previous)
            self.assertEqual(result["article"]["url"], latest["url"])
            self.assertEqual(result["通路"][0]["名稱"], "全家")
            self.assertEqual(len(result["articles"]), 2)
        with patch.object(c, "find_articles", return_value=[latest]), patch.object(c, "article_document", return_value={"text": "source", "published": "2026-10-25T08:00:00+08:00"}), patch.object(c, "extract", return_value=None), patch.object(c, "_refresh_log"):
            self.assertIs(c.build(previous), previous)

    def test_brand_news_and_older_roundup_are_added_without_losing_channels(self):
        previous = {"article": {"url": "https://www.nownews.com/news/6886549"},
                    "通路": [{"名稱": "星巴克", "期間": "10月31日", "優惠": [{"品項": "美式"}]}]}
        older = {"title": "咖啡優惠", "url": "https://www.nownews.com/news/6885855"}
        data = {"通路": [{"名稱": name, "管道": "APP", "期間": "10月31日", "優惠": [{"品項": "拿鐵"}]}
                         for name in ["全家", "7-ELEVEN", "85度C"]]}
        with patch.object(c, "find_articles", return_value=[older]), patch.object(c, "article_document", return_value={"text": "source", "published": "2026-10-25T08:00:00+08:00"}), patch.object(c, "extract", return_value=data), patch.object(c, "_refresh_log"):
            result = c.build(previous)
        self.assertEqual({ch["名稱"] for ch in result["通路"]}, {"星巴克", "85度C", "全家", "7-ELEVEN"})
        self.assertEqual(result["article"], previous["article"])
        with patch.object(c, "find_articles", return_value=[older]), patch.object(c, "extract") as extract:
            self.assertIs(c.build(result), result)
            extract.assert_not_called()

    def test_exact_duplicates_removed_but_different_channels_and_periods_kept(self):
        channel = {"名稱": "全家", "管道": "APP", "期間": "10月31日", "優惠": [{"品項": "拿鐵", "說明": "買1送1"}]}
        sources = [{"article": {"url": f"https://www.nownews.com/news/{n}"}, "通路": [channel]}
                   for n in [6885855, 6886549]]
        sources[0]["通路"] += [dict(channel, 管道="門市"), dict(channel, 期間="11月1日")]
        result = c.merge_articles(sources)
        self.assertEqual(len(result["通路"]), 3)
        self.assertEqual(sum(len(ch["優惠"]) for ch in result["通路"]), 3)
        self.assertEqual(len(sources[1]["通路"][0]["優惠"]), 1)

    def test_one_failure_does_not_drop_other_source(self):
        candidates = [{"url": f"https://www.nownews.com/news/{n}", "title": "咖啡優惠"} for n in [6886549, 6885855]]
        with patch.object(c, "find_articles", return_value=candidates), patch.object(c, "article_document", side_effect=[OSError("offline"), {"text": "source", "published": "2026-10-25T08:00:00+08:00"}]), patch.object(c, "extract", return_value={"通路": [{"名稱": "全家", "優惠": [{"品項": "拿鐵"}]}]}), patch.object(c, "_refresh_log"):
            result = c.build()
        self.assertEqual(len(result["articles"]), 1)
        self.assertEqual(result["article"]["url"], candidates[1]["url"])


if __name__ == "__main__":
    unittest.main()
