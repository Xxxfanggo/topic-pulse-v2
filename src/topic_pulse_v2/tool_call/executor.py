"""Local tool execution."""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from time import perf_counter
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from topic_pulse_v2.tool_register.registry import ToolRegistry


@dataclass(slots=True)
class ToolCallRequest:
    """A request to invoke one registered tool."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    call_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolCallResult:
    """Normalized result for a tool invocation."""

    name: str
    success: bool
    result: Any = None
    error: str | None = None
    call_id: str | None = None
    elapsed_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class ToolExecutor:
    """Executes tools from a registry and normalizes errors."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> ToolCallResult:
        return self.call_request(ToolCallRequest(name=name, arguments=arguments or {}))

    def call_request(self, request: ToolCallRequest) -> ToolCallResult:
        started = perf_counter()
        try:
            spec = self._registry.get(request.name)
            arguments = self._arguments_with_context(spec.handler, request.arguments, request.metadata)
            self._validate_arguments(spec.handler, arguments)
            value = spec.handler(**arguments)
            if inspect.isawaitable(value):
                value = self._run_awaitable(value)
            return ToolCallResult(
                name=request.name,
                success=True,
                result=value,
                call_id=request.call_id,
                elapsed_ms=self._elapsed_ms(started),
                metadata=request.metadata,
            )
        except Exception as exc:
            return ToolCallResult(
                name=request.name,
                success=False,
                error=f"{type(exc).__name__}: {exc}",
                call_id=request.call_id,
                elapsed_ms=self._elapsed_ms(started),
                metadata=request.metadata,
            )

    def batch_call(self, requests: list[ToolCallRequest]) -> list[ToolCallResult]:
        return [self.call_request(request) for request in requests]

    @staticmethod
    def _validate_arguments(handler: Any, arguments: dict[str, Any]) -> None:
        signature = inspect.signature(handler)
        signature.bind(**arguments)

    @staticmethod
    def _arguments_with_context(
        handler: Any,
        arguments: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        signature = inspect.signature(handler)
        merged = dict(arguments)
        for key in ("user_id",):
            if key in merged or key not in metadata or key not in signature.parameters:
                continue
            merged[key] = metadata[key]
        return merged

    @staticmethod
    def _run_awaitable(awaitable: Any) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(awaitable)
        raise RuntimeError("Cannot run async tool from a running event loop; use async_call.")

    @staticmethod
    def _elapsed_ms(started: float) -> float:
        return round((perf_counter() - started) * 1000, 3)

    async def async_call(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> ToolCallResult:
        return await self.async_call_request(
            ToolCallRequest(name=name, arguments=arguments or {})
        )

    async def async_call_request(self, request: ToolCallRequest) -> ToolCallResult:
        started = perf_counter()
        try:
            spec = self._registry.get(request.name)
            arguments = self._arguments_with_context(spec.handler, request.arguments, request.metadata)
            self._validate_arguments(spec.handler, arguments)
            value = spec.handler(**arguments)
            if inspect.isawaitable(value):
                value = await value
            return ToolCallResult(
                name=request.name,
                success=True,
                result=value,
                call_id=request.call_id,
                elapsed_ms=self._elapsed_ms(started),
                metadata=request.metadata,
            )
        except Exception as exc:
            return ToolCallResult(
                name=request.name,
                success=False,
                error=f"{type(exc).__name__}: {exc}",
                call_id=request.call_id,
                elapsed_ms=self._elapsed_ms(started),
                metadata=request.metadata,
            )
