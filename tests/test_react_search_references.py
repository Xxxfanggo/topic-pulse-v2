import json
import unittest

from topic_pulse_v2.process import ReActAgent


class ReActSearchReferenceTests(unittest.TestCase):
    def test_augment_answer_with_search_references(self):
        answer = '{"summary": "搜索完成", "items": []}'
        search_result = {
            "query": "内存条价格走势 最近6个月",
            "web_results": [
                {
                    "title": "内存条价格持续上涨",
                    "url": "https://example.com/news-1",
                },
                {
                    "raw": {
                        "Title": "DDR5 价格趋势分析",
                        "Url": "https://example.com/news-2",
                    }
                },
            ],
        }

        augmented = ReActAgent._augment_answer_with_search_references(
            answer,
            "内存条价格走势",
            search_result,
        )

        payload = json.loads(augmented)
        self.assertEqual(payload["query_key"], "内存条价格走势 最近6个月")
        self.assertEqual(
            payload["reference_data"],
            [
                {"title": "内存条价格持续上涨", "url": "https://example.com/news-1"},
                {"title": "DDR5 价格趋势分析", "url": "https://example.com/news-2"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
