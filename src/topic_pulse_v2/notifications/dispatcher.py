"""Notification dispatch orchestration."""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Protocol

from .models import NotificationDelivery, TopicRefreshNotification
from .providers.email_smtp import SMTPEmailProvider
from .renderer import render_topic_refresh_email
from .store import SQLiteNotificationStore

logger = logging.getLogger(__name__)


class EmailProvider(Protocol):
    def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str = "",
    ) -> str:
        ...


class NotificationDispatcher:
    """Dispatch notification events to enabled subscriptions."""

    def __init__(
        self,
        *,
        store: SQLiteNotificationStore | None = None,
        email_provider: EmailProvider | None = None,
        app_base_url: str = "",
    ) -> None:
        self.store = store or SQLiteNotificationStore()
        self.email_provider = email_provider or SMTPEmailProvider.from_env()
        self.app_base_url = app_base_url

    def initialize(self) -> None:
        self.store.initialize()

    def dispatch_topic_refresh(self, event: TopicRefreshNotification) -> list[NotificationDelivery]:
        result = event.result or {}
        user_id = str(event.user_id or "").strip()
        topic_id = str(event.topic_id or "").strip()
        if not user_id or not topic_id:
            return []

        subscriptions = self.store.list_topic_subscriptions(
            user_id=user_id,
            topic_id=topic_id,
            enabled_only=True,
        )
        deliveries: list[NotificationDelivery] = []
        for subscription in subscriptions:
            new_count = int(result.get("new_count") or 0)
            if subscription.only_when_has_new and new_count < subscription.min_new_count:
                continue
            if subscription.channel == "email":
                deliveries.append(self._dispatch_email(subscription, event))
        return deliveries

    def _dispatch_email(self, subscription, event: TopicRefreshNotification) -> NotificationDelivery:
        event = TopicRefreshNotification(
            job_id=event.job_id,
            job_run_id=event.job_run_id,
            user_id=event.user_id,
            topic_id=event.topic_id,
            topic_title=event.topic_title,
            result=event.result,
            app_base_url=event.app_base_url or self.app_base_url,
        )
        payload = render_topic_refresh_email(event)
        payload_hash = _payload_hash(
            {
                "job_run_id": event.job_run_id,
                "topic_id": event.topic_id,
                "channel": subscription.channel,
                "target": subscription.target,
                "subject": payload.subject,
                "text_body": payload.text_body,
            }
        )
        if self.store.has_delivery(subscription_id=subscription.id, payload_hash=payload_hash):
            return self._save_delivery(
                subscription,
                event,
                payload_hash=payload_hash,
                subject=payload.subject,
                status="skipped",
                error="duplicate payload",
            )
        if self.email_provider is None:
            return self._save_delivery(
                subscription,
                event,
                payload_hash=payload_hash,
                subject=payload.subject,
                status="failed",
                error="SMTP email provider is not configured",
            )
        try:
            provider_response = self.email_provider.send_email(
                to_email=subscription.target,
                subject=payload.subject,
                text_body=payload.text_body,
                html_body=payload.html_body,
            )
        except Exception as exc:
            logger.exception("Email notification delivery failed.")
            return self._save_delivery(
                subscription,
                event,
                payload_hash=payload_hash,
                subject=payload.subject,
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
            )
        return self._save_delivery(
            subscription,
            event,
            payload_hash=payload_hash,
            subject=payload.subject,
            status="sent",
            provider_response=provider_response,
            sent_at=datetime.now(timezone.utc),
        )

    def _save_delivery(
        self,
        subscription,
        event: TopicRefreshNotification,
        *,
        payload_hash: str,
        subject: str,
        status: str,
        error: str = "",
        provider_response: str = "",
        sent_at: datetime | None = None,
    ) -> NotificationDelivery:
        delivery = NotificationDelivery(
            id=f"ndl_{secrets.token_urlsafe(12)}",
            subscription_id=subscription.id,
            job_run_id=event.job_run_id,
            user_id=event.user_id,
            topic_id=event.topic_id,
            channel=subscription.channel,
            status=status,
            payload_hash=payload_hash,
            subject=subject,
            error=error,
            provider_response=provider_response,
            sent_at=sent_at,
        )
        self.store.save_delivery(delivery)
        return delivery


def _payload_hash(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

