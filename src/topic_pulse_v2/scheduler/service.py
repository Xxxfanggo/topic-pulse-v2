"""APScheduler-backed service for embedding in FastAPI."""

from __future__ import annotations

import inspect
from datetime import datetime
from time import perf_counter
from typing import Any
from uuid import uuid4

from .models import JobRun, ScheduledJob
from .registry import ScheduledTaskRegistry
from .store import SchedulerStore


class SchedulerService:
    """Application-owned scheduler facade backed by APScheduler."""

    def __init__(
        self,
        *,
        store: SchedulerStore,
        registry: ScheduledTaskRegistry,
        timezone: str = "Asia/Shanghai",
        enabled: bool = True,
    ) -> None:
        self._store = store
        self._registry = registry
        self._timezone = timezone
        self._enabled = enabled
        self._scheduler: Any | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    def start(self) -> None:
        """Initialize persistence, load active jobs, and start APScheduler."""

        if not self._enabled:
            return
        self._store.initialize()
        scheduler = self._create_scheduler()
        self._scheduler = scheduler
        for job in self._store.list_jobs():
            if job.status == "active":
                self._schedule_job(job)
        scheduler.start()

    def shutdown(self, *, wait: bool = False) -> None:
        if self._scheduler is not None and self._scheduler.running:
            self._scheduler.shutdown(wait=wait)

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
        text = str(result)
        if len(text) > 500:
            return f"{text[:497]}..."
        return text
