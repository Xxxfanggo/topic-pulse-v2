"""Scheduler domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


TriggerType = Literal["date", "interval", "cron"]
JobStatus = Literal["active", "paused", "disabled"]
RunStatus = Literal["running", "success", "failed", "skipped"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class ScheduledJob:
    """A persisted scheduling definition owned by the application."""

    id: str
    task_name: str
    trigger: TriggerType
    trigger_args: dict[str, Any] = field(default_factory=dict)
    args: list[Any] = field(default_factory=list)
    kwargs: dict[str, Any] = field(default_factory=dict)
    status: JobStatus = "active"
    name: str = ""
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class JobRun:
    """One execution record for a scheduled job."""

    id: str
    job_id: str
    task_name: str
    status: RunStatus
    started_at: datetime = field(default_factory=utc_now)
    finished_at: datetime | None = None
    duration_ms: float | None = None
    error: str = ""
    result_summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
