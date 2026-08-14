import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from topic_pulse_v2.session import SessionManager, SQLiteSessionStore


class SQLiteSessionStoreTests(unittest.TestCase):
    def test_sessions_are_user_scoped(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = SQLiteSessionStore(
                db_path=root / "topic_pulse.sqlite3",
                sessions_dir=root / "sessions",
            )

            first = store.create_or_get_session(user_id="user-1", session_id="session-1")
            first_again = store.create_or_get_session(user_id="user-1", session_id="session-1")
            other_user = store.create_or_get_session(user_id="user-2", session_id="session-2")

            self.assertEqual(first.markdown_path, first_again.markdown_path)
            self.assertEqual(other_user.id, "session-2")
            self.assertEqual(store.list_sessions(user_id="user-1")[0].user_id, "user-1")
            self.assertIsNone(store.get_session(user_id="user-1", session_id="missing"))

    def test_session_manager_writes_user_scoped_history_and_index(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = SQLiteSessionStore(
                db_path=root / "topic_pulse.sqlite3",
                sessions_dir=root / "sessions",
            )
            manager = SessionManager(session_store=store)

            session = manager.create(user_id="user-1")
            manager.append_history(session.id, "user", "hello")

            records = store.list_sessions(user_id="user-1")
            history = manager.get_history(session.id)

            self.assertEqual([item.id for item in records], [session.id])
            self.assertTrue(Path(records[0].markdown_path).exists())
            self.assertEqual(history[0].content, "hello")


if __name__ == "__main__":
    unittest.main()
