"""Topic-owned helpers for refresh schedule jobs."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from topic_pulse_v2.config import database_path, topics_dir as default_topics_dir
from topic_pulse_v2.scheduler import ScheduledJob, SQLiteSchedulerStore

from .store import SQLiteTopicStore, TopicRecord


GUEST_USER_PREFIX = "guest_"


class TopicRefreshScheduler(Protocol):
    def add_job(self, job: ScheduledJob) -> ScheduledJob:
        ...

    def list_jobs(self) -> list[ScheduledJob]:
        ...


def topic_refresh_job_id(topic_id: str) -> str:
    return f"topic-refresh-{uuid5(NAMESPACE_URL, f'topic-pulse/topic/{topic_id}')}"


def find_topic_refresh_job(
    scheduler: TopicRefreshScheduler,
    topic_id: str,
    *,
    user_id: str | None = None,
) -> ScheduledJob | None:
    for job in scheduler.list_jobs():
        metadata = job.metadata or {}
        if metadata.get("type") == "topic_refresh" and metadata.get("topic_id") == topic_id:
            if user_id is not None and metadata.get("user_id") != user_id:
                continue
            return job
    return None


def topic_refresh_trigger_args(
    *,
    trigger: str = "interval",
    interval_minutes: int = 60,
    cron_hour: int | None = None,
    cron_minute: int | None = None,
) -> tuple[str, dict]:
    if trigger == "interval":
        minutes = int(interval_minutes)
        if minutes < 1:
            raise ValueError("interval_minutes must be greater than or equal to 1.")
        return "interval", {"minutes": minutes}
    if trigger == "cron":
        if cron_hour is None or cron_minute is None:
            raise ValueError("cron_hour and cron_minute are required for cron trigger.")
        hour = int(cron_hour)
        minute = int(cron_minute)
        if not 0 <= hour <= 23:
            raise ValueError("cron_hour must be between 0 and 23.")
        if not 0 <= minute <= 59:
            raise ValueError("cron_minute must be between 0 and 59.")
        return "cron", {"hour": hour, "minute": minute}
    raise ValueError("trigger must be one of: interval, cron.")


def build_topic_refresh_job(
    record: TopicRecord,
    *,
    trigger: str = "interval",
    interval_minutes: int = 60,
    cron_hour: int | None = None,
    cron_minute: int | None = None,
    enabled: bool = True,
) -> ScheduledJob:
    schedule_trigger, trigger_args = topic_refresh_trigger_args(
        trigger=trigger,
        interval_minutes=interval_minutes,
        cron_hour=cron_hour,
        cron_minute=cron_minute,
    )
    path = Path(record.markdown_path)
    now = datetime.now(timezone.utc)
    return ScheduledJob(
        id=topic_refresh_job_id(record.id),
        task_name="refresh_topic",
        trigger=schedule_trigger,
        trigger_args=trigger_args,
        kwargs={
            "topic_name": record.title,
            "user_id": record.user_id,
        },
        status="active" if enabled else "paused",
        name=f"Refresh topic: {record.title}",
        description="Refresh one tracked topic from the web and update local Markdown memory.",
        metadata={
            "type": "topic_refresh",
            "topic_id": record.id,
            "topic_title": record.title,
            "topic_filename": path.name,
            "user_id": record.user_id,
        },
        created_at=now,
        updated_at=now,
    )


def create_topic_refresh_schedule(
    *,
    scheduler: TopicRefreshScheduler,
    topic_store: SQLiteTopicStore,
    user_id: str,
    topic_id: str | None = None,
    topic_name: str | None = None,
    trigger: str = "interval",
    interval_minutes: int = 60,
    cron_hour: int | None = None,
    cron_minute: int | None = None,
    enabled: bool = True,
) -> tuple[ScheduledJob, bool]:
    user_id = str(user_id or "").strip()
    if not user_id:
        raise ValueError("user_id cannot be empty.")
    if user_id.startswith(GUEST_USER_PREFIX):
        raise PermissionError("访客不能创建定时调度任务，请登录后使用。")

    record = resolve_scheduled_topic(topic_store, user_id=user_id, topic_id=topic_id, topic_name=topic_name)
    existing = find_topic_refresh_job(scheduler, record.id, user_id=user_id)
    if existing is not None:
        return existing, False

    job = build_topic_refresh_job(
        record,
        trigger=trigger,
        interval_minutes=interval_minutes,
        cron_hour=cron_hour,
        cron_minute=cron_minute,
        enabled=enabled,
    )
    return scheduler.add_job(job), True


def create_persisted_topic_refresh_schedule(
    *,
    user_id: str,
    topic_name: str,
    trigger: str = "interval",
    interval_minutes: int = 60,
    cron_hour: int | None = None,
    cron_minute: int | None = None,
    enabled: bool = True,
    db_path: str | Path | None = None,
    topics_dir: str | Path | None = None,
) -> tuple[ScheduledJob, bool]:
    topic_store = SQLiteTopicStore(
        db_path=db_path or database_path(),
        topics_dir=topics_dir or default_topics_dir(),
    )
    scheduler = _PersistedScheduler(path=db_path or database_path())
    try:
        scheduler.initialize()
        return create_topic_refresh_schedule(
            scheduler=scheduler,
            topic_store=topic_store,
            user_id=user_id,
            topic_name=topic_name,
            trigger=trigger,
            interval_minutes=interval_minutes,
            cron_hour=cron_hour,
            cron_minute=cron_minute,
            enabled=enabled,
        )
    finally:
        scheduler.close()


def resolve_scheduled_topic(
    topic_store: SQLiteTopicStore,
    *,
    user_id: str,
    topic_id: str | None = None,
    topic_name: str | None = None,
) -> TopicRecord:
    if topic_id:
        record = topic_store.get_topic(user_id=user_id, topic_id=topic_id)
    elif topic_name:
        record = topic_store.get_by_title(user_id=user_id, title=topic_name)
        if record is None:
            raise FileNotFoundError(f"topic markdown does not exist: {topic_name}")
    else:
        raise ValueError("topic_id and topic_name cannot both be empty.")

    path = Path(record.markdown_path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError("Topic not found")
    return record


class _PersistedScheduler:
    def __init__(self, *, path: str | Path) -> None:
        self._store = SQLiteSchedulerStore(path=path)

    def initialize(self) -> None:
        self._store.initialize()

    def add_job(self, job: ScheduledJob) -> ScheduledJob:
        return self._store.save_job(job)

    def list_jobs(self) -> list[ScheduledJob]:
        return self._store.list_jobs()

    def close(self) -> None:
        self._store.close()
