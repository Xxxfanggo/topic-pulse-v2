import json
import tempfile
import unittest
from pathlib import Path

from topic_pulse_v2.llm_call import LLMClient, LLMProvider, LLMRequest, LLMResponse
from topic_pulse_v2.process import ReActAgent, ReActConfig
from topic_pulse_v2.tool_register import ToolRegistry


class FakeTraceLLMProvider(LLMProvider):
    def __init__(self):
        self.call_count = 0

    def call(self, request: LLMRequest) -> LLMResponse:
        self.call_count += 1
        if self.call_count == 1:
            return LLMResponse(
                content=(
                    '{"thought": "需要调用工具", '
                    '"action": "echo", '
                    '"arguments": {"value": "测试"}}'
                )
            )
        return LLMResponse(
            content='{"thought": "已获得工具结果", "final_answer": "{\\"结果\\": \\"完成\\"}"}'
        )


class FakeSearchToStoreLLMProvider(LLMProvider):
    def __init__(self):
        self.call_count = 0

    def call(self, request: LLMRequest) -> LLMResponse:
        self.call_count += 1
        if self.call_count == 1:
            return LLMResponse(
                content=(
                    '{"thought": "先联网搜索", '
                    '"action": "doubao_search", '
                    '"arguments": {"query": "内存条架构走势"}}'
                )
            )
        if self.call_count == 2:
            return LLMResponse(
                content=(
                    '{"thought": "保存话题", '
                    '"action": "topic_markdown_store", '
                    '"arguments": {'
                    '"topic_name": "内存条架构走势 2025-2026", '
                    '"summary": "DDR5、HBM 等方向正在演进", '
                    '"latest_content": {'
                    '"summary": "模型整理后的摘要", '
                    '"web_results": {"item": [{"...": null}]}, '
                    '"hot_news": {"item": [{"...": null}]}'
                    '}}}'
                )
            )
        return LLMResponse(content='{"thought": "完成", "final_answer": "{\\"结果\\": \\"完成\\"}"}')


class ReActTraceLogTests(unittest.TestCase):
    def test_react_writes_llm_and_tool_trace_log(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            trace_path = Path(temp_dir) / "react_trace.jsonl"
            registry = ToolRegistry(auto_register_local_tools=False)
            registry.register("echo", lambda value: {"echo": value})

            result = ReActAgent(
                llm_client=LLMClient(
                    {"fake": FakeTraceLLMProvider()},
                    default_provider="fake",
                ),
                tool_registry=registry,
                config=ReActConfig(max_steps=2, trace_log_path=str(trace_path)),
            ).run(user_id="user-1", query="测试日志")

            events = [
                json.loads(line)
                for line in trace_path.read_text(encoding="utf-8").splitlines()
            ]
            event_types = [event["type"] for event in events]

            self.assertTrue(result.completed)
            self.assertIn("llm_request", event_types)
            self.assertIn("llm_response", event_types)
            self.assertIn("tool_request", event_types)
            self.assertIn("tool_response", event_types)
            self.assertIn("agent_finish", event_types)
            tool_request = next(event for event in events if event["type"] == "tool_request")
            tool_response = next(event for event in events if event["type"] == "tool_response")
            self.assertEqual(tool_request["data"]["arguments"], {"value": "测试"})
            self.assertEqual(tool_response["data"]["result"], {"echo": "测试"})

    def test_react_repairs_topic_store_placeholder_with_last_search_result(self):
        captured_store_arguments = {}
        search_result = {
            "query": "内存条架构走势",
            "search_type": "web",
            "result_count": 1,
            "web_results": [
                {
                    "title": "DDR5 与 HBM 架构演进",
                    "site_name": "示例新闻",
                    "url": "https://example.com/memory",
                    "publish_time": "2026-08-01T10:00:00+08:00",
                    "summary": "内存架构正在向 DDR5、HBM4 等方向演进。",
                }
            ],
        }

        def doubao_search(query):
            return search_result

        def topic_markdown_store(**kwargs):
            captured_store_arguments.update(kwargs)
            return {"ok": True}

        registry = ToolRegistry(auto_register_local_tools=False)
        registry.register("doubao_search", doubao_search)
        registry.register("topic_markdown_store", topic_markdown_store)

        result = ReActAgent(
            llm_client=LLMClient(
                {"fake": FakeSearchToStoreLLMProvider()},
                default_provider="fake",
            ),
            tool_registry=registry,
            config=ReActConfig(max_steps=3, trace_log_path=None),
        ).run(user_id="user-1", query="内存条架构走势")

        latest_content = captured_store_arguments["latest_content"]

        self.assertTrue(result.completed)
        self.assertEqual(latest_content["summary"], "模型整理后的摘要")
        self.assertEqual(latest_content["web_results"], search_result["web_results"])
        self.assertEqual(latest_content["web_results"][0]["url"], "https://example.com/memory")
        self.assertEqual(latest_content["doubao_search_result"], search_result)


if __name__ == "__main__":
    unittest.main()
