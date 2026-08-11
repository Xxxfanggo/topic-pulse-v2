import tempfile
import unittest
from pathlib import Path

from topic_pulse_v2.scheduler import ScheduledJob, SQLiteSchedulerStore
from topic_pulse_v2.scheduler.models import JobRun


class SchedulerStoreTests(unittest.TestCase):
    def test_save_and_list_jobs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SQLiteSchedulerStore(path=Path(temp_dir) / "scheduler.sqlite3")
            try:
                store.initialize()
                job = ScheduledJob(
                    id="job-1",
                    name="Refresh memory prices",
                    task_name="refresh_topic",
                    trigger="interval",
                    trigger_args={"minutes": 10},
                    kwargs={"topic_name": "memory prices"},
                    metadata={"owner": "test"},
                )

                store.save_job(job)

                saved = store.get_job("job-1")
                self.assertEqual(saved.task_name, "refresh_topic")
                self.assertEqual(saved.trigger_args, {"minutes": 10})
                self.assertEqual(saved.kwargs, {"topic_name": "memory prices"})
                self.assertEqual(saved.metadata, {"owner": "test"})
                self.assertEqual([item.id for item in store.list_jobs()], ["job-1"])
            finally:
                store.close()

    def test_save_and_list_runs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SQLiteSchedulerStore(path=Path(temp_dir) / "scheduler.sqlite3")
            try:
                store.initialize()
                store.save_job(
                    ScheduledJob(
                        id="job-1",
                        task_name="refresh_topic",
                        trigger="cron",
                        trigger_args={"hour": 9},
                    )
                )
                store.save_run(
                    JobRun(
                        id="run-1",
                        job_id="job-1",
                        task_name="refresh_topic",
                        status="success",
                        result_summary="done",
                    )
                )

                runs = store.list_runs("job-1")

                self.assertEqual(len(runs), 1)
                self.assertEqual(runs[0].id, "run-1")
                self.assertEqual(runs[0].status, "success")
                self.assertEqual(runs[0].result_summary, "done")
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
