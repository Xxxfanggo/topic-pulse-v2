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

    def test_augment_answer_with_topic_update(self):
        answer = '{"summary": "已更新关注话题", "items": []}'
        store_result = {
            "topic_name": "内存条价格走势",
            "operation": "update",
            "update_status": "updated_with_new_items",
            "new_count": 1,
            "existing_count": 2,
            "new_items": [
                {
                    "date": "2026-08-10",
                    "title": "DDR5 价格继续上涨",
                    "source": "示例新闻",
                    "url": "https://example.com/new",
                    "summary": "DDR5 现货价格继续上行。",
                }
            ],
            "existing_items": [
                {
                    "date": "2026-08-01",
                    "title": "此前已经记录的价格上涨",
                    "source": "旧来源",
                    "url": "https://example.com/old",
                    "summary": "此前记录。",
                }
            ],
        }

        augmented = ReActAgent._augment_answer_with_topic_update(answer, store_result)

        payload = json.loads(augmented)
        self.assertEqual(payload["topic_update"]["topic_name"], "内存条价格走势")
        self.assertEqual(payload["topic_update"]["new_count"], 1)
        self.assertEqual(payload["topic_update"]["existing_count"], 2)
        self.assertEqual(payload["topic_update"]["new_items"][0]["title"], "DDR5 价格继续上涨")
        self.assertEqual(payload["topic_update"]["existing_items"][0]["title"], "此前已经记录的价格上涨")


if __name__ == "__main__":
    unittest.main()
