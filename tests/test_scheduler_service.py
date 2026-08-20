import tempfile
import unittest
import json
from pathlib import Path
from types import SimpleNamespace

from topic_pulse_v2.scheduler import (
    ScheduledJob,
    ScheduledTaskRegistry,
    SchedulerService,
    SQLiteSchedulerStore,
)
from topic_pulse_v2.scheduler.tasks import register_builtin_tasks
from topic_pulse_v2.process.hotspot_agent import HotspotRunResult


class RecordingNotificationDispatcher:
    def __init__(self):
        self.events = []

    def dispatch_topic_refresh(self, event):
        self.events.append(event)
        return [SimpleNamespace(status="sent")]


class FakeRefreshChatRuntime:
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
            answer=(
                '{"summary":"已更新话题。","topic_update":'
                '{"topic_name":"Memory Prices","status":"updated_with_new_items",'
                '"new_count":2,"existing_count":5,"new_items":[],"existing_items":[]}}'
            ),
            session_id="scheduler-session",
            completed=True,
        )


class FakeHotspotAgent:
    def __init__(self):
        self.calls = []

    def run(self, request):
        self.calls.append(request)
        return HotspotRunResult(
            status="completed",
            date="2026-08-15",
            captured_at="2026-08-15T01:00:00+00:00",
            fetched_count=2,
            normalized_count=2,
            merged_topic_count=1,
            ranking_count=1,
            top_topics=[
                {
                    "rank": 1,
                    "topic_id": "hot_1",
                    "canonical_title": "AI 芯片需求持续升温",
                    "score": 88.0,
                }
            ],
        )


class SchedulerServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_job_now_records_success(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = ScheduledTaskRegistry()
            registry.register("echo", lambda value: f"echo:{value}")
            store = SQLiteSchedulerStore(path=Path(temp_dir) / "topic_pulse.sqlite3")
            try:
                store.initialize()
                store.save_job(
                    ScheduledJob(
                        id="job-1",
                        task_name="echo",
                        trigger="interval",
                        trigger_args={"minutes": 5},
                        args=["hello"],
                    )
                )
                service = SchedulerService(store=store, registry=registry, enabled=False)

                run = await service.run_job_now("job-1")

                self.assertEqual(run.status, "success")
                self.assertEqual(run.result_summary, "echo:hello")
                self.assertEqual(store.list_runs("job-1")[0].status, "success")
            finally:
                store.close()

    async def test_run_job_now_records_failure(self):
        def fail():
            raise ValueError("boom")

        with tempfile.TemporaryDirectory() as temp_dir:
            registry = ScheduledTaskRegistry()
            registry.register("fail", fail)
            store = SQLiteSchedulerStore(path=Path(temp_dir) / "topic_pulse.sqlite3")
            try:
                store.initialize()
                store.save_job(
                    ScheduledJob(
                        id="job-1",
                        task_name="fail",
                        trigger="interval",
                        trigger_args={"minutes": 5},
                    )
                )
                service = SchedulerService(store=store, registry=registry, enabled=False)

                run = await service.run_job_now("job-1")

                self.assertEqual(run.status, "failed")
                self.assertIn("ValueError", run.error)
            finally:
                store.close()

    async def test_refresh_topic_task_uses_chat_runtime_and_records_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            chat_runtime = FakeRefreshChatRuntime()
            registry = ScheduledTaskRegistry()
            register_builtin_tasks(registry, chat_runtime=chat_runtime)
            store = SQLiteSchedulerStore(path=Path(temp_dir) / "topic_pulse.sqlite3")
            try:
                store.initialize()
                store.save_job(
                    ScheduledJob(
                        id="job-refresh",
                        task_name="refresh_topic",
                        trigger="interval",
                        trigger_args={"minutes": 5},
                        kwargs={"topic_name": "Memory Prices"},
                    )
                )
                service = SchedulerService(store=store, registry=registry, enabled=False)

                run = await service.run_job_now("job-refresh")

                self.assertEqual(run.status, "success")
                self.assertIn('"topic_name": "Memory Prices"', run.result_summary)
                self.assertIn('"new_count": 2', run.result_summary)
                self.assertEqual(chat_runtime.calls[0]["user_id"], "scheduler")
                self.assertEqual(chat_runtime.calls[0]["metadata"]["source"], "scheduler")
                self.assertEqual(chat_runtime.calls[0]["metadata"]["task"], "refresh_topic")
                self.assertIn("Memory Prices", chat_runtime.calls[0]["message"])
            finally:
                store.close()

    async def test_refresh_topic_dispatches_notifications_after_success(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            chat_runtime = FakeRefreshChatRuntime()
            dispatcher = RecordingNotificationDispatcher()
            registry = ScheduledTaskRegistry()
            register_builtin_tasks(registry, chat_runtime=chat_runtime)
            store = SQLiteSchedulerStore(path=Path(temp_dir) / "topic_pulse.sqlite3")
            try:
                store.initialize()
                store.save_job(
                    ScheduledJob(
                        id="job-refresh",
                        task_name="refresh_topic",
                        trigger="interval",
                        trigger_args={"minutes": 5},
                        kwargs={"topic_name": "Memory Prices"},
                        metadata={
                            "type": "topic_refresh",
                            "topic_id": "topic-1",
                            "user_id": "user-1",
                        },
                    )
                )
                service = SchedulerService(
                    store=store,
                    registry=registry,
                    enabled=False,
                    notification_dispatcher=dispatcher,
                )

                run = await service.run_job_now("job-refresh")

                self.assertEqual(run.status, "success")
                self.assertEqual(len(dispatcher.events), 1)
                self.assertEqual(dispatcher.events[0].topic_id, "topic-1")
                self.assertEqual(dispatcher.events[0].user_id, "user-1")
                self.assertEqual(run.metadata["notifications"]["sent_count"], 1)
            finally:
                store.close()

    async def test_result_summary_keeps_valid_json_when_summary_is_truncated(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = ScheduledTaskRegistry()
            registry.register(
                "long_summary",
                lambda: {
                    "status": "completed",
                    "topic_name": "Memory Prices",
                    "new_count": 1,
                    "summary": "x" * 800,
                },
            )
            store = SQLiteSchedulerStore(path=Path(temp_dir) / "topic_pulse.sqlite3")
            try:
                store.initialize()
                store.save_job(
                    ScheduledJob(
                        id="job-long-summary",
                        task_name="long_summary",
                        trigger="interval",
                        trigger_args={"minutes": 5},
                    )
                )
                service = SchedulerService(store=store, registry=registry, enabled=False)

                run = await service.run_job_now("job-long-summary")
                payload = json.loads(run.result_summary)

                self.assertEqual(payload["status"], "completed")
                self.assertEqual(payload["new_count"], 1)
                self.assertEqual(len(payload["summary"]), 500)
                self.assertTrue(payload["summary"].endswith("..."))
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
