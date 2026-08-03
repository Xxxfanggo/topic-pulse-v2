import unittest


try:
    from fastapi.testclient import TestClient

    from topic_pulse_v2_chat.web import create_app
except ModuleNotFoundError:
    TestClient = None
    create_app = None


@unittest.skipIf(TestClient is None, "fastapi is not installed")
class ChatWebAppTests(unittest.TestCase):
    def test_health_and_chat_placeholder(self):
        client = TestClient(create_app())

        health = client.get("/api/health")
        chat = client.post("/api/chat", json={"message": "你好"})

        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")
        self.assertEqual(chat.status_code, 200)
        self.assertIn("session_id", chat.json())
        self.assertIn("前后端框架已就绪", chat.json()["answer"])


if __name__ == "__main__":
    unittest.main()
