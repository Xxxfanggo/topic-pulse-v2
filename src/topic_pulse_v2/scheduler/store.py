"""Persistence interfaces and SQLite scheduler store."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from topic_pulse_v2.db import Database, SQLiteDatabase

from .models import JobRun, ScheduledJob


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _load_json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    return json.loads(value)


def _datetime_to_text(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _datetime_from_text(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


class SchedulerStore(ABC):
    """Persistence boundary for scheduler jobs and run history."""

    @abstractmethod
    def initialize(self) -> None:
        """Create required structures."""

    @abstractmethod
    def save_job(self, job: ScheduledJob) -> ScheduledJob:
        """Create or update a scheduled job."""

    @abstractmethod
    def get_job(self, job_id: str) -> ScheduledJob:
        """Read one scheduled job."""

    @abstractmethod
    def list_jobs(self) -> list[ScheduledJob]:
        """List scheduled jobs."""

    @abstractmethod
    def delete_job(self, job_id: str) -> None:
        """Delete one scheduled job and its run records."""

    @abstractmethod
    def save_run(self, run: JobRun) -> JobRun:
        """Create or update a run record."""

    @abstractmethod
    def list_runs(self, job_id: str | None = None, *, limit: int = 50) -> list[JobRun]:
        """List run history."""

    @abstractmethod
    def close(self) -> None:
        """Close store resources."""


class SQLiteSchedulerStore(SchedulerStore):
    """SQLite implementation of scheduler persistence."""

    def __init__(
        self,
        database: Database | None = None,
        *,
        path: str | Path | None = None,
    ) -> None:
        self._database = database or SQLiteDatabase(path)

    def initialize(self) -> None:
        self._database.initialize()
        self._database.execute_script(
            """
            CREATE TABLE IF NOT EXISTS scheduled_jobs (
                id TEXT PRIMARY KEY,
                task_name TEXT NOT NULL,
                trigger TEXT NOT NULL,
                trigger_args TEXT NOT NULL,
                args TEXT NOT NULL,
                kwargs TEXT NOT NULL,
                status TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                metadata TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS job_runs (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                task_name TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                duration_ms REAL,
                error TEXT NOT NULL,
                result_summary TEXT NOT NULL,
                metadata TEXT NOT NULL,
                FOREIGN KEY(job_id) REFERENCES scheduled_jobs(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_status
                ON scheduled_jobs(status);
            CREATE INDEX IF NOT EXISTS idx_job_runs_job_started
                ON job_runs(job_id, started_at DESC);
            """
        )

    def save_job(self, job: ScheduledJob) -> ScheduledJob:
        self._database.execute(
            """
            INSERT INTO scheduled_jobs (
                id, task_name, trigger, trigger_args, args, kwargs, status,
                name, description, metadata, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                task_name = excluded.task_name,
                trigger = excluded.trigger,
                trigger_args = excluded.trigger_args,
                args = excluded.args,
                kwargs = excluded.kwargs,
                status = excluded.status,
                name = excluded.name,
                description = excluded.description,
                metadata = excluded.metadata,
                updated_at = excluded.updated_at
            """,
            (
                job.id,
                job.task_name,
                job.trigger,
                _dump_json(job.trigger_args),
                _dump_json(job.args),
                _dump_json(job.kwargs),
                job.status,
                job.name,
                job.description,
                _dump_json(job.metadata),
                _datetime_to_text(job.created_at),
                _datetime_to_text(job.updated_at),
            ),
        )
        return job

    def get_job(self, job_id: str) -> ScheduledJob:
        row = self._database.fetch_one(
            "SELECT * FROM scheduled_jobs WHERE id = ?",
            (job_id,),
        )
        if row is None:
            raise LookupError(f"Scheduled job not found: {job_id}")
        return self._job_from_row(row)

    def list_jobs(self) -> list[ScheduledJob]:
        rows = self._database.fetch_all(
            "SELECT * FROM scheduled_jobs ORDER BY created_at DESC"
        )
        return [self._job_from_row(row) for row in rows]

    def delete_job(self, job_id: str) -> None:
        self._database.execute("DELETE FROM scheduled_jobs WHERE id = ?", (job_id,))

    def save_run(self, run: JobRun) -> JobRun:
        self._database.execute(
            """
            INSERT INTO job_runs (
                id, job_id, task_name, status, started_at, finished_at,
                duration_ms, error, result_summary, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status,
                finished_at = excluded.finished_at,
                duration_ms = excluded.duration_ms,
                error = excluded.error,
                result_summary = excluded.result_summary,
                metadata = excluded.metadata
            """,
            (
                run.id,
                run.job_id,
                run.task_name,
                run.status,
                _datetime_to_text(run.started_at),
                _datetime_to_text(run.finished_at),
                run.duration_ms,
                run.error,
                run.result_summary,
                _dump_json(run.metadata),
            ),
        )
        return run

    def list_runs(self, job_id: str | None = None, *, limit: int = 50) -> list[JobRun]:
        if job_id is None:
            rows = self._database.fetch_all(
                "SELECT * FROM job_runs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            )
        else:
            rows = self._database.fetch_all(
                """
                SELECT * FROM job_runs
                WHERE job_id = ?
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (job_id, limit),
            )
        return [self._run_from_row(row) for row in rows]

    def close(self) -> None:
        self._database.close()

    @staticmethod
    def _job_from_row(row: dict[str, Any]) -> ScheduledJob:
        return ScheduledJob(
            id=row["id"],
            task_name=row["task_name"],
            trigger=row["trigger"],
            trigger_args=_load_json(row["trigger_args"], {}),
            args=_load_json(row["args"], []),
            kwargs=_load_json(row["kwargs"], {}),
            status=row["status"],
            name=row["name"],
            description=row["description"],
            metadata=_load_json(row["metadata"], {}),
            created_at=_datetime_from_text(row["created_at"]) or datetime.now(timezone.utc),
            updated_at=_datetime_from_text(row["updated_at"]) or datetime.now(timezone.utc),
        )

    @staticmethod
    def _run_from_row(row: dict[str, Any]) -> JobRun:
        return JobRun(
            id=row["id"],
            job_id=row["job_id"],
            task_name=row["task_name"],
            status=row["status"],
            started_at=_datetime_from_text(row["started_at"]) or datetime.now(timezone.utc),
            finished_at=_datetime_from_text(row["finished_at"]),
            duration_ms=row["duration_ms"],
            error=row["error"],
            result_summary=row["result_summary"],
            metadata=_load_json(row["metadata"], {}),
        )
