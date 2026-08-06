import importlib
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
