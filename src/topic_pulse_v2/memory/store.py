"""User-scoped memory storage abstractions and in-memory implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class MemoryRecord:
    """One memory item."""

    user_id: str
    content: str
    id: str = field(default_factory=lambda: str(uuid4()))
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)


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
            results.append(record)
            if len(results) >= limit:
                break

        return results
