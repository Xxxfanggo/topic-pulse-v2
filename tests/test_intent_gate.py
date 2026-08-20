import json
import unittest
from threading import Lock

from topic_pulse_v2.llm_call import LLMClient, LLMProvider, LLMRequest, LLMResponse
from topic_pulse_v2.process import ReActResult, ReActStreamEvent
from topic_pulse_v2.scope import CLARIFY_REPLY, OFF_TOPIC_REPLY, IntentGate

try:
    from topic_pulse_v2_chat.web.react_service import ReactChatService
except ModuleNotFoundError:
    ReactChatService = None


class RecordingClassifierProvider(LLMProvider):
    def __init__(self, content: str):
        self.content = content
        self.requests: list[LLMRequest] = []

    def call(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(content=self.content)


class RecordingAgent:
    def __init__(self):
        self.run_calls = []
        self.stream_calls = []

    def run(self, **kwargs):
        self.run_calls.append(kwargs)
        return ReActResult(
            answer='{"summary":"allowed"}',
            session_id=kwargs.get("session_id") or "session-allowed",
            steps=[],
            completed=True,
        )

    def stream(self, **kwargs):
        self.stream_calls.append(kwargs)
        yield ReActStreamEvent(
            type="result",
            session_id=kwargs.get("session_id") or "session-allowed",
            result=self.run(**kwargs),
        )


def build_service(gate: IntentGate, agent: RecordingAgent) -> ReactChatService:
    service = ReactChatService.__new__(ReactChatService)
    service._lock = Lock()
    service._intent_gate = gate
    service._agent = agent
    return service


class IntentGateTests(unittest.TestCase):
    def test_clear_hotspot_request_is_allowed_without_classifier(self):
        provider = RecordingClassifierProvider("not used")
        gate = IntentGate(
            classifier_client=LLMClient({"fake": provider}, default_provider="fake"),
            trace_log_path=None,
        )

        decision = gate.classify("整理今天的科技热点")

        self.assertEqual(decision.intent, "HOTSPOT_FILTER")
        self.assertEqual(decision.decision, "ALLOW")
        self.assertEqual(provider.requests, [])

    def test_clear_off_topic_request_is_rejected_without_classifier(self):
        provider = RecordingClassifierProvider("not used")
        gate = IntentGate(
            classifier_client=LLMClient({"fake": provider}, default_provider="fake"),
            trace_log_path=None,
        )

        decision = gate.classify("帮我写一个 Python 快排")

        self.assertEqual(decision.intent, "OFF_TOPIC")
        self.assertEqual(decision.decision, "REJECT")
        self.assertEqual(provider.requests, [])

    def test_ambiguous_request_uses_tool_free_classifier(self):
        provider = RecordingClassifierProvider(
            json.dumps(
                {
                    "intent": "HOTSPOT_TRACKING",
                    "confidence": 0.94,
                    "normalized_query": "分析这个热点事件的最新进展",
                },
                ensure_ascii=False,
            )
        )
        gate = IntentGate(
            classifier_client=LLMClient({"fake": provider}, default_provider="fake"),
            classifier_provider="fake",
            trace_log_path=None,
        )

        decision = gate.classify("分析这个事件")

        self.assertEqual(decision.intent, "HOTSPOT_TRACKING")
        self.assertEqual(decision.decision, "ALLOW")
        self.assertEqual(decision.normalized_query, "分析这个热点事件的最新进展")
        self.assertEqual(provider.requests[0].tools, [])
        self.assertEqual(provider.requests[0].metadata["purpose"], "intent_classification")

    def test_low_confidence_classifier_result_requires_clarification(self):
        provider = RecordingClassifierProvider(
            '{"intent":"HOTSPOT_DISCOVERY","confidence":0.42,"normalized_query":"看看最近发生了什么"}'
        )
        gate = IntentGate(
            classifier_client=LLMClient({"fake": provider}, default_provider="fake"),
            classifier_provider="fake",
            trace_log_path=None,
        )

        decision = gate.classify("最近怎么样")

        self.assertEqual(decision.intent, "AMBIGUOUS")
        self.assertEqual(decision.decision, "CLARIFY")

    def test_invalid_classifier_output_fails_closed(self):
        provider = RecordingClassifierProvider("I can help with that.")
        gate = IntentGate(
            classifier_client=LLMClient({"fake": provider}, default_provider="fake"),
            classifier_provider="fake",
            trace_log_path=None,
        )

        decision = gate.classify("帮我看看这个")

        self.assertEqual(decision.decision, "CLARIFY")
        self.assertEqual(decision.source, "fallback")

    def test_scheduler_refresh_is_trusted_hotspot_request(self):
        provider = RecordingClassifierProvider("not used")
        gate = IntentGate(
            classifier_client=LLMClient({"fake": provider}, default_provider="fake"),
            classifier_provider="fake",
            trace_log_path=None,
        )

        decision = gate.classify(
            "更新已关注话题",
            metadata={"source": "scheduler", "task": "refresh_topic"},
        )

        self.assertEqual(decision.intent, "HOTSPOT_TRACKING")
        self.assertEqual(decision.decision, "ALLOW")
        self.assertEqual(decision.source, "trusted")
        self.assertEqual(provider.requests, [])


@unittest.skipIf(ReactChatService is None, "web runtime dependencies are not installed")
class ReactChatServiceScopeTests(unittest.TestCase):
    def test_rejected_request_never_calls_agent_in_sync_path(self):
        agent = RecordingAgent()
        service = build_service(IntentGate(trace_log_path=None), agent)

        result = service.chat(user_id="user-1", message="什么是 Transformer？")

        self.assertEqual(result.answer, OFF_TOPIC_REPLY)
        self.assertTrue(result.completed)
        self.assertEqual(result.steps, [])
        self.assertEqual(agent.run_calls, [])

    def test_rejected_request_never_calls_agent_in_stream_path(self):
        agent = RecordingAgent()
        service = build_service(IntentGate(trace_log_path=None), agent)

        events = list(service.chat_stream(user_id="user-1", message="帮我翻译这段英文"))

        self.assertEqual([event.type for event in events], ["status", "result"])
        self.assertEqual(events[-1].result.answer, OFF_TOPIC_REPLY)
        self.assertEqual(agent.stream_calls, [])

    def test_allowed_request_reaches_agent_with_gate_metadata(self):
        agent = RecordingAgent()
        service = build_service(IntentGate(trace_log_path=None), agent)

        result = service.chat(user_id="user-1", message="整理今天的国际热点")

        self.assertEqual(result.answer, '{"summary":"allowed"}')
        self.assertEqual(len(agent.run_calls), 1)
        self.assertEqual(agent.run_calls[0]["metadata"]["intent"], "HOTSPOT_FILTER")
        self.assertEqual(agent.run_calls[0]["metadata"]["intent_decision"], "ALLOW")

    def test_ambiguous_request_uses_classifier_before_agent(self):
        provider = RecordingClassifierProvider(
            '{"intent":"HOTSPOT_DISCOVERY","confidence":0.91,"normalized_query":"整理今天的热点"}'
        )
        gate = IntentGate(
            classifier_client=LLMClient({"fake": provider}, default_provider="fake"),
            classifier_provider="fake",
            trace_log_path=None,
        )
        agent = RecordingAgent()
        service = build_service(gate, agent)

        result = service.chat(user_id="user-1", message="帮我看看这个")

        self.assertTrue(result.completed)
        self.assertEqual(len(provider.requests), 1)
        self.assertEqual(len(agent.run_calls), 1)
        self.assertEqual(agent.run_calls[0]["query"], "整理今天的热点")


if __name__ == "__main__":
    unittest.main()
