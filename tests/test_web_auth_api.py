import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace


try:
    from fastapi.testclient import TestClient

    from topic_pulse_v2.auth import AuthService, JwtCodec
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


if __name__ == "__main__":
    unittest.main()
