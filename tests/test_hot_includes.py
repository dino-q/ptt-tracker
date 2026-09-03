import unittest

from server import ALWAYS_INCLUDE_HOT_BOARDS, select_hot_boards, select_hot_probes


class HotIncludeTests(unittest.TestCase):
    def test_default_fixed_boards_are_womentalk_and_boy_girl(self):
        self.assertEqual(ALWAYS_INCLUDE_HOT_BOARDS, ["WomenTalk", "Boy-Girl"])

    def test_fixed_boards_are_appended_and_deduplicated(self):
        hot = [{"board": "Gossiping"}, {"board": "WomenTalk"}]
        boards, added = select_hot_boards(hot, 2, ALWAYS_INCLUDE_HOT_BOARDS)
        self.assertEqual(boards, ["Gossiping", "WomenTalk", "Boy-Girl"])
        self.assertEqual(added, ["Boy-Girl"])

    def test_reserved_boards_reach_probe_even_with_lower_scores(self):
        reps = [
            {"url": f"https://top/{i}", "board": "Gossiping", "score": 1000 - i}
            for i in range(40)
        ]
        reps += [
            {"url": "https://women/1", "board": "WomenTalk", "score": 30},
            {"url": "https://bg/1", "board": "Boy-Girl", "score": 25},
        ]
        probes = select_hot_probes(reps, 40, ALWAYS_INCLUDE_HOT_BOARDS)
        urls = {item["url"] for item in probes}
        self.assertEqual(len(probes), 40)
        self.assertIn("https://women/1", urls)
        self.assertIn("https://bg/1", urls)
        tiny = select_hot_probes(reps, 2, ALWAYS_INCLUDE_HOT_BOARDS)
        self.assertEqual({item["board"] for item in tiny}, {"WomenTalk", "Boy-Girl"})

    def test_reserved_board_quota_does_not_duplicate_urls(self):
        shared = {"url": "https://women/1", "board": "WomenTalk", "score": 99}
        probes = select_hot_probes([shared, shared], 10, ["WomenTalk"])
        self.assertEqual([item["url"] for item in probes], ["https://women/1"])


if __name__ == "__main__":
    unittest.main()
