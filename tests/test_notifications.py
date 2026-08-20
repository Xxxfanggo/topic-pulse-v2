import tempfile
import unittest
from pathlib import Path

from topic_pulse_v2.notifications import NotificationDispatcher, SQLiteNotificationStore, TopicRefreshNotification


class RecordingEmailProvider:
    def __init__(self):
        self.messages = []

    def send_email(self, *, to_email, subject, text_body, html_body=""):
        self.messages.append(
            {
                "to_email": to_email,
                "subject": subject,
                "text_body": text_body,
                "html_body": html_body,
            }
        )
        return "recorded"


class NotificationTests(unittest.TestCase):
    def test_email_dispatch_sends_and_records_delivery(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SQLiteNotificationStore(path=Path(temp_dir) / "topic_pulse.sqlite3")
            provider = RecordingEmailProvider()
            dispatcher = NotificationDispatcher(store=store, email_provider=provider, app_base_url="https://example.test")
            store.upsert_email_subscription(
                user_id="user-1",
                topic_id="topic-1",
                target="user@example.com",
                enabled=True,
            )

            deliveries = dispatcher.dispatch_topic_refresh(
                TopicRefreshNotification(
                    job_id="job-1",
                    job_run_id="run-1",
                    user_id="user-1",
                    topic_id="topic-1",
                    topic_title="Memory Prices",
                    result={
                        "topic_name": "Memory Prices",
                        "new_count": 2,
                        "existing_count": 3,
                        "new_items": [{"title": "DRAM price rises", "summary": "Contract prices moved up."}],
                    },
                )
            )

            self.assertEqual(len(provider.messages), 1)
            self.assertEqual(provider.messages[0]["to_email"], "user@example.com")
            self.assertIn("Memory Prices", provider.messages[0]["subject"])
            self.assertIn("DRAM price rises", provider.messages[0]["text_body"])
            self.assertIn("https://example.test/topics/topic-1", provider.messages[0]["text_body"])
            self.assertEqual(deliveries[0].status, "sent")
            self.assertEqual(store.list_deliveries(user_id="user-1", topic_id="topic-1")[0].status, "sent")
            store.close()

    def test_dispatch_skips_when_no_new_items(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SQLiteNotificationStore(path=Path(temp_dir) / "topic_pulse.sqlite3")
            provider = RecordingEmailProvider()
            dispatcher = NotificationDispatcher(store=store, email_provider=provider)
            store.upsert_email_subscription(
                user_id="user-1",
                topic_id="topic-1",
                target="user@example.com",
                enabled=True,
            )

            deliveries = dispatcher.dispatch_topic_refresh(
                TopicRefreshNotification(
                    job_id="job-1",
                    job_run_id="run-1",
                    user_id="user-1",
                    topic_id="topic-1",
                    topic_title="Memory Prices",
                    result={"topic_name": "Memory Prices", "new_count": 0},
                )
            )

            self.assertEqual(deliveries, [])
            self.assertEqual(provider.messages, [])
            store.close()


if __name__ == "__main__":
    unittest.main()
