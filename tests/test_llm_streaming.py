import unittest

from topic_pulse_v2.llm_call import LLMClient, LLMProvider, LLMRequest, LLMResponse, LLMStreamEvent
from topic_pulse_v2.process import ReActAgent, ReActConfig
from topic_pulse_v2.tool_register import ToolRegistry


class FallbackProvider(LLMProvider):
    def call(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(content="fallback response")


class StreamingProvider(LLMProvider):
    def call(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(content="unused")

    def stream(self, request: LLMRequest):
        yield LLMStreamEvent(type="delta", content='{"thought": "')
        yield LLMStreamEvent(type="delta", content='done", "final_answer": "')
        yield LLMStreamEvent(type="delta", content='streamed answer"}')
        yield LLMStreamEvent(
            type="done",
            response=LLMResponse(
                content='{"thought": "done", "final_answer": "streamed answer"}'
            ),
        )


class LLMStreamingTests(unittest.TestCase):
    def test_client_stream_falls_back_to_call(self):
        client = LLMClient({"fake": FallbackProvider()}, default_provider="fake")

        events = list(client.stream([]))

        self.assertEqual([event.type for event in events], ["delta", "done"])
        self.assertEqual(events[0].content, "fallback response")
        self.assertEqual(events[-1].response.content, "fallback response")

    def test_react_stream_yields_llm_delta_and_result(self):
        agent = ReActAgent(
            llm_client=LLMClient({"fake": StreamingProvider()}, default_provider="fake"),
            tool_registry=ToolRegistry(auto_register_local_tools=False),
            config=ReActConfig(trace_log_path=None),
        )

        events = list(agent.stream(user_id="user-1", query="hello"))

        self.assertTrue(any(event.type == "llm_delta" for event in events))
        self.assertEqual(events[-1].type, "result")
        self.assertEqual(events[-1].result.answer, "streamed answer")
        self.assertTrue(events[-1].result.completed)


if __name__ == "__main__":
    unittest.main()
