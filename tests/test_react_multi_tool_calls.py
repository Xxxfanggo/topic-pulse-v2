import json
import tempfile
import unittest
from pathlib import Path

from topic_pulse_v2.llm_call import LLMClient, LLMProvider, LLMRequest, LLMResponse
from topic_pulse_v2.process import ReActAgent, ReActConfig
from topic_pulse_v2.tool_register import ToolRegistry


class FakeMultiToolLLMProvider(LLMProvider):
    def __init__(self):
        self.call_count = 0
        self.second_request_messages = []

    def call(self, request: LLMRequest) -> LLMResponse:
        self.call_count += 1
        if self.call_count == 1:
            return LLMResponse(
                content="",
                tool_calls=[
                    {
                        "name": "first_tool",
                        "args": {"value": "第一个"},
                        "id": "call-1",
                        "type": "tool_call",
                    },
                    {
                        "name": "second_tool",
                        "args": {"value": "第二个"},
                        "id": "call-2",
                        "type": "tool_call",
                    },
                ],
            )
        self.second_request_messages = request.messages
        return LLMResponse(
            content='{"thought": "两个工具都已执行", "final_answer": "{\\"结果\\": \\"完成\\"}"}'
        )


class ReActMultiToolCallsTests(unittest.TestCase):
    def test_react_executes_all_tool_calls_from_one_model_response(self):
        provider = FakeMultiToolLLMProvider()
        calls = []

        def first_tool(value):
            calls.append(("first_tool", value))
            return {"value": value}

        def second_tool(value):
            calls.append(("second_tool", value))
            return {"value": value}

        with tempfile.TemporaryDirectory() as temp_dir:
            trace_path = Path(temp_dir) / "react_trace.jsonl"
            registry = ToolRegistry(auto_register_local_tools=False)
            registry.register("first_tool", first_tool)
            registry.register("second_tool", second_tool)

            result = ReActAgent(
                llm_client=LLMClient({"fake": provider}, default_provider="fake"),
                tool_registry=registry,
                config=ReActConfig(max_steps=2, trace_log_path=str(trace_path)),
            ).run(user_id="user-1", query="测试多工具调用")

            events = [
                json.loads(line)
                for line in trace_path.read_text(encoding="utf-8").splitlines()
            ]
            tool_requests = [event for event in events if event["type"] == "tool_request"]
            tool_responses = [event for event in events if event["type"] == "tool_response"]
            chronological_tool_requests = list(reversed(tool_requests))
            chronological_tool_responses = list(reversed(tool_responses))
            tool_messages = [
                message
                for message in provider.second_request_messages
                if message.role == "tool"
            ]

            self.assertTrue(result.completed)
            self.assertEqual(calls, [("first_tool", "第一个"), ("second_tool", "第二个")])
            self.assertEqual(
                [event["data"]["name"] for event in chronological_tool_requests],
                ["first_tool", "second_tool"],
            )
            self.assertEqual(
                [event["data"]["name"] for event in chronological_tool_responses],
                ["first_tool", "second_tool"],
            )
            self.assertEqual([message.tool_call_id for message in tool_messages], ["call-1", "call-2"])
            self.assertEqual(len(result.steps[0].tool_calls), 2)
            self.assertEqual(len(result.steps[0].tool_results), 2)


if __name__ == "__main__":
    unittest.main()
