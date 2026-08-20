"""Notification domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


NotificationChannel = Literal["email"]
DeliveryStatus = Literal["sent", "failed", "skipped"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class NotificationSubscription:
    id: str
    user_id: str
    topic_id: str
    channel: NotificationChannel
    target: str
    enabled: bool = True
    only_when_has_new: bool = True
    min_new_count: int = 1
    digest_mode: str = "immediate"
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class NotificationDelivery:
    id: str
    subscription_id: str
    job_run_id: str
    user_id: str
    topic_id: str
    channel: NotificationChannel
    status: DeliveryStatus
    payload_hash: str
    subject: str = ""
    error: str = ""
    provider_response: str = ""
    created_at: datetime = field(default_factory=utc_now)
    sent_at: datetime | None = None


@dataclass(slots=True)
class TopicRefreshNotification:
    job_id: str
    job_run_id: str
    user_id: str
    topic_id: str
    topic_title: str
    result: dict[str, Any]
    app_base_url: str = ""

