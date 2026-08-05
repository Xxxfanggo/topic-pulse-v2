import unittest

from topic_pulse_v2.context_trim import ContextTrimRequest, ContextTrimResult, ContextTrimmer
from topic_pulse_v2.llm_call import LLMClient, LLMProvider, LLMRequest, LLMResponse, Message
from topic_pulse_v2.process import ReActAgent, ReActConfig
from topic_pulse_v2.tool_register import ToolRegistry


class ReplacingContextTrimmer(ContextTrimmer):
    def __init__(self):
        self.requests: list[ContextTrimRequest] = []

    def trim(self, request: ContextTrimRequest) -> ContextTrimResult:
        self.requests.append(request)
        return ContextTrimResult(
            messages=[
                Message(role="system", content="已由 context_trim 组装上下文"),
                Message(role="user", content=request.query or ""),
            ],
            metadata={"strategy": "test_replace"},
        )


class CapturingProvider(LLMProvider):
    def __init__(self):
        self.request: LLMRequest | None = None

    def call(self, request: LLMRequest) -> LLMResponse:
        self.request = request
        return LLMResponse(
            content='{"thought": "直接回答", "final_answer": "{\\"结果\\": \\"完成\\"}"}'
        )


class ContextTrimTests(unittest.TestCase):
    def test_react_uses_context_trimmer_before_llm_call(self):
        provider = CapturingProvider()
        trimmer = ReplacingContextTrimmer()

        result = ReActAgent(
            llm_client=LLMClient({"fake": provider}, default_provider="fake"),
            tool_registry=ToolRegistry(auto_register_local_tools=False),
            context_trimmer=trimmer,
            config=ReActConfig(trace_log_path=None),
        ).run(user_id="user-1", query="测试上下文组装")

        self.assertTrue(result.completed)
        self.assertEqual(len(trimmer.requests), 1)
        self.assertIsNotNone(provider.request)
        self.assertEqual(
            [message.content for message in provider.request.messages],
            ["已由 context_trim 组装上下文", "测试上下文组装"],
        )


if __name__ == "__main__":
    unittest.main()
