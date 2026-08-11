import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from topic_pulse_v2.scheduler import (
    ScheduledJob,
    ScheduledTaskRegistry,
    SchedulerService,
    SQLiteSchedulerStore,
)
from topic_pulse_v2.scheduler.tasks import register_builtin_tasks


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


if __name__ == "__main__":
    unittest.main()
