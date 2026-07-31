import unittest

from topic_pulse_v2.information_search import DoubaoSearchResponse, DoubaoWebResult
from topic_pulse_v2.tool_register import (
    DOUBAO_SEARCH_TOOL_NAME,
    ToolRegistry,
    doubao_search,
    register_doubao_search_tool,
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


if __name__ == "__main__":
    unittest.main()
