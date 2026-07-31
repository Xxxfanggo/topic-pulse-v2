"""Memory storage abstractions and an in-memory implementation."""

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

    content: str
    id: str = field(default_factory=lambda: str(uuid4()))
    namespace: str = "default"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


class MemoryStore(ABC):
    """Abstract memory store."""

    @abstractmethod
    def save(
        self,
        content: str,
        *,
        namespace: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> MemoryRecord:
        """Save a memory item."""

    @abstractmethod
    def get(self, memory_id: str) -> MemoryRecord:
        """Read one memory item by id."""

    @abstractmethod
    def search(
        self,
        query: str = "",
        *,
        namespace: str | None = None,
        limit: int = 20,
    ) -> list[MemoryRecord]:
        """Search memory items."""

    @abstractmethod
    def delete(self, memory_id: str) -> None:
        """Delete one memory item."""


class InMemoryStore(MemoryStore):
    """Simple process-local memory store."""

    def __init__(self) -> None:
        self._records: dict[str, MemoryRecord] = {}

    def save(
        self,
        content: str,
        *,
        namespace: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> MemoryRecord:
        record = MemoryRecord(
            content=content,
            namespace=namespace,
            metadata=metadata or {},
        )
        self._records[record.id] = record
        return record

    def update(
        self,
        memory_id: str,
        *,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryRecord:
        record = self.get(memory_id)
        if content is not None:
            record.content = content
        if metadata is not None:
            record.metadata = metadata
        record.updated_at = utc_now()
        return record

    def get(self, memory_id: str) -> MemoryRecord:
        try:
            return self._records[memory_id]
        except KeyError as exc:
            raise LookupError(f"Memory not found: {memory_id}") from exc

    def search(
        self,
        query: str = "",
        *,
        namespace: str | None = None,
        limit: int = 20,
    ) -> list[MemoryRecord]:
        query_lower = query.lower().strip()
        results: list[MemoryRecord] = []

        for record in sorted(
            self._records.values(),
            key=lambda item: item.updated_at,
            reverse=True,
        ):
            if namespace is not None and record.namespace != namespace:
                continue
            if query_lower and query_lower not in record.content.lower():
                continue
            results.append(record)
            if len(results) >= limit:
                break

        return results

    def delete(self, memory_id: str) -> None:
        self._records.pop(memory_id)

    def clear(self, *, namespace: str | None = None) -> int:
        if namespace is None:
            count = len(self._records)
            self._records.clear()
            return count

        ids = [
            memory_id
            for memory_id, record in self._records.items()
            if record.namespace == namespace
        ]
        for memory_id in ids:
            self._records.pop(memory_id)
        return len(ids)
