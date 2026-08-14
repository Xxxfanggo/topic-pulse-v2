import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from topic_pulse_v2.topics import SQLiteTopicStore


class SQLiteTopicStoreTests(unittest.TestCase):
    def test_same_title_is_user_scoped_and_uses_id_in_markdown_filename(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = SQLiteTopicStore(
                db_path=root / "topic_pulse.sqlite3",
                topics_dir=root / "topics",
            )

            first = store.create_or_get_topic(user_id="user-1", title="Memory Prices")
            first_again = store.create_or_get_topic(user_id="user-1", title="Memory Prices")
            second_user = store.create_or_get_topic(user_id="user-2", title="Memory Prices")

            self.assertEqual(first.id, first_again.id)
            self.assertNotEqual(first.id, second_user.id)
            self.assertIn(first.id, Path(first.markdown_path).name)
            self.assertIn(second_user.id, Path(second_user.markdown_path).name)
            self.assertNotEqual(first.markdown_path, second_user.markdown_path)
            self.assertEqual([item.id for item in store.list_topics(user_id="user-1")], [first.id])


if __name__ == "__main__":
    unittest.main()
