"""咖啡來源被首頁洗出、標籤換行及舊文回退的回歸測試。"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import coffee_news as c


class CoffeeNewsTests(unittest.TestCase):
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

    def test_older_or_same_article_never_replaces_newer_data(self):
        previous = {"updated_at": "2026-10-24 12:00", "article": {"url": "https://www.nownews.com/news/6885855"}}
        for article_id in [6882560, 6885855]:
            with self.subTest(article_id=article_id), patch.object(c, "find_latest", return_value={"title": "咖啡優惠", "url": f"https://www.nownews.com/news/{article_id}"}), patch.object(c, "extract") as extract, patch.object(c, "_refresh_log"):
                self.assertIs(c.build(previous), previous)
                extract.assert_not_called()

    def test_new_article_updates_but_extraction_failure_keeps_previous(self):
        previous = {"article": {"url": "https://www.nownews.com/news/6882560"}}
        latest = {"title": "咖啡優惠", "url": "https://www.nownews.com/news/6885855"}
        with patch.object(c, "find_latest", return_value=latest), patch.object(c, "article_text", return_value="source"), patch.object(c, "extract", return_value={"活動期間": "10/23-10/27", "通路": [{"名稱": "全家"}]}), patch.object(c, "_refresh_log"):
            result = c.build(previous)
            self.assertEqual(result["article"]["url"], latest["url"])
            self.assertEqual(result["通路"], [{"名稱": "全家"}])
        with patch.object(c, "find_latest", return_value=latest), patch.object(c, "article_text", return_value="source"), patch.object(c, "extract", return_value=None), patch.object(c, "_refresh_log"):
            self.assertIs(c.build(previous), previous)


if __name__ == "__main__":
    unittest.main()
