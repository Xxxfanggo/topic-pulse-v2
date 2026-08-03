import unittest
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


if __name__ == "__main__":
    unittest.main()
