"""SQLite index for user-scoped Markdown topics."""

from __future__ import annotations

import re
import secrets
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
class TopicRecord:
    id: str
    user_id: str
    title: str
    markdown_path: str
    created_at: datetime
    updated_at: datetime


class SQLiteTopicStore:
    """Persistent user/topic to Markdown-file mapping."""

    def __init__(
        self,
        *,
        db_path: str | Path = "data/topic_pulse.sqlite3",
        topics_dir: str | Path = "data/topics",
    ) -> None:
        self.db_path = Path(db_path)
        self.topics_dir = Path(topics_dir)

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.topics_dir.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            with connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS topics (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        title TEXT NOT NULL,
                        markdown_path TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(user_id, title)
                    );

                    CREATE INDEX IF NOT EXISTS idx_topics_user_updated
                        ON topics(user_id, updated_at DESC);
                    """
                )

    def create_or_get_topic(self, *, user_id: str, title: str) -> TopicRecord:
        self._validate_user_id(user_id)
        title = self._normalize_title(title)
        self.initialize()
        existing = self.get_by_title(user_id=user_id, title=title)
        if existing is not None:
            return existing

        now = utc_now()
        topic_id = f"tpc_{secrets.token_urlsafe(12)}"
        markdown_path = str(self.path_for_topic(topic_id, title))
        with closing(self._connect()) as connection:
            with connection:
                try:
                    connection.execute(
                        """
                        INSERT INTO topics (
                            id, user_id, title, markdown_path, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            topic_id,
                            user_id,
                            title,
                            markdown_path,
                            _datetime_to_text(now),
                            _datetime_to_text(now),
                        ),
                    )
                except sqlite3.IntegrityError:
                    return self.get_by_title(user_id=user_id, title=title)
        return TopicRecord(
            id=topic_id,
            user_id=user_id,
            title=title,
            markdown_path=markdown_path,
            created_at=now,
            updated_at=now,
        )

    def get_topic(self, *, user_id: str, topic_id: str) -> TopicRecord:
        self._validate_user_id(user_id)
        self.initialize()
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM topics WHERE user_id = ? AND id = ?",
                (user_id, topic_id),
            ).fetchone()
        if row is None:
            raise LookupError(f"Topic not found: {topic_id}")
        return self._record_from_row(dict(row))

    def get_by_title(self, *, user_id: str, title: str) -> TopicRecord | None:
        self._validate_user_id(user_id)
        title = self._normalize_title(title)
        self.initialize()
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM topics WHERE user_id = ? AND title = ?",
                (user_id, title),
            ).fetchone()
        return self._record_from_row(dict(row)) if row is not None else None

    def list_topics(self, *, user_id: str) -> list[TopicRecord]:
        self._validate_user_id(user_id)
        self.initialize()
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM topics WHERE user_id = ? ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
        return [self._record_from_row(dict(row)) for row in rows]

    def touch_topic(self, topic_id: str, *, updated_at: datetime | None = None) -> None:
        self.initialize()
        value = _datetime_to_text(updated_at or utc_now())
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    "UPDATE topics SET updated_at = ? WHERE id = ?",
                    (value, topic_id),
                )

    def path_for_topic(self, topic_id: str, title: str) -> Path:
        safe_title = self._safe_title(title)
        path = (self.topics_dir / f"{topic_id}-{safe_title}.md").resolve()
        root = self.topics_dir.resolve()
        if root not in path.parents:
            raise ValueError("topic markdown path must stay inside topics_dir.")
        return path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _record_from_row(row: dict) -> TopicRecord:
        return TopicRecord(
            id=row["id"],
            user_id=row["user_id"],
            title=row["title"],
            markdown_path=row["markdown_path"],
            created_at=_datetime_from_text(row["created_at"]),
            updated_at=_datetime_from_text(row["updated_at"]),
        )

    @staticmethod
    def _validate_user_id(user_id: str) -> None:
        if not str(user_id or "").strip():
            raise ValueError("user_id cannot be empty.")

    @staticmethod
    def _normalize_title(title: str) -> str:
        normalized = " ".join(str(title or "").strip().split())
        if not normalized:
            raise ValueError("topic title cannot be empty.")
        return normalized

    @staticmethod
    def _safe_title(title: str) -> str:
        sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title.strip())
        sanitized = re.sub(r"\s+", "-", sanitized).strip(" .-")
        return sanitized[:80] or "topic"
