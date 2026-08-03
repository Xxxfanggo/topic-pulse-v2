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


if __name__ == "__main__":
    unittest.main()
