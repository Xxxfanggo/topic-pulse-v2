import json
import tempfile
import unittest
from pathlib import Path

from topic_pulse_v2.trace import log_event, resolve_trace_log_path


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

            partition_path = resolve_trace_log_path(str(path))
            event = json.loads(partition_path.read_text(encoding="utf-8"))

            self.assertEqual(event["type"], "tool_request")
            self.assertEqual(event["session_id"], "session-1")
            self.assertEqual(event["step_index"], 1)
            self.assertEqual(event["data"]["arguments"], {"value": "测试"})
            self.assertEqual(partition_path.parent.name, "trace")
            self.assertEqual(partition_path.suffix, ".jsonl")

    def test_log_event_appends_events_to_daily_partition(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "trace.jsonl"

            log_event(str(path), "first", data={"order": 1})
            log_event(str(path), "second", data={"order": 2})

            partition_path = resolve_trace_log_path(str(path))
            events = [
                json.loads(line)
                for line in partition_path.read_text(encoding="utf-8").splitlines()
            ]

            self.assertEqual([event["type"] for event in events], ["first", "second"])
            self.assertTrue(all(event["timestamp"] for event in events))
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
