import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from topic_pulse_v2.tool_register.tools.topic_markdown_read import topic_markdown_read_summary
from topic_pulse_v2.tool_register.tools.topic_markdown_store import topic_markdown_store
from topic_pulse_v2.topics import SQLiteTopicStore


class TopicMarkdownUserScopeTests(unittest.TestCase):
    def test_store_creates_user_scoped_topic_record_and_id_based_file(self):
        original_cwd = os.getcwd()
        with TemporaryDirectory() as temp_dir:
            os.chdir(temp_dir)
            try:
                result = topic_markdown_store(
                    "Memory Prices",
                    user_id="user-1",
                    root_dir="data/topics",
                    summary="Tracked memory price movement.",
                    timeline_items=[
                        {
                            "date": "2026-08-14",
                            "title": "DDR5 prices rise",
                            "source": "Example",
                            "url": "https://example.com",
                            "summary": "Prices moved higher.",
                        }
                    ],
                )

                store = SQLiteTopicStore()
                records = store.list_topics(user_id="user-1")
                summaries = topic_markdown_read_summary(user_id="user-1", root_dir="data/topics")
            finally:
                os.chdir(original_cwd)

        self.assertEqual(len(records), 1)
        self.assertEqual(result["topic_id"], records[0].id)
        self.assertIn(records[0].id, Path(records[0].markdown_path).name)
        self.assertEqual(summaries["count"], 1)
        self.assertEqual(summaries["topics"][0]["topic_id"], records[0].id)


if __name__ == "__main__":
    unittest.main()
