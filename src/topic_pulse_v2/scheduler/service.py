"""APScheduler-backed service for embedding in FastAPI."""

from __future__ import annotations

import inspect
import json
import logging
from dataclasses import replace
from datetime import datetime
from time import perf_counter
from typing import Any, Protocol
from uuid import uuid4

from topic_pulse_v2.notifications import TopicRefreshNotification

from .models import JobRun, ScheduledJob
from .registry import ScheduledTaskRegistry
from .store import SchedulerStore

SUMMARY_FIELD_LIMIT = 500
logger = logging.getLogger(__name__)


class NotificationDispatcherRuntime(Protocol):
    def dispatch_topic_refresh(self, event: TopicRefreshNotification):
        ...


class SchedulerService:
    """Application-owned scheduler facade backed by APScheduler."""

    def __init__(
        self,
        *,
        store: SchedulerStore,
        registry: ScheduledTaskRegistry,
        timezone: str = "Asia/Shanghai",
        enabled: bool = True,
        notification_dispatcher: NotificationDispatcherRuntime | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._timezone = timezone
        self._enabled = enabled
        self._notification_dispatcher = notification_dispatcher
        self._scheduler: Any | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    def start(self) -> None:
        """Initialize persistence, load active jobs, and start APScheduler."""

        self._store.initialize()
        if not self._enabled:
            return
        scheduler = self._create_scheduler()
        self._scheduler = scheduler
        for job in self._store.list_jobs():
            if job.status == "active":
                self._schedule_job(job)
        scheduler.start()

    def shutdown(self, *, wait: bool = False) -> None:
        if self._scheduler is not None and self._scheduler.running:
            self._scheduler.shutdown(wait=wait)
        self._store.close()

    def add_job(self, job: ScheduledJob) -> ScheduledJob:
        self._store.save_job(job)
        if self._scheduler is not None and job.status == "active":
            self._schedule_job(job, replace_existing=True)
        return job

    def pause_job(self, job_id: str) -> ScheduledJob:
        job = self._store.get_job(job_id)
        job.status = "paused"
        job.updated_at = datetime.now(job.updated_at.tzinfo)
        self._store.save_job(job)
        if self._scheduler is not None:
            self._scheduler.pause_job(job_id)
        return job

    def resume_job(self, job_id: str) -> ScheduledJob:
        job = self._store.get_job(job_id)
        job.status = "active"
        job.updated_at = datetime.now(job.updated_at.tzinfo)
        self._store.save_job(job)
        if self._scheduler is not None:
            if self._scheduler.get_job(job_id):
                self._scheduler.resume_job(job_id)
            else:
                self._schedule_job(job)
        return job

    async def run_job_now(self, job_id: str) -> JobRun:
        job = self._store.get_job(job_id)
        return await self._run_job(job)

    def list_jobs(self) -> list[ScheduledJob]:
        return self._store.list_jobs()

    def list_runs(self, job_id: str | None = None, *, limit: int = 50) -> list[JobRun]:
        return self._store.list_runs(job_id, limit=limit)

    def _create_scheduler(self) -> Any:
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "APScheduler is required for SchedulerService. "
                "Install project dependencies from requirements.txt."
            ) from exc
        return AsyncIOScheduler(timezone=self._timezone)

    def _schedule_job(
        self,
        job: ScheduledJob,
        *,
        replace_existing: bool = True,
    ) -> None:
        if self._scheduler is None:
            return
        job = _with_runtime_kwargs(job)
        self._scheduler.add_job(
            self._run_job,
            trigger=job.trigger,
            args=[job],
            id=job.id,
            name=job.name or job.id,
            replace_existing=replace_existing,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=job.metadata.get("misfire_grace_time", 60),
            **job.trigger_args,
        )

    async def _run_job(self, job: ScheduledJob) -> JobRun:
        job = _with_runtime_kwargs(job)
        started = perf_counter()
        run = JobRun(
            id=str(uuid4()),
            job_id=job.id,
            task_name=job.task_name,
            status="running",
        )
        self._store.save_run(run)
        try:
            task = self._registry.get(job.task_name)
            result = task.handler(*job.args, **job.kwargs)
            if inspect.isawaitable(result):
                result = await result
            run.status = "success"
            run.result_summary = self._result_summary(result)
            run.metadata = {"task_metadata": task.metadata}
            notification_metadata = self._dispatch_notifications(job, run, result)
            if notification_metadata:
                run.metadata["notifications"] = notification_metadata
        except Exception as exc:
            run.status = "failed"
            run.error = f"{type(exc).__name__}: {exc}"
        finally:
            run.finished_at = datetime.now(run.started_at.tzinfo)
            run.duration_ms = round((perf_counter() - started) * 1000, 3)
            self._store.save_run(run)
        return run

    @staticmethod
    def _result_summary(result: Any) -> str:
        if result is None:
            return ""
        if isinstance(result, (dict, list)):
            return json.dumps(
                _truncate_summary_fields(result),
                ensure_ascii=False,
                default=str,
            )
        return str(result)

    def _dispatch_notifications(self, job: ScheduledJob, run: JobRun, result: Any) -> dict:
        if self._notification_dispatcher is None or job.task_name != "refresh_topic":
            return {}
        if not isinstance(result, dict):
            return {}

        metadata = job.metadata or {}
        user_id = str(result.get("user_id") or job.kwargs.get("user_id") or metadata.get("user_id") or "").strip()
        topic_id = str(result.get("topic_id") or metadata.get("topic_id") or "").strip()
        if not user_id or not topic_id:
            return {"status": "skipped", "reason": "missing user_id or topic_id"}

        event = TopicRefreshNotification(
            job_id=job.id,
            job_run_id=run.id,
            user_id=user_id,
            topic_id=topic_id,
            topic_title=str(result.get("topic_name") or metadata.get("topic_title") or "").strip(),
            result=result,
        )
        try:
            deliveries = self._notification_dispatcher.dispatch_topic_refresh(event)
        except Exception as exc:
            logger.exception("Notification dispatch failed.")
            return {
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
            }
        return {
            "status": "completed",
            "delivery_count": len(deliveries or []),
            "sent_count": sum(1 for item in deliveries or [] if getattr(item, "status", "") == "sent"),
            "failed_count": sum(1 for item in deliveries or [] if getattr(item, "status", "") == "failed"),
            "skipped_count": sum(1 for item in deliveries or [] if getattr(item, "status", "") == "skipped"),
        }


def _truncate_summary_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _truncate_text(item) if key == "summary" and isinstance(item, str) else _truncate_summary_fields(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_truncate_summary_fields(item) for item in value]
    return value


def _with_runtime_kwargs(job: ScheduledJob) -> ScheduledJob:
    if job.task_name != "refresh_topic":
        return job

    kwargs = dict(job.kwargs or {})
    if kwargs.get("user_id"):
        return job

    user_id = (job.metadata or {}).get("user_id")
    kwargs["user_id"] = user_id or "scheduler"
    return replace(job, kwargs=kwargs)


def _truncate_text(value: str, limit: int = SUMMARY_FIELD_LIMIT) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: max(0, limit - 3)]}..."
