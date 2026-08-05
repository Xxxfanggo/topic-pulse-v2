import tempfile
import unittest
from pathlib import Path

from topic_pulse_v2.session import MarkdownSessionHistoryStore, SessionMessage


class SessionHistoryTests(unittest.TestCase):
    def test_markdown_session_history_store_appends_and_reads_messages(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MarkdownSessionHistoryStore(temp_dir)
            session_id = "session-1"

            store.append(
                session_id,
                SessionMessage(
                    role="user",
                    content="帮我关注内存条价格走势",
                    metadata={"type": "user_input"},
                ),
            )
            store.append(
                session_id,
                SessionMessage(
                    role="assistant",
                    content='{"回答": "已记录"}',
                    metadata={"type": "final_answer", "completed": True},
                ),
            )

            messages = store.list(session_id)
            path = Path(temp_dir) / "session-1.md"

            self.assertTrue(path.exists())
            self.assertEqual([message.role for message in messages], ["user", "assistant"])
            self.assertEqual(messages[0].content, "帮我关注内存条价格走势")
            self.assertEqual(messages[1].metadata["completed"], True)


if __name__ == "__main__":
    unittest.main()
