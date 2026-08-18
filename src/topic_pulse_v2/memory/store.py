"""User-scoped memory storage abstractions and implementations."""

from __future__ import annotations

import json
import re
import sqlite3
from abc import ABC, abstractmethod
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from topic_pulse_v2.config import database_path


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _datetime_to_text(value: datetime) -> str:
    return value.isoformat()


def _datetime_from_text(value: str) -> datetime:
    return datetime.fromisoformat(value)


@dataclass(slots=True)
class MemoryRecord:
    """One memory item."""

    user_id: str
    content: str
    id: str = field(default_factory=lambda: str(uuid4()))
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


class MemoryStore(ABC):
    """Abstract memory store."""

    @abstractmethod
    def save(
        self,
        user_id: str,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryRecord:
        """Save one memory item for a user."""

    @abstractmethod
    def search(
        self,
        user_id: str,
        query: str = "",
        *,
        limit: int = 20,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[MemoryRecord]:
        """Search memory items for a user."""


class InMemoryStore(MemoryStore):
    """Simple process-local memory store."""

    def __init__(self) -> None:
        self._records: dict[str, MemoryRecord] = {}
        self._record_orders: dict[str, int] = {}
        self._next_order = 0

    def save(
        self,
        user_id: str,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryRecord:
        if not user_id:
            raise ValueError("user_id cannot be empty.")
        record = MemoryRecord(
            user_id=user_id,
            content=content,
            metadata=metadata or {},
        )
        self._records[record.id] = record
        self._record_orders[record.id] = self._next_order
        self._next_order += 1
        return record

    def search(
        self,
        user_id: str,
        query: str = "",
        *,
        limit: int = 20,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[MemoryRecord]:
        if not user_id:
            raise ValueError("user_id cannot be empty.")
        query_lower = query.lower().strip()
        results: list[MemoryRecord] = []

        for record in sorted(
            self._records.values(),
            key=lambda item: self._record_orders[item.id],
            reverse=True,
        ):
            if record.user_id != user_id:
                continue
            if query_lower and query_lower not in record.content.lower():
                continue
            if metadata_filter and not _metadata_matches(record.metadata, metadata_filter):
                continue
            results.append(record)
            if len(results) >= limit:
                break

        return results


class SQLiteMemoryStore(MemoryStore):
    """SQLite-backed user memory store.

    The MVP keeps retrieval deterministic and lightweight: metadata filters,
    substring matching, and newest-first ordering. Embeddings can sit behind
    the same interface later.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else database_path()

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            with connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS memories (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        content TEXT NOT NULL,
                        metadata TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_memories_user_updated
                        ON memories(user_id, updated_at DESC);
                    """
                )

    def save(
        self,
        user_id: str,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryRecord:
        if not user_id:
            raise ValueError("user_id cannot be empty.")
        content = str(content or "").strip()
        if not content:
            raise ValueError("content cannot be empty.")

        self.initialize()
        now = utc_now()
        record = MemoryRecord(
            user_id=user_id,
            content=content,
            metadata=metadata or {},
            created_at=now,
            updated_at=now,
        )
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO memories (
                        id, user_id, content, metadata, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.id,
                        record.user_id,
                        record.content,
                        json.dumps(record.metadata, ensure_ascii=False, default=str),
                        _datetime_to_text(record.created_at),
                        _datetime_to_text(record.updated_at),
                    ),
                )
        return record

    def search(
        self,
        user_id: str,
        query: str = "",
        *,
        limit: int = 20,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[MemoryRecord]:
        if not user_id:
            raise ValueError("user_id cannot be empty.")
        self.initialize()
        query_lower = query.lower().strip()
        rows = self._rows_for_user(user_id)
        records: list[MemoryRecord] = []
        for row in rows:
            record = self._record_from_row(row)
            if metadata_filter and not _metadata_matches(record.metadata, metadata_filter):
                continue
            if query_lower and not _query_matches(record, query_lower):
                continue
            records.append(record)
            if len(records) >= limit:
                break
        return records

    def _rows_for_user(self, user_id: str) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM memories WHERE user_id = ? ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _record_from_row(row: dict[str, Any]) -> MemoryRecord:
        try:
            metadata = json.loads(row["metadata"])
        except json.JSONDecodeError:
            metadata = {}
        return MemoryRecord(
            id=row["id"],
            user_id=row["user_id"],
            content=row["content"],
            metadata=metadata if isinstance(metadata, dict) else {},
            created_at=_datetime_from_text(row["created_at"]),
            updated_at=_datetime_from_text(row["updated_at"]),
        )


def _metadata_matches(metadata: dict[str, Any], expected: dict[str, Any]) -> bool:
    for key, value in expected.items():
        if metadata.get(key) != value:
            return False
    return True


def _query_matches(record: MemoryRecord, query_lower: str) -> bool:
    haystack = f"{record.content} {json.dumps(record.metadata, ensure_ascii=False, default=str)}".lower()
    if query_lower in haystack:
        return True
    tokens = [
        token
        for token in re.split(r"[\s,，。；;：:（）()]+", query_lower)
        if len(token) >= 2
    ]
    return any(token in haystack for token in tokens)
