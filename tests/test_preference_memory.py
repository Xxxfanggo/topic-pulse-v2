import json
import tempfile
import unittest
from pathlib import Path

from topic_pulse_v2.llm_call import LLMClient, LLMProvider, LLMRequest, LLMResponse, LLMStreamEvent
from topic_pulse_v2.memory import InMemoryStore, SQLiteMemoryStore
from topic_pulse_v2.process import (
    PreferenceMemoryExtractionProcess,
    PreferenceMemoryExtractionRequest,
    ReActAgent,
    ReActConfig,
)
from topic_pulse_v2.tool_register import ToolRegistry


class PreferenceExtractorProvider(LLMProvider):
    def __init__(self):
        self.requests: list[LLMRequest] = []

    def call(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(
            content=json.dumps(
                {
                    "memories": [
                        {
                            "content": "用户偏好回答时先给结论，再列来源。",
                            "category": "style",
                            "confidence": 0.9,
                            "importance": 0.8,
                            "evidence": "以后回答我先给结论再列来源",
                        }
                    ]
                },
                ensure_ascii=False,
            )
        )


class FinalAnswerProvider(LLMProvider):
    def __init__(self):
        self.requests: list[LLMRequest] = []

    def call(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(
            content=json.dumps(
                {"thought": "done", "final_answer": "好的"},
                ensure_ascii=False,
            )
        )

    def stream(self, request: LLMRequest):
        self.requests.append(request)
        yield LLMStreamEvent(
            type="done",
            response=LLMResponse(
                content=json.dumps(
                    {"thought": "done", "final_answer": "好的"},
                    ensure_ascii=False,
                )
            ),
        )


class CapturingPreferenceProcess:
    def __init__(self):
        self.requests: list[PreferenceMemoryExtractionRequest] = []

    def schedule_after_turn(self, request: PreferenceMemoryExtractionRequest):
        self.requests.append(request)


class PreferenceMemoryTests(unittest.TestCase):
    def test_extracts_preference_memory_to_sqlite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            provider = PreferenceExtractorProvider()
            store = SQLiteMemoryStore(Path(temp_dir) / "memory.sqlite3")
            process = PreferenceMemoryExtractionProcess(
                llm_client=LLMClient({"fake": provider}, default_provider="fake"),
                memory_store=store,
            )

            result = process.extract(
                PreferenceMemoryExtractionRequest(
                    user_id="user-1",
                    user_message="以后回答我先给结论再列来源。",
                    assistant_answer="好的。",
                    session_id="session-1",
                )
            )

            memories = store.search(
                "user-1",
                "结论 来源",
                metadata_filter={"type": "preference"},
            )
            self.assertTrue(result.should_extract)
            self.assertEqual(len(result.saved), 1)
            self.assertEqual(len(memories), 1)
            self.assertEqual(memories[0].metadata["source_session_id"], "session-1")

    def test_ignores_turn_without_preference_signal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            provider = PreferenceExtractorProvider()
            process = PreferenceMemoryExtractionProcess(
                llm_client=LLMClient({"fake": provider}, default_provider="fake"),
                memory_store=SQLiteMemoryStore(Path(temp_dir) / "memory.sqlite3"),
            )

            result = process.extract(
                PreferenceMemoryExtractionRequest(
                    user_id="user-1",
                    user_message="今天有哪些热点？",
                    assistant_answer="这里是热点列表。",
                )
            )

            self.assertFalse(result.should_extract)
            self.assertEqual(provider.requests, [])

    def test_react_schedules_preference_extraction_after_run_and_stream(self):
        preference_process = CapturingPreferenceProcess()
        agent = ReActAgent(
            llm_client=LLMClient({"fake": FinalAnswerProvider()}, default_provider="fake"),
            tool_registry=ToolRegistry(auto_register_local_tools=False),
            preference_memory_process=preference_process,
            config=ReActConfig(trace_log_path=None),
        )

        agent.run(user_id="user-1", query="以后回答我简洁一点")
        list(agent.stream(user_id="user-1", query="以后默认用表格"))

        self.assertEqual(len(preference_process.requests), 2)
        self.assertEqual(preference_process.requests[0].user_message, "以后回答我简洁一点")
        self.assertEqual(preference_process.requests[1].assistant_answer, "好的")

    def test_react_injects_preference_memory_as_user_profile(self):
        provider = FinalAnswerProvider()
        memory = InMemoryStore()
        memory.save(
            "user-1",
            "用户偏好回答时先给结论，再列来源。",
            metadata={"type": "preference"},
        )
        memory.save(
            "user-1",
            "这是一条非偏好运行记录。",
            metadata={"type": "runtime_note"},
        )
        agent = ReActAgent(
            llm_client=LLMClient({"fake": provider}, default_provider="fake"),
            tool_registry=ToolRegistry(auto_register_local_tools=False),
            memory_store=memory,
            config=ReActConfig(trace_log_path=None),
        )

        agent.run(user_id="user-1", query="今天热点有哪些？")

        system_message = provider.requests[0].messages[0].content
        self.assertIn("用户偏好：", system_message)
        self.assertIn("用户偏好回答时先给结论，再列来源。", system_message)
        self.assertNotIn("这是一条非偏好运行记录。", system_message)


if __name__ == "__main__":
    unittest.main()
