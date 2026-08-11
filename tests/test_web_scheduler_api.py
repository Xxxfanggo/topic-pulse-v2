import importlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

try:
    from fastapi.testclient import TestClient

    from topic_pulse_v2.scheduler import SchedulerService, ScheduledTaskRegistry, SQLiteSchedulerStore
    from topic_pulse_v2.scheduler.tasks import register_builtin_tasks
    from topic_pulse_v2_chat.web import create_app
except ModuleNotFoundError:
    TestClient = None
    create_app = None


class FakeChatRuntime:
    def chat(self, *, user_id, message, session_id=None, metadata=None):
        raise AssertionError("chat should not be called")


@unittest.skipIf(TestClient is None, "fastapi is not installed")
class WebSchedulerApiTests(unittest.TestCase):
    def _scheduler_service(self, db_path: Path) -> SchedulerService:
        registry = ScheduledTaskRegistry()
        register_builtin_tasks(registry)
        return SchedulerService(
            store=SQLiteSchedulerStore(path=db_path),
            registry=registry,
            enabled=False,
        )

    def test_topic_refresh_schedule_lifecycle(self):
        with TemporaryDirectory() as temp_dir:
            web_app_module = importlib.import_module("topic_pulse_v2_chat.web.app")
            root = Path(temp_dir)
            topics_dir = root / "topics"
            topics_dir.mkdir()
            (topics_dir / "memory-prices.md").write_text(
                "# Memory Prices\n\n## Summary\n\nTracked topic.\n",
                encoding="utf-8",
            )
            scheduler = self._scheduler_service(root / "topic_pulse.sqlite3")

            with patch.object(web_app_module, "TOPICS_DIR", topics_dir):
                with TestClient(
                    create_app(
                        chat_runtime=FakeChatRuntime(),
                        scheduler_service=scheduler,
                    )
                ) as client:
                    created = client.post(
                        "/api/topics/memory-prices/schedule",
                        json={"trigger": "interval", "interval_minutes": 30},
                    )
                    duplicate = client.post(
                        "/api/topics/memory-prices/schedule",
                        json={"trigger": "interval", "interval_minutes": 60},
                    )
                    topic_schedule = client.get("/api/topics/memory-prices/schedule")
                    jobs = client.get("/api/scheduler/jobs")

                    self.assertEqual(created.status_code, 200)
                    self.assertEqual(created.json()["task_name"], "refresh_topic")
                    self.assertEqual(created.json()["trigger_args"], {"minutes": 30})
                    self.assertEqual(created.json()["metadata"]["topic_id"], "memory-prices")
                    self.assertEqual(duplicate.json()["id"], created.json()["id"])
                    self.assertEqual(duplicate.json()["trigger_args"], {"minutes": 30})
                    self.assertEqual(topic_schedule.json()["id"], created.json()["id"])
                    self.assertEqual(len(jobs.json()["jobs"]), 1)

                    job_id = created.json()["id"]
                    paused = client.post(f"/api/scheduler/jobs/{job_id}/pause")
                    resumed = client.post(f"/api/scheduler/jobs/{job_id}/resume")
                    run = client.post(f"/api/scheduler/jobs/{job_id}/run")
                    runs = client.get(f"/api/scheduler/jobs/{job_id}/runs")

                    self.assertEqual(paused.json()["status"], "paused")
                    self.assertEqual(resumed.json()["status"], "active")
                    self.assertEqual(run.status_code, 200)
                    self.assertEqual(run.json()["status"], "success")
                    self.assertEqual(runs.status_code, 200)
                    self.assertEqual(runs.json()["runs"][0]["job_id"], job_id)

    def test_topic_schedule_returns_not_found_for_missing_topic(self):
        with TemporaryDirectory() as temp_dir:
            web_app_module = importlib.import_module("topic_pulse_v2_chat.web.app")
            root = Path(temp_dir)
            topics_dir = root / "topics"
            topics_dir.mkdir()
            scheduler = self._scheduler_service(root / "topic_pulse.sqlite3")

            with patch.object(web_app_module, "TOPICS_DIR", topics_dir):
                with TestClient(
                    create_app(
                        chat_runtime=FakeChatRuntime(),
                        scheduler_service=scheduler,
                    )
                ) as client:
                    response = client.post(
                        "/api/topics/missing/schedule",
                        json={"trigger": "interval", "interval_minutes": 30},
                    )

            self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
