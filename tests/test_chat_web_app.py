import unittest
import importlib
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
            answer="这是 ReActAgent 的模拟回复",
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
                "message": "关注最近互联网大厂因 AI 裁员的信息",
                "session_id": "session-existing",
                "history": [{"role": "user", "content": "你好"}],
            },
        )

        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")
        self.assertEqual(chat.status_code, 200)
        self.assertEqual(chat.json()["answer"], "这是 ReActAgent 的模拟回复")
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
                "message": "你好",
            },
        )

        self.assertEqual(chat.status_code, 503)
        self.assertIn("模型服务暂时不可用", chat.json()["detail"])

    def test_chat_formats_structured_answer_for_display(self):
        class StructuredRuntime:
            def chat(self, *, user_id, message, session_id=None, metadata=None):
                return SimpleNamespace(
                    answer='{"summary":"你好，我可以帮你追踪热点。","items":[],"next_action":"请补充具体话题。"}',
                    session_id="session-structured",
                    completed=True,
                    steps=[],
                )

        client = TestClient(create_app(chat_runtime=StructuredRuntime()))
        chat = client.post(
            "/api/chat",
            json={
                "user_id": "anonymous-user-1",
                "message": "你好",
            },
        )

        self.assertEqual(chat.status_code, 200)
        self.assertEqual(chat.json()["answer"], "你好，我可以帮你追踪热点。\n\n请补充具体话题。")

    def test_chat_formats_think_prefixed_structured_answer_for_display(self):
        class ThinkStructuredRuntime:
            def chat(self, *, user_id, message, session_id=None, metadata=None):
                return SimpleNamespace(
                    answer='<think>内部推理</think>\n\n{"summary":"已整理完成。","items":[],"next_action":"可以继续追问。"}',
                    session_id="session-structured",
                    completed=True,
                    steps=[],
                )

        client = TestClient(create_app(chat_runtime=ThinkStructuredRuntime()))
        chat = client.post(
            "/api/chat",
            json={
                "user_id": "anonymous-user-1",
                "message": "你好",
            },
        )

        self.assertEqual(chat.status_code, 200)
        self.assertEqual(chat.json()["answer"], "已整理完成。\n\n可以继续追问。")

    def test_topics_list_and_detail(self):
        with TemporaryDirectory() as temp_dir:
            topics_dir = Path(temp_dir)
            topic_path = topics_dir / "测试话题.md"
            topic_path.write_text("# 测试话题\n\n这是一段话题摘要。\n\n## 时间线\n\n- 节点", encoding="utf-8")

            web_app = importlib.import_module("topic_pulse_v2_chat.web.app")

            original_topics_dir = web_app.TOPICS_DIR
            web_app.TOPICS_DIR = topics_dir
            try:
                client = TestClient(create_app(chat_runtime=FakeChatRuntime()))

                topics = client.get("/api/topics")
                detail = client.get("/api/topics/%E6%B5%8B%E8%AF%95%E8%AF%9D%E9%A2%98")

                self.assertEqual(topics.status_code, 200)
                self.assertEqual(topics.json()["topics"][0]["title"], "测试话题")
                self.assertEqual(detail.status_code, 200)
                self.assertIn("这是一段话题摘要", detail.json()["content"])
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
                "你好\n"
                "<!-- /message -->\n\n"
                "<!-- message\n"
                '{"role": "assistant", "created_at": "2026-08-05T10:00:01+00:00", "metadata": {"type": "final_answer", "completed": true}}\n'
                "-->\n"
                '<think>内部推理不应该展示</think>\n\n'
                '{"thought":"用户说了"你好"，需要引导",'
                '"final_answer":"{\\"summary\\":\\"你好，我可以帮你追踪热点。\\",'
                '\\"items\\":[],\\"next_action\\":\\"请补充具体话题。\\"}"}\n'
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
                self.assertEqual(sessions.json()["sessions"][0]["title"], "你好")
                self.assertEqual(detail.status_code, 200)
                self.assertEqual(detail.json()["messages"][0]["content"], "你好")
                self.assertEqual(
                    detail.json()["messages"][1]["content"],
                    "你好，我可以帮你追踪热点。\n\n请补充具体话题。",
                )
                self.assertTrue(detail.json()["messages"][1]["completed"])
            finally:
                web_app.SESSION_DATA_DIR = original_session_data_dir


if __name__ == "__main__":
    unittest.main()
