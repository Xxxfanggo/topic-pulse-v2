"""Conversation history storage for sessions."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .state import utc_now


@dataclass(slots=True)
class SessionMessage:
    """One persisted chat message in a session."""

    role: str
    content: str
    created_at: datetime = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)


class SessionHistoryStore(ABC):
    """Storage interface for session conversation history."""

    @abstractmethod
    def append(self, session_id: str, message: SessionMessage) -> None:
        """Append one message to a session history."""

    def append_many(self, session_id: str, messages: list[SessionMessage]) -> None:
        """Append multiple messages to a session history."""
        for message in messages:
            self.append(session_id, message)

    @abstractmethod
    def list(self, session_id: str, limit: int | None = None) -> list[SessionMessage]:
        """Read messages for a session, oldest first."""

    @abstractmethod
    def delete(self, session_id: str) -> None:
        """Delete a session history."""


class MarkdownSessionHistoryStore(SessionHistoryStore):
    """Persist session conversation history as Markdown files."""

    _MESSAGE_PATTERN = re.compile(
        r"<!--\s*message\s*\n(?P<meta>.*?)\n-->\n"
        r"(?P<content>.*?)"
        r"\n<!--\s*/message\s*-->",
        flags=re.DOTALL,
    )

    def __init__(self, root_dir: str | Path | None = None) -> None:
        self._root_dir = Path(root_dir) if root_dir else Path(__file__).parent / "data"
        self._root_dir.mkdir(parents=True, exist_ok=True)

    @property
    def root_dir(self) -> Path:
        return self._root_dir

    def append(self, session_id: str, message: SessionMessage) -> None:
        path = self.path_for(session_id)
        if not path.exists():
            path.write_text(
                f"# Session {session_id}\n\n## Messages\n\n",
                encoding="utf-8",
            )
        with path.open("a", encoding="utf-8", newline="\n") as file:
            file.write(self._format_message(message))

    def list(self, session_id: str, limit: int | None = None) -> list[SessionMessage]:
        path = self.path_for(session_id)
        if not path.exists():
            return []

        content = path.read_text(encoding="utf-8")
        messages: list[SessionMessage] = []
        for match in self._MESSAGE_PATTERN.finditer(content):
            try:
                metadata = json.loads(match.group("meta"))
            except json.JSONDecodeError:
                continue
            created_at = self._parse_datetime(metadata.get("created_at"))
            messages.append(
                SessionMessage(
                    role=str(metadata.get("role") or ""),
                    content=match.group("content").strip(),
                    created_at=created_at,
                    metadata=dict(metadata.get("metadata") or {}),
                )
            )
        if limit is not None and limit >= 0:
            return messages[-limit:]
        return messages

    def delete(self, session_id: str) -> None:
        path = self.path_for(session_id)
        if path.exists():
            path.unlink()

    def path_for(self, session_id: str) -> Path:
        filename = f"{self._safe_session_id(session_id)}.md"
        path = (self._root_dir / filename).resolve()
        root = self._root_dir.resolve()
        if root not in path.parents and path != root:
            raise ValueError(f"Invalid session_id path: {session_id}")
        return path

    @staticmethod
    def _format_message(message: SessionMessage) -> str:
        metadata = {
            "role": message.role,
            "created_at": message.created_at.isoformat(),
            "metadata": message.metadata,
        }
        return (
            "<!-- message\n"
            f"{json.dumps(metadata, ensure_ascii=False, default=str)}\n"
            "-->\n"
            f"{message.content.rstrip()}\n"
            "<!-- /message -->\n\n"
        )

    @staticmethod
    def _parse_datetime(value: Any) -> datetime:
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                pass
        return utc_now()

    @staticmethod
    def _safe_session_id(session_id: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", session_id.strip())
        if not safe:
            raise ValueError("session_id cannot be empty.")
        return safe
