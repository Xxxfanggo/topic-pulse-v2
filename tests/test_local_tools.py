import unittest
import tempfile
from pathlib import Path

from topic_pulse_v2.information_search import DoubaoSearchResponse, DoubaoWebResult
from topic_pulse_v2.tool_register import (
    DOUBAO_SEARCH_TOOL_NAME,
    TOPIC_MARKDOWN_STORE_TOOL_NAME,
    ToolRegistry,
    doubao_search,
    register_doubao_search_tool,
    topic_markdown_store,
)


class FakeDoubaoClient:
    def __init__(self):
        self.calls = []

    def web_search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return DoubaoSearchResponse(
            query=query,
            search_type="web",
            result_count=1,
            web_results=[
                DoubaoWebResult(
                    id="result-1",
                    title="成都天气",
                    url="https://example.com/weather",
                    snippet="晴",
                )
            ],
            request_id="request-1",
            raw={"Result": {"ResultCount": 1}},
        )


class LocalToolsTests(unittest.TestCase):
    def test_doubao_search_calls_web_search_and_returns_dict(self):
        client = FakeDoubaoClient()

        result = doubao_search("今天成都天气怎么样", count=3, client=client)

        self.assertEqual(client.calls[0][0], "今天成都天气怎么样")
        self.assertEqual(client.calls[0][1]["count"], 3)
        self.assertEqual(result["query"], "今天成都天气怎么样")
        self.assertEqual(result["web_results"][0]["title"], "成都天气")
        self.assertEqual(result["raw"], {"Result": {"ResultCount": 1}})

    def test_register_doubao_search_tool(self):
        registry = ToolRegistry(auto_register_local_tools=False)

        register_doubao_search_tool(registry)

        self.assertTrue(registry.has(DOUBAO_SEARCH_TOOL_NAME))
        spec = registry.get(DOUBAO_SEARCH_TOOL_NAME)
        self.assertEqual(spec.metadata["tool_display_name"], "豆包搜索")
        self.assertIn("query", spec.parameters["required"])

    def test_registry_auto_registers_local_tools(self):
        registry = ToolRegistry()

        self.assertTrue(registry.has(DOUBAO_SEARCH_TOOL_NAME))
        self.assertTrue(registry.has(TOPIC_MARKDOWN_STORE_TOOL_NAME))

    def test_topic_markdown_store_creates_and_merges_topic_file(self):
        latest_content = {
            "overall_summary": "韩红近期热点主要围绕公益辟谣与演唱会动态。",
            "result": {
                "web_results": [
                    {
                        "publish_time": "2026-07-20T10:00:00+08:00",
                        "title": "韩红基金会回应传言",
                        "summary": "基金会回应近期网络传言。",
                        "site_name": "示例新闻",
                        "url": "https://example.com/old",
                        "note": "这条备注不应写入 Markdown。",
                    },
                    {
                        "publish_time": "2026-08-01T10:00:00+08:00",
                        "title": "韩红公益项目最新进展",
                        "summary": "公益项目出现最新进展。",
                        "raw": {
                            "SiteName": "豆包来源站点",
                            "Url": "https://example.com/new",
                        },
                    },
                ],
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            first = topic_markdown_store(
                "韩红最近热点新闻",
                latest_content=latest_content,
                root_dir=temp_dir,
                created_at="2026-08-03",
            )
            second = topic_markdown_store(
                "韩红最近热点新闻",
                latest_content=latest_content,
                root_dir=temp_dir,
            )

            content = Path(first["path"]).read_text(encoding="utf-8")
            timeline_content = content.split("## 时间线", 1)[1]

            self.assertTrue(first["created"])
            self.assertEqual(first["appended_count"], 2)
            self.assertFalse(second["created"])
            self.assertEqual(second["appended_count"], 0)
            self.assertIn("# 韩红最近热点新闻", content)
            self.assertIn("韩红基金会回应传言", content)
            self.assertIn("- 来源：豆包来源站点", content)
            self.assertIn("- 链接：https://example.com/new", content)
            self.assertIn("- 来源：示例新闻", content)
            self.assertIn("- 链接：https://example.com/old", content)
            self.assertNotIn("- 备注：", content)
            self.assertLess(
                timeline_content.index("韩红公益项目最新进展"),
                timeline_content.index("韩红基金会回应传言"),
            )
            for item in first["appended_items"]:
                self.assertNotIn("note", item)


if __name__ == "__main__":
    unittest.main()
