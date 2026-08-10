"""Web-facing ReActAgent runtime."""

from __future__ import annotations

from dataclasses import asdict
from collections.abc import Iterator
from threading import Lock
from typing import Any

from topic_pulse_v2.llm_call import LLMClient, MiniMaxLLMProvider
from topic_pulse_v2.memory import InMemoryStore
from topic_pulse_v2.process import ReActAgent, ReActConfig, ReActResult, ReActStreamEvent
from topic_pulse_v2.session import SessionManager
from topic_pulse_v2.tool_register import ToolRegistry


class ReactChatService:
    """Small singleton wrapper around the ReAct runtime used by FastAPI."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._llm_client = LLMClient(
            {"minimax": MiniMaxLLMProvider()},
            default_provider="minimax",
        )
        self._memory = InMemoryStore()
        self._session_manager = SessionManager()
        self._tool_registry = ToolRegistry()
        self._config = ReActConfig(max_steps=20)
        self._agent = ReActAgent(
            llm_client=self._llm_client,
            tool_registry=self._tool_registry,
            memory_store=self._memory,
            session_manager=self._session_manager,
            config=self._config,
        )

    def chat(
        self,
        *,
        user_id: str,
        message: str,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ReActResult:
        # The current in-memory stores are process-local and not thread-safe.
        # Keep requests serialized until a persistent store is introduced.
        with self._lock:
            return self._agent.run(
                user_id=user_id,
                query=message,
                session_id=session_id,
                provider="minimax",
                metadata=metadata,
            )

    def chat_stream(
        self,
        *,
        user_id: str,
        message: str,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[ReActStreamEvent]:
        # The current in-memory stores are process-local and not thread-safe.
        # Keep the whole stream serialized until a persistent store is introduced.
        with self._lock:
            yield from self._agent.stream(
                user_id=user_id,
                query=message,
                session_id=session_id,
                provider="minimax",
                metadata=metadata,
            )


def react_result_steps_to_dict(result: ReActResult) -> list[dict[str, Any]]:
    steps = []
    for step in result.steps:
        payload = asdict(step)
        tool_result = payload.get("tool_result")
        if tool_result is not None:
            payload["tool_result"] = tool_result
        steps.append(payload)
    return steps
