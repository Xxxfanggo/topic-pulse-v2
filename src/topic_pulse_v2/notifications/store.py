"""SQLite storage for notification subscriptions and delivery attempts."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from topic_pulse_v2.config import database_path
from topic_pulse_v2.db import Database, SQLiteDatabase

from .models import NotificationDelivery, NotificationSubscription


def _datetime_to_text(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _datetime_from_text(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _bool_to_int(value: bool) -> int:
    return 1 if value else 0


def _int_to_bool(value: Any) -> bool:
    return bool(int(value or 0))


class SQLiteNotificationStore:
    """Persistent notification subscriptions and delivery history."""

    def __init__(
        self,
        database: Database | None = None,
        *,
        path: str | Path | None = None,
    ) -> None:
        self._database = database or SQLiteDatabase(path or database_path())

    def initialize(self) -> None:
        self._database.initialize()
        self._database.execute_script(
            """
            CREATE TABLE IF NOT EXISTS notification_subscriptions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                topic_id TEXT NOT NULL,
                channel TEXT NOT NULL,
                target TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                only_when_has_new INTEGER NOT NULL,
                min_new_count INTEGER NOT NULL,
                digest_mode TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, topic_id, channel)
            );

            CREATE TABLE IF NOT EXISTS notification_deliveries (
                id TEXT PRIMARY KEY,
                subscription_id TEXT NOT NULL,
                job_run_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                topic_id TEXT NOT NULL,
                channel TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                subject TEXT NOT NULL,
                error TEXT NOT NULL,
                provider_response TEXT NOT NULL,
                created_at TEXT NOT NULL,
                sent_at TEXT,
                FOREIGN KEY(subscription_id) REFERENCES notification_subscriptions(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_notification_subscriptions_user_topic
                ON notification_subscriptions(user_id, topic_id);
            CREATE INDEX IF NOT EXISTS idx_notification_deliveries_topic_created
                ON notification_deliveries(user_id, topic_id, created_at DESC);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_notification_deliveries_subscription_payload
                ON notification_deliveries(subscription_id, payload_hash);
            """
        )

    def upsert_email_subscription(
        self,
        *,
        user_id: str,
        topic_id: str,
        target: str,
        enabled: bool = True,
        only_when_has_new: bool = True,
        min_new_count: int = 1,
        digest_mode: str = "immediate",
    ) -> NotificationSubscription:
        self.initialize()
        now = datetime.now(timezone.utc)
        existing = self.get_subscription(user_id=user_id, topic_id=topic_id, channel="email")
        subscription_id = existing.id if existing else f"ntf_{secrets.token_urlsafe(12)}"
        created_at = existing.created_at if existing else now
        subscription = NotificationSubscription(
            id=subscription_id,
            user_id=user_id,
            topic_id=topic_id,
            channel="email",
            target=target,
            enabled=enabled,
            only_when_has_new=only_when_has_new,
            min_new_count=max(1, int(min_new_count or 1)),
            digest_mode=digest_mode or "immediate",
            created_at=created_at,
            updated_at=now,
        )
        self._database.execute(
            """
            INSERT INTO notification_subscriptions (
                id, user_id, topic_id, channel, target, enabled, only_when_has_new,
                min_new_count, digest_mode, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, topic_id, channel) DO UPDATE SET
                target = excluded.target,
                enabled = excluded.enabled,
                only_when_has_new = excluded.only_when_has_new,
                min_new_count = excluded.min_new_count,
                digest_mode = excluded.digest_mode,
                updated_at = excluded.updated_at
            """,
            (
                subscription.id,
                subscription.user_id,
                subscription.topic_id,
                subscription.channel,
                subscription.target,
                _bool_to_int(subscription.enabled),
                _bool_to_int(subscription.only_when_has_new),
                subscription.min_new_count,
                subscription.digest_mode,
                _datetime_to_text(subscription.created_at),
                _datetime_to_text(subscription.updated_at),
            ),
        )
        return subscription

    def get_subscription(
        self,
        *,
        user_id: str,
        topic_id: str,
        channel: str,
    ) -> NotificationSubscription | None:
        self.initialize()
        row = self._database.fetch_one(
            """
            SELECT * FROM notification_subscriptions
            WHERE user_id = ? AND topic_id = ? AND channel = ?
            """,
            (user_id, topic_id, channel),
        )
        return self._subscription_from_row(row) if row else None

    def list_topic_subscriptions(
        self,
        *,
        user_id: str,
        topic_id: str,
        channel: str | None = None,
        enabled_only: bool = False,
    ) -> list[NotificationSubscription]:
        self.initialize()
        filters = ["user_id = ?", "topic_id = ?"]
        params: list[Any] = [user_id, topic_id]
        if channel:
            filters.append("channel = ?")
            params.append(channel)
        if enabled_only:
            filters.append("enabled = 1")
        rows = self._database.fetch_all(
            f"""
            SELECT * FROM notification_subscriptions
            WHERE {' AND '.join(filters)}
            ORDER BY created_at DESC
            """,
            params,
        )
        return [self._subscription_from_row(row) for row in rows]

    def save_delivery(self, delivery: NotificationDelivery) -> NotificationDelivery:
        self.initialize()
        self._database.execute(
            """
            INSERT INTO notification_deliveries (
                id, subscription_id, job_run_id, user_id, topic_id, channel, status,
                payload_hash, subject, error, provider_response, created_at, sent_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(subscription_id, payload_hash) DO NOTHING
            """,
            (
                delivery.id,
                delivery.subscription_id,
                delivery.job_run_id,
                delivery.user_id,
                delivery.topic_id,
                delivery.channel,
                delivery.status,
                delivery.payload_hash,
                delivery.subject,
                delivery.error,
                delivery.provider_response,
                _datetime_to_text(delivery.created_at),
                _datetime_to_text(delivery.sent_at),
            ),
        )
        return delivery

    def has_delivery(self, *, subscription_id: str, payload_hash: str) -> bool:
        self.initialize()
        row = self._database.fetch_one(
            """
            SELECT id FROM notification_deliveries
            WHERE subscription_id = ? AND payload_hash = ?
            LIMIT 1
            """,
            (subscription_id, payload_hash),
        )
        return row is not None

    def list_deliveries(
        self,
        *,
        user_id: str,
        topic_id: str | None = None,
        limit: int = 50,
    ) -> list[NotificationDelivery]:
        self.initialize()
        if topic_id:
            rows = self._database.fetch_all(
                """
                SELECT * FROM notification_deliveries
                WHERE user_id = ? AND topic_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, topic_id, limit),
            )
        else:
            rows = self._database.fetch_all(
                """
                SELECT * FROM notification_deliveries
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            )
        return [self._delivery_from_row(row) for row in rows]

    def close(self) -> None:
        self._database.close()

    @staticmethod
    def _subscription_from_row(row: dict[str, Any]) -> NotificationSubscription:
        return NotificationSubscription(
            id=row["id"],
            user_id=row["user_id"],
            topic_id=row["topic_id"],
            channel=row["channel"],
            target=row["target"],
            enabled=_int_to_bool(row["enabled"]),
            only_when_has_new=_int_to_bool(row["only_when_has_new"]),
            min_new_count=int(row["min_new_count"] or 1),
            digest_mode=row["digest_mode"],
            created_at=_datetime_from_text(row["created_at"]) or datetime.now(timezone.utc),
            updated_at=_datetime_from_text(row["updated_at"]) or datetime.now(timezone.utc),
        )

    @staticmethod
    def _delivery_from_row(row: dict[str, Any]) -> NotificationDelivery:
        return NotificationDelivery(
            id=row["id"],
            subscription_id=row["subscription_id"],
            job_run_id=row["job_run_id"],
            user_id=row["user_id"],
            topic_id=row["topic_id"],
            channel=row["channel"],
            status=row["status"],
            payload_hash=row["payload_hash"],
            subject=row["subject"],
            error=row["error"],
            provider_response=row["provider_response"],
            created_at=_datetime_from_text(row["created_at"]) or datetime.now(timezone.utc),
            sent_at=_datetime_from_text(row["sent_at"]),
        )
