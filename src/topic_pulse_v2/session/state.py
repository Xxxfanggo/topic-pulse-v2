"""Session state management."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SessionStatus(str, Enum):
    CREATED = "created"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CLOSED = "closed"


ALLOWED_TRANSITIONS: dict[SessionStatus, set[SessionStatus]] = {
    SessionStatus.CREATED: {SessionStatus.ACTIVE, SessionStatus.CLOSED},
    SessionStatus.ACTIVE: {
        SessionStatus.PAUSED,
        SessionStatus.COMPLETED,
        SessionStatus.FAILED,
        SessionStatus.CLOSED,
    },
    SessionStatus.PAUSED: {SessionStatus.ACTIVE, SessionStatus.CLOSED},
    SessionStatus.COMPLETED: {SessionStatus.ACTIVE, SessionStatus.CLOSED},
    SessionStatus.FAILED: {SessionStatus.ACTIVE, SessionStatus.CLOSED},
    SessionStatus.CLOSED: set(),
}


@dataclass(slots=True)
class Session:
    """Session data and state."""

    id: str = field(default_factory=lambda: str(uuid4()))
    status: SessionStatus = SessionStatus.CREATED
    context: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def transition_to(self, status: SessionStatus) -> None:
        if status not in ALLOWED_TRANSITIONS[self.status]:
            raise ValueError(f"Invalid session transition: {self.status} -> {status}")
        self.status = status
        self.updated_at = utc_now()
