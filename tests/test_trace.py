import json
import tempfile
import unittest
from pathlib import Path

from topic_pulse_v2.trace import log_event


class TraceTests(unittest.TestCase):
    def test_log_event_writes_jsonl(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "trace.jsonl"

            log_event(
                str(path),
                "tool_request",
                session_id="session-1",
                step_index=1,
                data={"name": "echo", "arguments": {"value": "测试"}},
            )

            event = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(event["type"], "tool_request")
            self.assertEqual(event["session_id"], "session-1")
            self.assertEqual(event["step_index"], 1)
            self.assertEqual(event["data"]["arguments"], {"value": "测试"})

    def test_log_event_writes_newest_event_first(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "trace.jsonl"

            log_event(str(path), "first", data={"order": 1})
            log_event(str(path), "second", data={"order": 2})

            events = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
            ]

            self.assertEqual([event["type"] for event in events], ["second", "first"])
            self.assertTrue(all(event["timestamp"] for event in events))


if __name__ == "__main__":
    unittest.main()
