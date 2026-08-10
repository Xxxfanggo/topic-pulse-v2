import importlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace


try:
    from fastapi.testclient import TestClient

    from topic_pulse_v2_chat.web import create_app
except ModuleNotFoundError:
    TestClient = None
    create_app = None


class FakeChatRuntime:
    def __init__(self):
        self.calls = []

    def chat(self, *, user_id, message, session_id=None, metadata=None):
        self.calls.append(
            {
                "user_id": user_id,
                "message": message,
                "session_id": session_id,
                "metadata": metadata,
            }
        )
        return SimpleNamespace(
            answer="This is a fake ReActAgent answer.",
            session_id=session_id or "session-1",
            completed=True,
            steps=[],
        )


class FailingChatRuntime:
    def chat(self, *, user_id, message, session_id=None, metadata=None):
        raise RuntimeError("upstream model unavailable")


@unittest.skipIf(TestClient is None, "fastapi is not installed")
class ChatWebAppTests(unittest.TestCase):
    def test_health_and_chat_calls_runtime(self):
        runtime = FakeChatRuntime()
        client = TestClient(create_app(chat_runtime=runtime))

        health = client.get("/api/health")
        chat = client.post(
            "/api/chat",
            json={
                "user_id": "anonymous-user-1",
                "message": "Track recent AI layoff news.",
                "session_id": "session-existing",
                "history": [{"role": "user", "content": "hello"}],
            },
        )

        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")
        self.assertEqual(chat.status_code, 200)
        self.assertEqual(chat.json()["answer"], "This is a fake ReActAgent answer.")
        self.assertEqual(chat.json()["session_id"], "session-existing")
        self.assertEqual(chat.json()["user_id"], "anonymous-user-1")
        self.assertTrue(chat.json()["completed"])
        self.assertEqual(runtime.calls[0]["user_id"], "anonymous-user-1")
        self.assertEqual(runtime.calls[0]["session_id"], "session-existing")
        self.assertEqual(runtime.calls[0]["metadata"]["source"], "web")
        self.assertEqual(runtime.calls[0]["metadata"]["history_length"], 1)

    def test_chat_runtime_failure_returns_json_error(self):
        client = TestClient(create_app(chat_runtime=FailingChatRuntime()))

        chat = client.post(
            "/api/chat",
            json={
                "user_id": "anonymous-user-1",
                "message": "hello",
            },
        )

        self.assertEqual(chat.status_code, 503)
        self.assertIn("detail", chat.json())

    def test_chat_formats_structured_answer_summary_only(self):
        class StructuredRuntime:
            def chat(self, *, user_id, message, session_id=None, metadata=None):
                return SimpleNamespace(
                    answer='{"summary":"Hello, I can track topics for you.","items":[],"next_action":"Please add a topic."}',
                    session_id="session-structured",
                    completed=True,
                    steps=[],
                )

        client = TestClient(create_app(chat_runtime=StructuredRuntime()))
        chat = client.post(
            "/api/chat",
            json={
                "user_id": "anonymous-user-1",
                "message": "hello",
            },
        )

        self.assertEqual(chat.status_code, 200)
        self.assertEqual(chat.json()["answer"], "Hello, I can track topics for you.")

    def test_stream_chat_returns_ndjson_events(self):
        class StructuredRuntime:
            def chat(self, *, user_id, message, session_id=None, metadata=None):
                return SimpleNamespace(
                    answer='{"summary":"Streaming answer.","items":[],"query_key":"stream query","reference_data":[{"title":"Ref","url":"https://example.com"}]}',
                    session_id="session-stream",
                    completed=True,
                    steps=[],
                )

        client = TestClient(create_app(chat_runtime=StructuredRuntime()))
        with client.stream(
            "POST",
            "/api/chat/stream",
            json={
                "user_id": "anonymous-user-1",
                "message": "hello",
            },
        ) as response:
            body = response.read().decode("utf-8")

        events = [json.loads(line) for line in body.splitlines() if line.strip()]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(events[0]["type"], "status")
        self.assertIn({"type": "delta", "content": "Streaming an"}, events)
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(events[-1]["session_id"], "session-stream")

    def test_stream_chat_uses_runtime_stream_when_available(self):
        class StreamingRuntime:
            def chat(self, *, user_id, message, session_id=None, metadata=None):
                raise AssertionError("chat fallback should not be used")

            def chat_stream(self, *, user_id, message, session_id=None, metadata=None):
                yield SimpleNamespace(type="status", data={"stage": "llm_start"})
                yield SimpleNamespace(
                    type="result",
                    data={},
                    result=SimpleNamespace(
                        answer='{"summary":"Runtime stream answer.","items":[]}',
                        session_id="session-runtime-stream",
                        completed=True,
                        steps=[],
                    ),
                )

        client = TestClient(create_app(chat_runtime=StreamingRuntime()))
        with client.stream(
            "POST",
            "/api/chat/stream",
            json={
                "user_id": "anonymous-user-1",
                "message": "hello",
            },
        ) as response:
            body = response.read().decode("utf-8")

        events = [json.loads(line) for line in body.splitlines() if line.strip()]
        self.assertEqual(response.status_code, 200)
        self.assertIn({"type": "delta", "content": "Runtime stre"}, events)
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(events[-1]["session_id"], "session-runtime-stream")

    def test_stream_chat_extracts_visible_answer_from_llm_delta(self):
        class StreamingRuntime:
            def chat(self, *, user_id, message, session_id=None, metadata=None):
                raise AssertionError("chat fallback should not be used")

            def chat_stream(self, *, user_id, message, session_id=None, metadata=None):
                yield SimpleNamespace(type="status", data={"stage": "llm_start"})
                yield SimpleNamespace(
                    type="llm_delta",
                    content='{"thought":"done","final_answer":"{\\"summary\\":\\"Hel',
                    data={},
                )
                yield SimpleNamespace(
                    type="llm_delta",
                    content='lo stream\\",\\"items\\":[]}"}',
                    data={},
                )
                yield SimpleNamespace(
                    type="result",
                    data={},
                    result=SimpleNamespace(
                        answer='{"summary":"Hello stream","items":[]}',
                        session_id="session-visible-stream",
                        completed=True,
                        steps=[],
                    ),
                )

        client = TestClient(create_app(chat_runtime=StreamingRuntime()))
        with client.stream(
            "POST",
            "/api/chat/stream",
            json={
                "user_id": "anonymous-user-1",
                "message": "hello",
            },
        ) as response:
            body = response.read().decode("utf-8")

        events = [json.loads(line) for line in body.splitlines() if line.strip()]
        deltas = [event["content"] for event in events if event["type"] == "delta"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual("".join(deltas), "Hello stream")
        self.assertFalse(any("final_answer" in delta for delta in deltas))

    def test_stream_chat_emits_public_agent_steps(self):
        class StreamingRuntime:
            def chat(self, *, user_id, message, session_id=None, metadata=None):
                raise AssertionError("chat fallback should not be used")

            def chat_stream(self, *, user_id, message, session_id=None, metadata=None):
                yield SimpleNamespace(type="status", data={"stage": "llm_start"})
                yield SimpleNamespace(
                    type="tool_start",
                    step_index=1,
                    data={
                        "name": "doubao_search",
                        "arguments": {"query": "latest AI news"},
                        "thought": "需要先检索最新资料，再组织回答。",
                    },
                )
                yield SimpleNamespace(
                    type="tool_end",
                    step_index=1,
                    data={"name": "doubao_search", "success": True},
                )
                yield SimpleNamespace(
                    type="step_end",
                    step_index=1,
                    data={"completed": False, "thought": "资料已返回，需要继续归纳。"},
                )
                yield SimpleNamespace(
                    type="result",
                    data={},
                    result=SimpleNamespace(
                        answer='{"summary":"Done.","items":[]}',
                        session_id="session-agent-step",
                        completed=True,
                        steps=[],
                    ),
                )

        client = TestClient(create_app(chat_runtime=StreamingRuntime()))
        with client.stream(
            "POST",
            "/api/chat/stream",
            json={"user_id": "anonymous-user-1", "message": "hello"},
        ) as response:
            body = response.read().decode("utf-8")

        events = [json.loads(line) for line in body.splitlines() if line.strip()]
        step_events = [event for event in events if event["type"] == "agent_step"]
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(step_events), 3)
        self.assertEqual(step_events[0]["title"], "正在联网检索")
        self.assertIn("检索最新资料", step_events[0]["detail"])
        self.assertFalse(any("<think>" in event["detail"] for event in step_events))

    def test_chat_returns_search_reference_metadata(self):
        class SearchReferenceRuntime:
            def chat(self, *, user_id, message, session_id=None, metadata=None):
                return SimpleNamespace(
                    answer=(
                        '{"summary":"搜索完成","items":[],'
                        '"query_key":"内存条价格走势 最近6个月",'
                        '"reference_data":[{"资料标题":"内存条价格持续上涨","资料链接":"https://example.com/news-1"}]}'
                    ),
                    session_id="session-search",
                    completed=True,
                    steps=[],
                )

        client = TestClient(create_app(chat_runtime=SearchReferenceRuntime()))
        chat = client.post(
            "/api/chat",
            json={
                "user_id": "anonymous-user-1",
                "message": "查一下内存条价格走势",
            },
        )

        self.assertEqual(chat.status_code, 200)
        self.assertEqual(chat.json()["answer"], "搜索完成")
        self.assertEqual(chat.json()["query_key"], "内存条价格走势 最近6个月")
        self.assertEqual(
            chat.json()["reference_data"],
            [{"title": "内存条价格持续上涨", "url": "https://example.com/news-1"}],
        )

    def test_chat_returns_topic_update_metadata(self):
        class TopicUpdateRuntime:
            def chat(self, *, user_id, message, session_id=None, metadata=None):
                return SimpleNamespace(
                    answer=(
                        '{"summary":"已更新关注话题","items":[],'
                        '"topic_update":{'
                        '"topic_name":"内存条价格走势",'
                        '"status":"updated_with_new_items",'
                        '"new_count":1,'
                        '"existing_count":2,'
                        '"new_items":[{"date":"2026-08-10","title":"DDR5 价格继续上涨","source":"示例新闻","url":"https://example.com/new","summary":"价格继续上行"}],'
                        '"existing_items":[{"date":"2026-08-01","title":"此前已记录的价格上涨","source":"旧来源","url":"https://example.com/old"}]'
                        '}}'
                    ),
                    session_id="session-topic-update",
                    completed=True,
                    steps=[],
                )

        client = TestClient(create_app(chat_runtime=TopicUpdateRuntime()))
        chat = client.post(
            "/api/chat",
            json={
                "user_id": "anonymous-user-1",
                "message": "上次关注的内存条价格怎么样了",
            },
        )

        self.assertEqual(chat.status_code, 200)
        self.assertEqual(chat.json()["answer"], "已更新关注话题")
        self.assertEqual(chat.json()["topic_update"]["topic_name"], "内存条价格走势")
        self.assertEqual(chat.json()["topic_update"]["new_count"], 1)
        self.assertEqual(chat.json()["topic_update"]["new_items"][0]["title"], "DDR5 价格继续上涨")

    def test_chat_formats_think_prefixed_structured_answer_summary_only(self):
        class ThinkStructuredRuntime:
            def chat(self, *, user_id, message, session_id=None, metadata=None):
                return SimpleNamespace(
                    answer='<think>internal reasoning</think>\n\n{"summary":"Done.","items":[],"next_action":"Ask another question."}',
                    session_id="session-structured",
                    completed=True,
                    steps=[],
                )

        client = TestClient(create_app(chat_runtime=ThinkStructuredRuntime()))
        chat = client.post(
            "/api/chat",
            json={
                "user_id": "anonymous-user-1",
                "message": "hello",
            },
        )

        self.assertEqual(chat.status_code, 200)
        self.assertEqual(chat.json()["answer"], "Done.")

    def test_chat_keeps_markdown_summary_for_display(self):
        class MarkdownStructuredRuntime:
            def chat(self, *, user_id, message, session_id=None, metadata=None):
                return SimpleNamespace(
                    answer='{"summary":"## Insight\\n\\n- Alpha\\n- **Beta**","items":[{"title":"Hidden"}],"next_action":"Hidden action"}',
                    session_id="session-markdown",
                    completed=True,
                    steps=[],
                )

        client = TestClient(create_app(chat_runtime=MarkdownStructuredRuntime()))
        chat = client.post(
            "/api/chat",
            json={
                "user_id": "anonymous-user-1",
                "message": "hello",
            },
        )

        self.assertEqual(chat.status_code, 200)
        self.assertEqual(chat.json()["answer"], "## Insight\n\n- Alpha\n- **Beta**")

    def test_chat_extracts_summary_from_malformed_json_answer(self):
        class MalformedStructuredRuntime:
            def chat(self, *, user_id, message, session_id=None, metadata=None):
                return SimpleNamespace(
                    answer='{"summary":"Apple enters the "biggest product year" with new devices.\\n\\n- iPhone\\n- Mac","items":[{"title":"Hidden"}],"next_action":"Hidden action"}',
                    session_id="session-malformed",
                    completed=True,
                    steps=[],
                )

        client = TestClient(create_app(chat_runtime=MalformedStructuredRuntime()))
        chat = client.post(
            "/api/chat",
            json={
                "user_id": "anonymous-user-1",
                "message": "hello",
            },
        )

        self.assertEqual(chat.status_code, 200)
        self.assertEqual(chat.json()["answer"], 'Apple enters the "biggest product year" with new devices.\n\n- iPhone\n- Mac')

    def test_chat_extracts_summary_from_nested_summary_json(self):
        class NestedSummaryRuntime:
            def chat(self, *, user_id, message, session_id=None, metadata=None):
                return SimpleNamespace(
                    answer=(
                        '{"summary":"<think>hidden</think>\\n\\n'
                        '{\\"summary\\": \\"Used iPhone 13 prices are roughly 1300-3000 RMB.\\", '
                        '\\"items\\": [{\\"grade\\": \\"95 new\\"}], '
                        '\\"next_action\\": \\"Beware of \\"trap phones\\"\\"}", '
                        '"items": [], "next_action": "Hidden outer action"}'
                    ),
                    session_id="session-nested",
                    completed=True,
                    steps=[],
                )

        client = TestClient(create_app(chat_runtime=NestedSummaryRuntime()))
        chat = client.post(
            "/api/chat",
            json={
                "user_id": "anonymous-user-1",
                "message": "hello",
            },
        )

        self.assertEqual(chat.status_code, 200)
        self.assertEqual(chat.json()["answer"], "Used iPhone 13 prices are roughly 1300-3000 RMB.")

    def test_topics_list_and_detail(self):
        with TemporaryDirectory() as temp_dir:
            topics_dir = Path(temp_dir)
            topic_path = topics_dir / "test-topic.md"
            topic_path.write_text("# Test Topic\n\nThis is a topic summary.\n\n## Timeline\n\n- Node", encoding="utf-8")

            web_app = importlib.import_module("topic_pulse_v2_chat.web.app")

            original_topics_dir = web_app.TOPICS_DIR
            web_app.TOPICS_DIR = topics_dir
            try:
                client = TestClient(create_app(chat_runtime=FakeChatRuntime()))

                topics = client.get("/api/topics")
                detail = client.get("/api/topics/test-topic")

                self.assertEqual(topics.status_code, 200)
                self.assertEqual(topics.json()["topics"][0]["title"], "Test Topic")
                self.assertEqual(detail.status_code, 200)
                self.assertIn("This is a topic summary.", detail.json()["content"])
            finally:
                web_app.TOPICS_DIR = original_topics_dir

    def test_sessions_list_and_detail_from_markdown_history(self):
        with TemporaryDirectory() as temp_dir:
            sessions_dir = Path(temp_dir)
            session_path = sessions_dir / "session-existing.md"
            session_path.write_text(
                "# Session session-existing\n\n"
                "## Messages\n\n"
                "<!-- message\n"
                '{"role": "user", "created_at": "2026-08-05T10:00:00+00:00", "metadata": {"type": "user_input"}}\n'
                "-->\n"
                "hello\n"
                "<!-- /message -->\n\n"
                "<!-- message\n"
                '{"role": "assistant", "created_at": "2026-08-05T10:00:01+00:00", "metadata": {"type": "final_answer", "completed": true}}\n'
                "-->\n"
                '<think>internal reasoning should be hidden</think>\n\n'
                '{"thought":"hidden",'
                '"final_answer":"{\\"summary\\":\\"## Insight\\\\n\\\\n- Alpha\\",'
                '\\"items\\":[],\\"next_action\\":\\"Hidden action\\"}"}\n'
                "<!-- /message -->\n\n",
                encoding="utf-8",
            )

            web_app = importlib.import_module("topic_pulse_v2_chat.web.app")

            original_session_data_dir = web_app.SESSION_DATA_DIR
            web_app.SESSION_DATA_DIR = sessions_dir
            try:
                client = TestClient(create_app(chat_runtime=FakeChatRuntime()))

                sessions = client.get("/api/sessions")
                detail = client.get("/api/sessions/session-existing")

                self.assertEqual(sessions.status_code, 200)
                self.assertEqual(sessions.json()["sessions"][0]["id"], "session-existing")
                self.assertEqual(sessions.json()["sessions"][0]["title"], "hello")
                self.assertEqual(detail.status_code, 200)
                self.assertEqual(detail.json()["messages"][0]["content"], "hello")
                self.assertEqual(detail.json()["messages"][1]["content"], "## Insight\n\n- Alpha")
                self.assertTrue(detail.json()["messages"][1]["completed"])
            finally:
                web_app.SESSION_DATA_DIR = original_session_data_dir


if __name__ == "__main__":
    unittest.main()
