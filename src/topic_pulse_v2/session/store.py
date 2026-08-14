"""SQLite index for user-scoped conversation sessions."""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _datetime_to_text(value: datetime) -> str:
    return value.isoformat()


def _datetime_from_text(value: str) -> datetime:
    return datetime.fromisoformat(value)


@dataclass(slots=True)
class SessionRecord:
    id: str
    user_id: str
    markdown_path: str
    status: str
    created_at: datetime
    updated_at: datetime


class SQLiteSessionStore:
    """Persistent user/session to Markdown-file mapping."""

    def __init__(
        self,
        *,
        db_path: str | Path = "data/topic_pulse.sqlite3",
        sessions_dir: str | Path | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.sessions_dir = Path(sessions_dir) if sessions_dir else Path(__file__).parent / "data"

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            with connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS chat_sessions (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        markdown_path TEXT NOT NULL,
                        status TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_updated
                        ON chat_sessions(user_id, updated_at DESC);
                    """
                )

    def create_or_get_session(
        self,
        *,
        user_id: str,
        session_id: str,
        status: str = "active",
    ) -> SessionRecord:
        self._validate_user_id(user_id)
        session_id = self._safe_session_id(session_id)
        self.initialize()
        existing = self.get_session(user_id=user_id, session_id=session_id)
        if existing is not None:
            return existing

        now = utc_now()
        markdown_path = str(self.path_for_session(session_id))
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO chat_sessions (
                        id, user_id, markdown_path, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        user_id,
                        markdown_path,
                        status,
                        _datetime_to_text(now),
                        _datetime_to_text(now),
                    ),
                )
        return SessionRecord(
            id=session_id,
            user_id=user_id,
            markdown_path=markdown_path,
            status=status,
            created_at=now,
            updated_at=now,
        )

    def get_session(self, *, user_id: str, session_id: str) -> SessionRecord | None:
        self._validate_user_id(user_id)
        self.initialize()
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM chat_sessions WHERE user_id = ? AND id = ?",
                (user_id, session_id),
            ).fetchone()
        return self._record_from_row(dict(row)) if row is not None else None

    def require_session(self, *, user_id: str, session_id: str) -> SessionRecord:
        record = self.get_session(user_id=user_id, session_id=session_id)
        if record is None:
            raise LookupError(f"Session not found: {session_id}")
        return record

    def list_sessions(self, *, user_id: str) -> list[SessionRecord]:
        self._validate_user_id(user_id)
        self.initialize()
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM chat_sessions WHERE user_id = ? ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
        return [self._record_from_row(dict(row)) for row in rows]

    def touch_session(
        self,
        session_id: str,
        *,
        status: str | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        self.initialize()
        value = _datetime_to_text(updated_at or utc_now())
        with closing(self._connect()) as connection:
            with connection:
                if status is None:
                    connection.execute(
                        "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
                        (value, session_id),
                    )
                else:
                    connection.execute(
                        "UPDATE chat_sessions SET status = ?, updated_at = ? WHERE id = ?",
                        (status, value, session_id),
                    )

    def delete_session(self, *, user_id: str, session_id: str) -> None:
        self._validate_user_id(user_id)
        self.initialize()
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    "DELETE FROM chat_sessions WHERE user_id = ? AND id = ?",
                    (user_id, session_id),
                )

    def path_for_session(self, session_id: str) -> Path:
        safe = self._safe_session_id(session_id)
        path = (self.sessions_dir / f"{safe}.md").resolve()
        root = self.sessions_dir.resolve()
        if root not in path.parents:
            raise ValueError("session markdown path must stay inside sessions_dir.")
        return path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _record_from_row(row: dict) -> SessionRecord:
        return SessionRecord(
            id=row["id"],
            user_id=row["user_id"],
            markdown_path=row["markdown_path"],
            status=row["status"],
            created_at=_datetime_from_text(row["created_at"]),
            updated_at=_datetime_from_text(row["updated_at"]),
        )

    @staticmethod
    def _validate_user_id(user_id: str) -> None:
        if not str(user_id or "").strip():
            raise ValueError("user_id cannot be empty.")

    @staticmethod
    def _safe_session_id(session_id: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(session_id or "").strip())
        if not safe:
            raise ValueError("session_id cannot be empty.")
        return safe
