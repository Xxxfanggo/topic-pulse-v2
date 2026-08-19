import tempfile
import unittest
from pathlib import Path

from topic_pulse_v2.scheduler import SQLiteSchedulerStore
from topic_pulse_v2.tool_register import TOPIC_SCHEDULE_CREATE_TOOL_NAME, ToolRegistry, topic_schedule_create
from topic_pulse_v2.tool_register.tools.topic_schedule_create import set_active_topic_schedule_scheduler
from topic_pulse_v2.tool_call import ToolCallRequest, ToolExecutor
from topic_pulse_v2.topics import SQLiteTopicStore


class FakeScheduler:
    def __init__(self):
        self.jobs = []

    def add_job(self, job):
        self.jobs.append(job)
        return job

    def list_jobs(self):
        return list(self.jobs)


class TopicScheduleCreateToolTests(unittest.TestCase):
    def test_creates_refresh_job_for_tracked_topic(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = root / "topic_pulse.sqlite3"
            topics_dir = root / "topics"
            topic_store = SQLiteTopicStore(db_path=db_path, topics_dir=topics_dir)
            topic = topic_store.create_or_get_topic(user_id="user-1", title="Memory Prices")
            Path(topic.markdown_path).write_text("# Memory Prices\n\n## Summary\n\nTracked.\n", encoding="utf-8")

            result = topic_schedule_create(
                "Memory Prices",
                user_id="user-1",
                interval_minutes=30,
                db_path=str(db_path),
                root_dir=str(topics_dir),
            )

            self.assertTrue(result["created"])
            self.assertFalse(result["active_immediately"])
            self.assertEqual(result["job"]["task_name"], "refresh_topic")
            self.assertEqual(result["job"]["trigger_args"], {"minutes": 30})
            self.assertEqual(result["job"]["kwargs"]["topic_name"], "Memory Prices")
            self.assertEqual(result["job"]["kwargs"]["user_id"], "user-1")
            self.assertEqual(result["job"]["metadata"]["topic_id"], topic.id)
            self.assertEqual(result["job"]["metadata"]["user_id"], "user-1")

            store = SQLiteSchedulerStore(path=db_path)
            try:
                store.initialize()
                saved = store.get_job(result["job"]["id"])
                self.assertEqual(saved.task_name, "refresh_topic")
                self.assertEqual(saved.metadata["topic_title"], "Memory Prices")
            finally:
                store.close()

    def test_uses_active_scheduler_when_configured(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = root / "topic_pulse.sqlite3"
            topics_dir = root / "topics"
            topic_store = SQLiteTopicStore(db_path=db_path, topics_dir=topics_dir)
            topic = topic_store.create_or_get_topic(user_id="user-1", title="Memory Prices")
            Path(topic.markdown_path).write_text("# Memory Prices\n", encoding="utf-8")
            scheduler = FakeScheduler()
            set_active_topic_schedule_scheduler(scheduler)
            try:
                result = topic_schedule_create(
                    "Memory Prices",
                    user_id="user-1",
                    trigger="cron",
                    cron_hour=9,
                    cron_minute=30,
                    db_path=str(db_path),
                    root_dir=str(topics_dir),
                )
            finally:
                set_active_topic_schedule_scheduler(None)

            self.assertTrue(result["created"])
            self.assertTrue(result["active_immediately"])
            self.assertEqual(len(scheduler.jobs), 1)
            self.assertEqual(scheduler.jobs[0].trigger, "cron")
            self.assertEqual(scheduler.jobs[0].trigger_args, {"hour": 9, "minute": 30})

    def test_repeated_call_returns_existing_job(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = root / "topic_pulse.sqlite3"
            topics_dir = root / "topics"
            topic_store = SQLiteTopicStore(db_path=db_path, topics_dir=topics_dir)
            topic = topic_store.create_or_get_topic(user_id="user-1", title="Memory Prices")
            Path(topic.markdown_path).write_text("# Memory Prices\n", encoding="utf-8")

            first = topic_schedule_create("Memory Prices", user_id="user-1", db_path=str(db_path), root_dir=str(topics_dir))
            second = topic_schedule_create("Memory Prices", user_id="user-1", db_path=str(db_path), root_dir=str(topics_dir))

            self.assertTrue(first["created"])
            self.assertFalse(second["created"])
            self.assertEqual(first["job"]["id"], second["job"]["id"])

            store = SQLiteSchedulerStore(path=db_path)
            try:
                store.initialize()
                self.assertEqual(len(store.list_jobs()), 1)
            finally:
                store.close()

    def test_cron_requires_hour_and_minute(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = root / "topic_pulse.sqlite3"
            topics_dir = root / "topics"
            topic_store = SQLiteTopicStore(db_path=db_path, topics_dir=topics_dir)
            topic = topic_store.create_or_get_topic(user_id="user-1", title="Memory Prices")
            Path(topic.markdown_path).write_text("# Memory Prices\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                topic_schedule_create(
                    "Memory Prices",
                    user_id="user-1",
                    trigger="cron",
                    db_path=str(db_path),
                    root_dir=str(topics_dir),
                )

    def test_missing_topic_raises_not_found(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with self.assertRaises(FileNotFoundError):
                topic_schedule_create(
                    "Missing",
                    user_id="user-1",
                    db_path=str(root / "topic_pulse.sqlite3"),
                    root_dir=str(root / "topics"),
                )

    def test_guest_user_cannot_create_schedule(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = root / "topic_pulse.sqlite3"
            topics_dir = root / "topics"
            topic_store = SQLiteTopicStore(db_path=db_path, topics_dir=topics_dir)
            topic = topic_store.create_or_get_topic(user_id="guest_browser-1", title="Memory Prices")
            Path(topic.markdown_path).write_text("# Memory Prices\n", encoding="utf-8")

            with self.assertRaises(PermissionError):
                topic_schedule_create(
                    "Memory Prices",
                    user_id="guest_browser-1",
                    db_path=str(db_path),
                    root_dir=str(topics_dir),
                )

    def test_registry_auto_registers_tool_and_injects_user_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = root / "topic_pulse.sqlite3"
            topics_dir = root / "topics"
            topic_store = SQLiteTopicStore(db_path=db_path, topics_dir=topics_dir)
            topic = topic_store.create_or_get_topic(user_id="user-1", title="Memory Prices")
            Path(topic.markdown_path).write_text("# Memory Prices\n", encoding="utf-8")
            registry = ToolRegistry()

            self.assertTrue(registry.has(TOPIC_SCHEDULE_CREATE_TOOL_NAME))

            result = ToolExecutor(registry).call_request(
                ToolCallRequest(
                    name=TOPIC_SCHEDULE_CREATE_TOOL_NAME,
                    arguments={
                        "topic_name": "Memory Prices",
                        "db_path": str(db_path),
                        "root_dir": str(topics_dir),
                    },
                    metadata={"user_id": "user-1"},
                )
            )

            self.assertTrue(result.success)
            self.assertTrue(result.result["created"])


if __name__ == "__main__":
    unittest.main()
