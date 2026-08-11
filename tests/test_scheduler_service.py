import tempfile
import unittest
from pathlib import Path

from topic_pulse_v2.scheduler import (
    ScheduledJob,
    ScheduledTaskRegistry,
    SchedulerService,
    SQLiteSchedulerStore,
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


if __name__ == "__main__":
    unittest.main()
