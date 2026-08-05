"""Interfaces for managing model context before LLM calls."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from topic_pulse_v2.llm_call import Message


@dataclass(slots=True)
class ContextTrimRequest:
    """Input for context assembly and trimming."""

    messages: list[Message]
    tools: list[dict[str, Any]] = field(default_factory=list)
    session_id: str | None = None
    user_id: str | None = None
    query: str | None = None
    step_index: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ContextTrimResult:
    """Context returned to the process before calling the LLM."""

    messages: list[Message]
    metadata: dict[str, Any] = field(default_factory=dict)


class ContextTrimmer(ABC):
    """Interface for future context size management, trimming, and compression."""

    @abstractmethod
    def trim(self, request: ContextTrimRequest) -> ContextTrimResult:
        """Return the messages that should be sent to the LLM."""


class PassthroughContextTrimmer(ContextTrimmer):
    """Default implementation that keeps the context unchanged."""

    def trim(self, request: ContextTrimRequest) -> ContextTrimResult:
        return ContextTrimResult(
            messages=list(request.messages),
            metadata={
                "strategy": "passthrough",
                "original_message_count": len(request.messages),
                "trimmed_message_count": len(request.messages),
            },
        )
