"""SQLite database implementation."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import RLock

from topic_pulse_v2.config import database_path

from .base import Database, Params, Row


class SQLiteDatabase(Database):
    """Thin SQLite adapter behind the project database interface."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else database_path()
        self._connection: sqlite3.Connection | None = None
        self._transaction_depth = 0
        self._lock = RLock()

    def initialize(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = self._connect()
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.commit()

    def execute(self, sql: str, params: Params = None) -> int:
        with self._lock:
            connection = self._connect()
            cursor = connection.execute(sql, params or ())
            if self._transaction_depth == 0:
                connection.commit()
            return cursor.rowcount

    def execute_script(self, sql: str) -> None:
        with self._lock:
            connection = self._connect()
            connection.executescript(sql)
            if self._transaction_depth == 0:
                connection.commit()

    def fetch_one(self, sql: str, params: Params = None) -> Row | None:
        with self._lock:
            cursor = self._connect().execute(sql, params or ())
            row = cursor.fetchone()
            return dict(row) if row is not None else None

    def fetch_all(self, sql: str, params: Params = None) -> list[Row]:
        with self._lock:
            cursor = self._connect().execute(sql, params or ())
            return [dict(row) for row in cursor.fetchall()]

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self._lock.acquire()
        is_outermost = False
        entered = False
        try:
            connection = self._connect()
            is_outermost = self._transaction_depth == 0
            if is_outermost:
                connection.execute("BEGIN")
            self._transaction_depth += 1
            entered = True
            try:
                yield
            except Exception:
                if is_outermost:
                    connection.rollback()
                raise
            else:
                if is_outermost:
                    connection.commit()
        finally:
            if entered:
                self._transaction_depth -= 1
            self._lock.release()

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def _connect(self) -> sqlite3.Connection:
        if self._connection is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(self.path, check_same_thread=False)
            self._connection.row_factory = sqlite3.Row
        return self._connection
