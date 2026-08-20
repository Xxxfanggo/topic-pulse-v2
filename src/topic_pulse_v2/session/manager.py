"""Session manager and persistence boundary."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .history import (
    MarkdownSessionHistoryStore,
    SessionHistoryStore,
    SessionMessage,
)
from .state import Session, SessionStatus, utc_now
from .store import SQLiteSessionStore


class SessionRepository(ABC):
    """Storage interface for sessions."""

    @abstractmethod
    def save(self, session: Session) -> Session:
        """Persist a session."""

    @abstractmethod
    def get(self, session_id: str) -> Session:
        """Read a session."""

    @abstractmethod
    def delete(self, session_id: str) -> None:
        """Delete a session."""

    @abstractmethod
    def list(self) -> list[Session]:
        """List sessions."""


class InMemorySessionRepository(SessionRepository):
    """Process-local session repository."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def save(self, session: Session) -> Session:
        self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> Session:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise LookupError(f"Session not found: {session_id}") from exc

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id)

    def list(self) -> list[Session]:
        return sorted(self._sessions.values(), key=lambda session: session.updated_at, reverse=True)


class SessionManager:
    """High-level API for session lifecycle, context, and data."""

    def __init__(
        self,
        repository: SessionRepository | None = None,
        history_store: SessionHistoryStore | None = None,
        session_store: SQLiteSessionStore | None = None,
    ) -> None:
        self._repository = repository or InMemorySessionRepository()
        self._session_store = session_store
        self._history_store = history_store or MarkdownSessionHistoryStore(session_store=session_store)

    def create(
        self,
        *,
        context: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        user_id: str | None = None,
        activate: bool = True,
    ) -> Session:
        session = Session(
            context=context or {},
            data=data or {},
            metadata=metadata or {},
        )
        if user_id:
            session.context["user_id"] = user_id
            self._ensure_session_record(session.id, user_id, status=(SessionStatus.ACTIVE if activate else session.status).value)
        if activate:
            session.transition_to(SessionStatus.ACTIVE)
        saved = self._repository.save(session)
        self._touch_session_record(saved)
        return saved

    def get(self, session_id: str) -> Session:
        return self._repository.get(session_id)

    def ensure(
        self,
        session_id: str,
        *,
        context: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        user_id: str | None = None,
        activate: bool = True,
    ) -> Session:
        try:
            session = self.get(session_id)
            if user_id:
                session.context["user_id"] = user_id
                self._ensure_session_record(session.id, user_id, status=session.status.value)
            return session
        except LookupError:
            session = Session(
                id=session_id,
                context=context or {},
                data=data or {},
                metadata=metadata or {},
            )
            if user_id:
                session.context["user_id"] = user_id
                self._ensure_session_record(session.id, user_id, status=(SessionStatus.ACTIVE if activate else session.status).value)
            if activate:
                session.transition_to(SessionStatus.ACTIVE)
            saved = self._repository.save(session)
            self._touch_session_record(saved)
            return saved

    def list(self) -> list[Session]:
        return self._repository.list()

    def transition(self, session_id: str, status: SessionStatus | str) -> Session:
        session = self.get(session_id)
        session.transition_to(SessionStatus(status))
        saved = self._repository.save(session)
        self._touch_session_record(saved)
        return saved

    def set_context(self, session_id: str, key: str, value: Any) -> Session:
        session = self.get(session_id)
        session.context[key] = value
        session.updated_at = utc_now()
        return self._repository.save(session)

    def get_context(self, session_id: str, key: str, default: Any = None) -> Any:
        return self.get(session_id).context.get(key, default)

    def set_data(self, session_id: str, key: str, value: Any) -> Session:
        session = self.get(session_id)
        session.data[key] = value
        session.updated_at = utc_now()
        return self._repository.save(session)

    def get_data(self, session_id: str, key: str, default: Any = None) -> Any:
        return self.get(session_id).data.get(key, default)

    def delete(self, session_id: str) -> None:
        user_id = self._session_user_id(session_id)
        self._repository.delete(session_id)
        self._history_store.delete(session_id, user_id=user_id)
        if user_id and self._session_store is not None:
            self._session_store.delete_session(user_id=user_id, session_id=session_id)

    def append_history(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
        user_id: str | None = None,
    ) -> None:
        resolved_user_id = user_id or self._session_user_id(session_id)
        self._history_store.append(
            session_id,
            SessionMessage(
                role=role,
                content=content,
                metadata=metadata or {},
            ),
            user_id=resolved_user_id,
        )
        if resolved_user_id:
            self._ensure_session_record(session_id, resolved_user_id)

    def append_history_many(
        self,
        session_id: str,
        messages: list[SessionMessage],
        *,
        user_id: str | None = None,
    ) -> None:
        resolved_user_id = user_id or self._session_user_id(session_id)
        self._history_store.append_many(session_id, messages, user_id=resolved_user_id)
        if resolved_user_id:
            self._ensure_session_record(session_id, resolved_user_id)

    def get_history(
        self,
        session_id: str,
        *,
        limit: int | None = None,
        user_id: str | None = None,
    ) -> list[SessionMessage]:
        return self._history_store.list(session_id, limit=limit, user_id=user_id or self._session_user_id(session_id))

    def _session_user_id(self, session_id: str) -> str | None:
        try:
            value = self.get(session_id).context.get("user_id")
        except LookupError:
            return None
        return str(value) if value else None

    def _ensure_session_record(self, session_id: str, user_id: str, *, status: str = "active") -> None:
        if self._session_store is not None:
            self._session_store.create_or_get_session(
                user_id=user_id,
                session_id=session_id,
                status=status,
            )

    def _touch_session_record(self, session: Session) -> None:
        if self._session_store is None:
            return
        user_id = str(session.context.get("user_id") or "")
        if user_id:
            self._session_store.touch_session(session.id, status=session.status.value)
