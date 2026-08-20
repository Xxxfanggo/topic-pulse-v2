import unittest
import importlib
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch


try:
    from fastapi.testclient import TestClient

    from topic_pulse_v2.auth import AuthService, JwtCodec
    from topic_pulse_v2.session import SQLiteSessionStore
    from topic_pulse_v2.topics import SQLiteTopicStore
    from topic_pulse_v2.tool_register.tools.topic_markdown_store import topic_markdown_store
    from topic_pulse_v2_chat.web import create_app
except ModuleNotFoundError:
    TestClient = None
    create_app = None


class RecordingSender:
    def __init__(self):
        self.messages = []

    def send_verification_code(self, *, email, code, purpose):
        self.messages.append({"email": email, "code": code, "purpose": purpose})


class FakeChatRuntime:
    def __init__(self):
        self.calls = []

    def chat(self, *, user_id, message, session_id=None, metadata=None):
        self.calls.append({"user_id": user_id, "message": message, "session_id": session_id})
        return SimpleNamespace(
            answer="ok",
            session_id=session_id or "session-auth",
            completed=True,
            steps=[],
        )


@unittest.skipIf(TestClient is None, "fastapi is not installed")
class WebAuthApiTests(unittest.TestCase):
    def _auth_service(self, root: Path, sender: RecordingSender) -> AuthService:
        return AuthService(
            path=root / "auth.sqlite3",
            sender=sender,
            jwt_codec=JwtCodec("test-secret"),
        )

    def test_email_code_registration_login_and_me(self):
        with TemporaryDirectory() as temp_dir:
            sender = RecordingSender()
            auth = self._auth_service(Path(temp_dir), sender)
            client = TestClient(create_app(auth_service=auth, chat_runtime=FakeChatRuntime()))

            requested = client.post("/api/auth/register/request-code", json={"email": "USER@example.com"})
            self.assertEqual(requested.status_code, 200)
            self.assertEqual(sender.messages[0]["email"], "user@example.com")

            registered = client.post(
                "/api/auth/register/verify",
                json={
                    "email": "user@example.com",
                    "code": sender.messages[0]["code"],
                    "password": "password-123",
                },
            )
            self.assertEqual(registered.status_code, 200)
            token = registered.json()["access_token"]
            self.assertEqual(registered.json()["user"]["email"], "user@example.com")

            me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(me.status_code, 200)
            self.assertEqual(me.json()["email"], "user@example.com")

            logged_in = client.post(
                "/api/auth/login",
                json={"email": "user@example.com", "password": "password-123"},
            )
            self.assertEqual(logged_in.status_code, 200)
            self.assertIn("access_token", logged_in.json())

    def test_protected_chat_requires_token_and_uses_authenticated_user(self):
        with TemporaryDirectory() as temp_dir:
            sender = RecordingSender()
            auth = self._auth_service(Path(temp_dir), sender)
            runtime = FakeChatRuntime()
            client = TestClient(create_app(auth_service=auth, chat_runtime=runtime))

            unauthorized = client.post("/api/chat", json={"message": "hello", "user_id": "spoofed"})
            self.assertEqual(unauthorized.status_code, 401)

            client.post("/api/auth/register/request-code", json={"email": "owner@example.com"})
            token_response = client.post(
                "/api/auth/register/verify",
                json={
                    "email": "owner@example.com",
                    "code": sender.messages[0]["code"],
                    "password": "password-123",
                },
            )
            token = token_response.json()["access_token"]

            chat = client.post(
                "/api/chat",
                headers={"Authorization": f"Bearer {token}"},
                json={"message": "hello", "user_id": "spoofed"},
            )
            self.assertEqual(chat.status_code, 200)
            self.assertEqual(chat.json()["user_id"], token_response.json()["user"]["id"])
            self.assertEqual(runtime.calls[0]["user_id"], token_response.json()["user"]["id"])

    def test_guest_identity_can_use_authenticated_apis(self):
        with TemporaryDirectory() as temp_dir:
            sender = RecordingSender()
            auth = self._auth_service(Path(temp_dir), sender)
            runtime = FakeChatRuntime()
            client = TestClient(create_app(auth_service=auth, chat_runtime=runtime))
            headers = {"X-Guest-Id": "guest_browser-123456"}

            me = client.get("/api/auth/me", headers=headers)
            chat = client.post("/api/chat", headers=headers, json={"message": "hello"})

            self.assertEqual(me.status_code, 200)
            self.assertEqual(me.json()["id"], "guest_browser-123456")
            self.assertTrue(me.json()["is_guest"])
            self.assertEqual(chat.status_code, 200)
            self.assertEqual(chat.json()["user_id"], "guest_browser-123456")
            self.assertEqual(runtime.calls[0]["user_id"], "guest_browser-123456")

    def test_guest_can_create_at_most_three_sessions(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sender = RecordingSender()
            auth = self._auth_service(root, sender)
            runtime = FakeChatRuntime()
            session_store = SQLiteSessionStore(db_path=root / "sessions.sqlite3", sessions_dir=root / "sessions")
            web_app_module = importlib.import_module("topic_pulse_v2_chat.web.app")
            guest_id = "guest_browser-123456"

            for index in range(3):
                record = session_store.create_or_get_session(user_id=guest_id, session_id=f"session-{index}")
                Path(record.markdown_path).write_text(
                    "# Session\n\n## Messages\n\n"
                    "<!-- message\n"
                    '{"role": "user", "created_at": "2026-08-05T10:00:00+00:00", "metadata": {"type": "user_input"}}\n'
                    "-->\n"
                    "hello\n"
                    "<!-- /message -->\n\n",
                    encoding="utf-8",
                )

            with patch.object(web_app_module, "_session_index_store", return_value=session_store):
                client = TestClient(create_app(auth_service=auth, chat_runtime=runtime))
                blocked = client.post(
                    "/api/chat",
                    headers={"X-Guest-Id": guest_id},
                    json={"message": "new chat"},
                )
                existing = client.post(
                    "/api/chat",
                    headers={"X-Guest-Id": guest_id},
                    json={"message": "continue", "session_id": "session-1"},
                )

            self.assertEqual(blocked.status_code, 403)
            self.assertIn("访客最多创建 3 个对话", blocked.json()["detail"])
            self.assertEqual(existing.status_code, 200)
            self.assertEqual(runtime.calls[0]["session_id"], "session-1")

    def test_guest_can_create_at_most_three_topics(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            topic_store = SQLiteTopicStore(db_path=root / "topics.sqlite3", topics_dir=root / "topics")
            tool_module = importlib.import_module("topic_pulse_v2.tool_register.tools.topic_markdown_store")
            guest_id = "guest_browser-123456"

            with patch.object(tool_module, "SQLiteTopicStore", return_value=topic_store):
                for index in range(3):
                    result = topic_markdown_store(
                        f"Topic {index}",
                        summary="summary",
                        root_dir=str(root / "topics"),
                        user_id=guest_id,
                    )
                    self.assertTrue(result["created"])

                with self.assertRaises(ValueError) as context:
                    topic_markdown_store(
                        "Topic 4",
                        summary="summary",
                        root_dir=str(root / "topics"),
                        user_id=guest_id,
                    )

            self.assertIn("访客最多创建 3 个话题", str(context.exception))

    def test_topics_are_scoped_to_authenticated_user(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sender = RecordingSender()
            auth = self._auth_service(root, sender)
            topic_store = SQLiteTopicStore(db_path=root / "topics.sqlite3", topics_dir=root / "topics")
            web_app_module = importlib.import_module("topic_pulse_v2_chat.web.app")

            client = TestClient(create_app(auth_service=auth, chat_runtime=FakeChatRuntime()))
            client.post("/api/auth/register/request-code", json={"email": "one@example.com"})
            user_one = client.post(
                "/api/auth/register/verify",
                json={"email": "one@example.com", "code": sender.messages[-1]["code"], "password": "password-123"},
            ).json()
            client.post("/api/auth/register/request-code", json={"email": "two@example.com"})
            user_two = client.post(
                "/api/auth/register/verify",
                json={"email": "two@example.com", "code": sender.messages[-1]["code"], "password": "password-123"},
            ).json()

            topic_one = topic_store.create_or_get_topic(user_id=user_one["user"]["id"], title="Memory Prices")
            topic_two = topic_store.create_or_get_topic(user_id=user_two["user"]["id"], title="Memory Prices")
            Path(topic_one.markdown_path).write_text("# Memory Prices\n\nUser one topic.", encoding="utf-8")
            Path(topic_two.markdown_path).write_text("# Memory Prices\n\nUser two topic.", encoding="utf-8")

            with patch.object(web_app_module, "_topic_store", return_value=topic_store):
                topics = client.get(
                    "/api/topics",
                    headers={"Authorization": f"Bearer {user_one['access_token']}"},
                )
                own_detail = client.get(
                    f"/api/topics/{topic_one.id}",
                    headers={"Authorization": f"Bearer {user_one['access_token']}"},
                )
                other_detail = client.get(
                    f"/api/topics/{topic_two.id}",
                    headers={"Authorization": f"Bearer {user_one['access_token']}"},
                )

            self.assertEqual(topics.status_code, 200)
            self.assertEqual([item["id"] for item in topics.json()["topics"]], [topic_one.id])
            self.assertEqual(own_detail.status_code, 200)
            self.assertIn("User one topic.", own_detail.json()["content"])
            self.assertEqual(other_detail.status_code, 404)

    def test_sessions_are_scoped_to_authenticated_user(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sender = RecordingSender()
            auth = self._auth_service(root, sender)
            session_store = SQLiteSessionStore(db_path=root / "sessions.sqlite3", sessions_dir=root / "sessions")
            web_app_module = importlib.import_module("topic_pulse_v2_chat.web.app")

            client = TestClient(create_app(auth_service=auth, chat_runtime=FakeChatRuntime()))
            client.post("/api/auth/register/request-code", json={"email": "one@example.com"})
            user_one = client.post(
                "/api/auth/register/verify",
                json={"email": "one@example.com", "code": sender.messages[-1]["code"], "password": "password-123"},
            ).json()
            client.post("/api/auth/register/request-code", json={"email": "two@example.com"})
            user_two = client.post(
                "/api/auth/register/verify",
                json={"email": "two@example.com", "code": sender.messages[-1]["code"], "password": "password-123"},
            ).json()

            session_one = session_store.create_or_get_session(user_id=user_one["user"]["id"], session_id="session-one")
            session_two = session_store.create_or_get_session(user_id=user_two["user"]["id"], session_id="session-two")
            Path(session_one.markdown_path).write_text(
                "# Session session-one\n\n## Messages\n\n"
                "<!-- message\n"
                '{"role": "user", "created_at": "2026-08-05T10:00:00+00:00", "metadata": {"type": "user_input"}}\n'
                "-->\n"
                "hello from one\n"
                "<!-- /message -->\n\n",
                encoding="utf-8",
            )
            Path(session_two.markdown_path).write_text(
                "# Session session-two\n\n## Messages\n\n"
                "<!-- message\n"
                '{"role": "user", "created_at": "2026-08-05T10:00:00+00:00", "metadata": {"type": "user_input"}}\n'
                "-->\n"
                "hello from two\n"
                "<!-- /message -->\n\n",
                encoding="utf-8",
            )

            with patch.object(web_app_module, "_session_index_store", return_value=session_store):
                sessions = client.get(
                    "/api/sessions",
                    headers={"Authorization": f"Bearer {user_one['access_token']}"},
                )
                own_detail = client.get(
                    "/api/sessions/session-one",
                    headers={"Authorization": f"Bearer {user_one['access_token']}"},
                )
                other_detail = client.get(
                    "/api/sessions/session-two",
                    headers={"Authorization": f"Bearer {user_one['access_token']}"},
                )

            self.assertEqual(sessions.status_code, 200)
            self.assertEqual([item["id"] for item in sessions.json()["sessions"]], ["session-one"])
            self.assertEqual(own_detail.status_code, 200)
            self.assertEqual(own_detail.json()["messages"][0]["content"], "hello from one")
            self.assertEqual(other_detail.status_code, 404)


if __name__ == "__main__":
    unittest.main()
