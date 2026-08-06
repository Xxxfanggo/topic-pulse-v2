"""Interfaces for swappable large language model providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from .types import LLMRequest, LLMResponse, LLMStreamEvent, Message


class LLMProvider(ABC):
    """Abstract base class for model providers."""

    @abstractmethod
    def call(self, request: LLMRequest) -> LLMResponse:
        """Execute one model call."""

    def stream(self, request: LLMRequest) -> Iterator[LLMStreamEvent]:
        """Execute one model call and yield stream events.

        Providers that do not support native streaming inherit this compatible
        fallback, so callers can adopt the stream API without losing rollback.
        """

        response = self.call(request)
        if response.content:
            yield LLMStreamEvent(type="delta", content=response.content)
        yield LLMStreamEvent(type="done", response=response)


@dataclass(slots=True)
class LLMConfig:
    """Configuration used to build or identify an LLM provider."""

    provider: str
    model: str | None = None
    options: dict[str, Any] = field(default_factory=dict)


class LLMClient:
    """Facade that allows model providers to be registered and swapped."""

    def __init__(
        self,
        providers: Mapping[str, LLMProvider] | None = None,
        default_provider: str | None = None,
    ) -> None:
        self._providers: dict[str, LLMProvider] = dict(providers or {})
        self._default_provider = default_provider

    @property
    def default_provider(self) -> str | None:
        return self._default_provider

    def register_provider(
        self,
        name: str,
        provider: LLMProvider,
        *,
        set_default: bool = False,
    ) -> None:
        if not name:
            raise ValueError("Provider name cannot be empty.")
        self._providers[name] = provider
        if set_default or self._default_provider is None:
            self._default_provider = name

    def unregister_provider(self, name: str) -> None:
        self._providers.pop(name)
        if self._default_provider == name:
            self._default_provider = next(iter(self._providers), None)

    def get_provider(self, name: str | None = None) -> LLMProvider:
        provider_name = name or self._default_provider
        if provider_name is None:
            raise LookupError("No LLM provider has been configured.")
        try:
            return self._providers[provider_name]
        except KeyError as exc:
            raise LookupError(f"LLM provider not found: {provider_name}") from exc

    def list_providers(self) -> list[str]:
        return sorted(self._providers)

    def call(
        self,
        messages: list[Message],
        *,
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LLMResponse:
        request = LLMRequest(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools or [],
            metadata=metadata or {},
        )
        return self.get_provider(provider).call(request)

    def stream(
        self,
        messages: list[Message],
        *,
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[LLMStreamEvent]:
        request = LLMRequest(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools or [],
            metadata=metadata or {},
        )
        yield from self.get_provider(provider).stream(request)
