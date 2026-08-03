import io
import unittest
from types import SimpleNamespace

from topic_pulse_v2_chat.terminal import TerminalChatApp


class FakeTerminalChatService:
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
            answer=f"收到：{message}",
            session_id=session_id or "session-1",
            completed=True,
            steps=[object()],
        )


class TerminalChatTests(unittest.TestCase):
    def test_terminal_chat_keeps_session_across_turns(self):
        inputs = iter(["第一轮问题", "第二轮问题", "/exit"])
        output = io.StringIO()
        service = FakeTerminalChatService()
        app = TerminalChatApp(
            chat_service=service,
            user_id="terminal-user-1",
            input_func=lambda prompt: next(inputs),
            output=output,
        )

        exit_code = app.run()

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(service.calls), 2)
        self.assertEqual(service.calls[0]["user_id"], "terminal-user-1")
        self.assertIsNone(service.calls[0]["session_id"])
        self.assertEqual(service.calls[1]["session_id"], "session-1")
        self.assertEqual(service.calls[0]["metadata"]["source"], "terminal")
        self.assertIn("收到：第一轮问题", output.getvalue())
        self.assertIn("收到：第二轮问题", output.getvalue())


if __name__ == "__main__":
    unittest.main()
