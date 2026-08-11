"""Database interface boundaries."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any


Row = dict[str, Any]
Params = Sequence[Any] | dict[str, Any] | None


class Database(ABC):
    """Small interface for project-owned persistence implementations."""

    @abstractmethod
    def initialize(self) -> None:
        """Create required database structures."""

    @abstractmethod
    def execute(self, sql: str, params: Params = None) -> int:
        """Execute a statement and return the affected row count."""

    @abstractmethod
    def execute_script(self, sql: str) -> None:
        """Execute multiple SQL statements."""

    @abstractmethod
    def fetch_one(self, sql: str, params: Params = None) -> Row | None:
        """Fetch a single row."""

    @abstractmethod
    def fetch_all(self, sql: str, params: Params = None) -> list[Row]:
        """Fetch all rows."""

    @contextmanager
    @abstractmethod
    def transaction(self) -> Iterator[None]:
        """Run statements in a transaction."""

    @abstractmethod
    def close(self) -> None:
        """Close any open resources."""
