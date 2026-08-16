import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from topic_pulse_v2.config import (
    app_data_dir,
    database_path,
    hotspot_trace_log_path,
    load_env_file,
    logs_dir,
    react_trace_log_path,
    session_data_dir,
    topics_dir,
)


class EnvLoaderTests(unittest.TestCase):
    def test_load_env_file_sets_values_without_overriding_existing_env(self):
        with TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "SMTP_HOST=smtp.qq.com",
                        "SMTP_FROM_NAME=\"Topic Pulse\"",
                        "EXISTING=value-from-file",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"EXISTING": "keep-me"}, clear=False):
                loaded = load_env_file(env_path)
                self.assertEqual(loaded, env_path)
                self.assertEqual(os.environ["SMTP_HOST"], "smtp.qq.com")
                self.assertEqual(os.environ["SMTP_FROM_NAME"], "Topic Pulse")
                self.assertEqual(os.environ["EXISTING"], "keep-me")

    def test_runtime_paths_follow_configured_data_dir(self):
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "runtime-data"

            with patch.dict(os.environ, {"TOPIC_PULSE_DATA_DIR": str(data_dir)}, clear=False):
                self.assertEqual(app_data_dir(), data_dir)
                self.assertEqual(database_path(), data_dir / "topic_pulse.sqlite3")
                self.assertEqual(topics_dir(), data_dir / "topics")
                self.assertEqual(session_data_dir(), data_dir / "session")
                self.assertEqual(logs_dir(), data_dir / "logs")
                self.assertEqual(react_trace_log_path(), data_dir / "logs" / "react_trace.jsonl")
                self.assertEqual(hotspot_trace_log_path(), data_dir / "logs" / "hotspot_agent_trace.jsonl")

    def test_default_runtime_components_use_configured_data_dir(self):
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "runtime-data"

            with patch.dict(os.environ, {"TOPIC_PULSE_DATA_DIR": str(data_dir)}, clear=False):
                from topic_pulse_v2.process import HotspotAgent, ReActConfig
                from topic_pulse_v2.session import MarkdownSessionHistoryStore, SQLiteSessionStore

                session_index = SQLiteSessionStore()
                history_store = MarkdownSessionHistoryStore()
                react_config = ReActConfig()
                hotspot_agent = HotspotAgent()

                self.assertEqual(session_index.db_path, data_dir / "topic_pulse.sqlite3")
                self.assertEqual(session_index.sessions_dir, data_dir / "session")
                self.assertEqual(history_store.root_dir, data_dir / "session")
                self.assertEqual(react_config.trace_log_path, str(data_dir / "logs" / "react_trace.jsonl"))
                self.assertEqual(
                    hotspot_agent._trace_log_path,
                    str(data_dir / "logs" / "hotspot_agent_trace.jsonl"),
                )


if __name__ == "__main__":
    unittest.main()
