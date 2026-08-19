import asyncio
import importlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

try:
    from fastapi.testclient import TestClient

    from topic_pulse_v2.auth import AuthService, JwtCodec
    from topic_pulse_v2.notifications import SQLiteNotificationStore
    from topic_pulse_v2.scheduler import SchedulerService, ScheduledJob, ScheduledTaskRegistry, SQLiteSchedulerStore
    from topic_pulse_v2.scheduler.tasks import register_builtin_tasks
    from topic_pulse_v2.topics import SQLiteTopicStore
    from topic_pulse_v2_chat.web import create_app
except ModuleNotFoundError:
    TestClient = None
    create_app = None


class FakeChatRuntime:
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
        return type(
            "FakeResult",
            (),
            {
                "answer": '{"summary":"updated","topic_update":{"topic_name":"Memory Prices","new_count":1,"existing_count":3}}',
                "session_id": "scheduler-session",
                "completed": True,
            },
        )()


class RecordingSender:
    def send_verification_code(self, *, email, code, purpose):
        pass


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

    def _auth_service(self, root: Path) -> AuthService:
        return AuthService(
            path=root / "auth.sqlite3",
            sender=RecordingSender(),
            jwt_codec=JwtCodec("test-secret"),
        )

    def test_topic_refresh_schedule_lifecycle(self):
        with TemporaryDirectory() as temp_dir:
            web_app_module = importlib.import_module("topic_pulse_v2_chat.web.app")
            root = Path(temp_dir)
            topics_dir = root / "topics"
            topics_dir.mkdir()
            topic_store = SQLiteTopicStore(db_path=root / "topics.sqlite3", topics_dir=topics_dir)
            topic = topic_store.create_or_get_topic(user_id="anonymous-user-1", title="Memory Prices")
            Path(topic.markdown_path).write_text(
                "# Memory Prices\n\n## Summary\n\nTracked topic.\n",
                encoding="utf-8",
            )
            scheduler = self._scheduler_service(root / "topic_pulse.sqlite3")

            with patch.object(web_app_module, "_topic_store", return_value=topic_store):
                with TestClient(
                    create_app(
                        chat_runtime=FakeChatRuntime(),
                        scheduler_service=scheduler,
                        auth_required=False,
                    )
                ) as client:
                    created = client.post(
                        f"/api/topics/{topic.id}/schedule",
                        json={"trigger": "interval", "interval_minutes": 30},
                    )
                    duplicate = client.post(
                        f"/api/topics/{topic.id}/schedule",
                        json={"trigger": "interval", "interval_minutes": 60},
                    )
                    topic_schedule = client.get(f"/api/topics/{topic.id}/schedule")
                    jobs = client.get("/api/scheduler/jobs")

                    self.assertEqual(created.status_code, 200)
                    self.assertEqual(created.json()["task_name"], "refresh_topic")
                    self.assertEqual(created.json()["trigger_args"], {"minutes": 30})
                    self.assertEqual(created.json()["kwargs"]["user_id"], "anonymous-user-1")
                    self.assertEqual(created.json()["metadata"]["topic_id"], topic.id)
                    self.assertEqual(created.json()["metadata"]["user_id"], "anonymous-user-1")
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

    def test_default_scheduler_uses_app_chat_runtime_for_manual_refresh(self):
        with TemporaryDirectory() as temp_dir:
            web_app_module = importlib.import_module("topic_pulse_v2_chat.web.app")
            root = Path(temp_dir)
            topics_dir = root / "topics"
            topics_dir.mkdir()
            topic_store = SQLiteTopicStore(db_path=root / "topics.sqlite3", topics_dir=topics_dir)
            topic = topic_store.create_or_get_topic(user_id="anonymous-user-1", title="Memory Prices")
            Path(topic.markdown_path).write_text(
                "# Memory Prices\n\n## Summary\n\nTracked topic.\n",
                encoding="utf-8",
            )
            chat_runtime = FakeChatRuntime()

            with patch.object(web_app_module, "_topic_store", return_value=topic_store):
                with patch.object(web_app_module, "SQLiteSchedulerStore") as store_class:
                    store_class.return_value = SQLiteSchedulerStore(path=root / "topic_pulse.sqlite3")
                    with TestClient(create_app(chat_runtime=chat_runtime, auth_required=False)) as client:
                        created = client.post(
                            f"/api/topics/{topic.id}/schedule",
                            json={"trigger": "interval", "interval_minutes": 30},
                        )
                        run = client.post(f"/api/scheduler/jobs/{created.json()['id']}/run")

            self.assertEqual(run.status_code, 200)
            self.assertEqual(run.json()["status"], "success")
            self.assertIn('"new_count": 1', run.json()["result_summary"])
            self.assertEqual(chat_runtime.calls[0]["user_id"], "anonymous-user-1")
            self.assertEqual(chat_runtime.calls[0]["metadata"]["source"], "scheduler")

    def test_topic_refresh_job_backfills_user_id_from_metadata(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            chat_runtime = FakeChatRuntime()
            registry = ScheduledTaskRegistry()
            register_builtin_tasks(registry, chat_runtime=chat_runtime)
            scheduler = SchedulerService(
                store=SQLiteSchedulerStore(path=root / "topic_pulse.sqlite3"),
                registry=registry,
                enabled=False,
            )
            scheduler.start()
            try:
                job = ScheduledJob(
                    id="legacy-topic-refresh",
                    task_name="refresh_topic",
                    trigger="interval",
                    trigger_args={"minutes": 30},
                    kwargs={"topic_name": "Memory Prices"},
                    metadata={
                        "type": "topic_refresh",
                        "topic_id": "topic-1",
                        "user_id": "user-from-metadata",
                    },
                )
                scheduler.add_job(job)

                run = asyncio.run(scheduler.run_job_now(job.id))
            finally:
                scheduler.shutdown()

            self.assertEqual(run.status, "success")
            self.assertEqual(chat_runtime.calls[0]["user_id"], "user-from-metadata")

    def test_topic_schedule_returns_not_found_for_missing_topic(self):
        with TemporaryDirectory() as temp_dir:
            web_app_module = importlib.import_module("topic_pulse_v2_chat.web.app")
            root = Path(temp_dir)
            topics_dir = root / "topics"
            topics_dir.mkdir()
            topic_store = SQLiteTopicStore(db_path=root / "topics.sqlite3", topics_dir=topics_dir)
            scheduler = self._scheduler_service(root / "topic_pulse.sqlite3")

            with patch.object(web_app_module, "_topic_store", return_value=topic_store):
                with TestClient(
                    create_app(
                        chat_runtime=FakeChatRuntime(),
                        scheduler_service=scheduler,
                        auth_required=False,
                    )
                ) as client:
                    response = client.post(
                        "/api/topics/missing/schedule",
                        json={"trigger": "interval", "interval_minutes": 30},
                    )

            self.assertEqual(response.status_code, 404)

    def test_guest_cannot_create_topic_refresh_schedule(self):
        with TemporaryDirectory() as temp_dir:
            web_app_module = importlib.import_module("topic_pulse_v2_chat.web.app")
            root = Path(temp_dir)
            topics_dir = root / "topics"
            topics_dir.mkdir()
            guest_id = "guest_browser-123456"
            topic_store = SQLiteTopicStore(db_path=root / "topics.sqlite3", topics_dir=topics_dir)
            topic = topic_store.create_or_get_topic(user_id=guest_id, title="Memory Prices")
            Path(topic.markdown_path).write_text(
                "# Memory Prices\n\n## Summary\n\nTracked topic.\n",
                encoding="utf-8",
            )
            scheduler = self._scheduler_service(root / "topic_pulse.sqlite3")

            with patch.object(web_app_module, "_topic_store", return_value=topic_store):
                with TestClient(
                    create_app(
                        chat_runtime=FakeChatRuntime(),
                        scheduler_service=scheduler,
                        auth_service=self._auth_service(root),
                    )
                ) as client:
                    response = client.post(
                        f"/api/topics/{topic.id}/schedule",
                        headers={"X-Guest-Id": guest_id},
                        json={"trigger": "interval", "interval_minutes": 30},
                    )

            self.assertEqual(response.status_code, 403)
            self.assertIn("访客不能创建定时调度任务", response.json()["detail"])

    def test_topic_email_notification_subscription_api(self):
        with TemporaryDirectory() as temp_dir:
            web_app_module = importlib.import_module("topic_pulse_v2_chat.web.app")
            root = Path(temp_dir)
            topics_dir = root / "topics"
            topics_dir.mkdir()
            topic_store = SQLiteTopicStore(db_path=root / "topics.sqlite3", topics_dir=topics_dir)
            topic = topic_store.create_or_get_topic(user_id="anonymous-user-1", title="Memory Prices")
            Path(topic.markdown_path).write_text(
                "# Memory Prices\n\n## Summary\n\nTracked topic.\n",
                encoding="utf-8",
            )
            scheduler = self._scheduler_service(root / "topic_pulse.sqlite3")
            notification_store = SQLiteNotificationStore(path=root / "topic_pulse.sqlite3")

            with patch.object(web_app_module, "_topic_store", return_value=topic_store):
                with patch.object(web_app_module, "_notification_store", return_value=notification_store):
                    with TestClient(
                        create_app(
                            chat_runtime=FakeChatRuntime(),
                            scheduler_service=scheduler,
                            auth_required=False,
                        )
                    ) as client:
                        initial = client.get(f"/api/topics/{topic.id}/notifications/email")
                        saved = client.put(
                            f"/api/topics/{topic.id}/notifications/email",
                            json={"enabled": True, "only_when_has_new": True, "min_new_count": 2},
                        )
                        deliveries = client.get(f"/api/topics/{topic.id}/notifications/deliveries")

            self.assertEqual(initial.status_code, 200)
            self.assertFalse(initial.json()["enabled"])
            self.assertEqual(saved.status_code, 200)
            self.assertTrue(saved.json()["enabled"])
            self.assertEqual(saved.json()["target"], "anonymous@example.test")
            self.assertEqual(saved.json()["min_new_count"], 2)
            self.assertEqual(deliveries.status_code, 200)
            self.assertEqual(deliveries.json()["deliveries"], [])


if __name__ == "__main__":
    unittest.main()
