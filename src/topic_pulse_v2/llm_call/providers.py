"""Built-in LLM providers useful for local development and tests."""

from __future__ import annotations

import os
from typing import Any

from .base import LLMProvider
from .types import LLMRequest, LLMResponse, Message


class MiniMaxLLMProvider(LLMProvider):
    """MiniMax chat provider backed by the OpenAI-compatible API.

    This provider uses ``langchain_openai.ChatOpenAI`` lazily so the core
    scaffold can still be imported without optional MiniMax dependencies.
    Set ``MINIMAX_API_KEY`` in the environment, or pass ``api_key`` directly.
    """

    DEFAULT_MODEL = "MiniMax-M3"
    DEFAULT_BASE_URL = "https://api.minimaxi.com/v1"

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        client: Any | None = None,
        client_options: dict[str, Any] | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = client
        self._client_options = client_options or {}

    def call(self, request: LLMRequest) -> LLMResponse:
        client = self._client or self._build_client(request)
        messages = self._to_langchain_messages(request.messages)
        if request.tools and hasattr(client, "bind_tools"):
            client = client.bind_tools(request.tools)
        ai_message = client.invoke(messages)
        content = getattr(ai_message, "content", ai_message)
        response_metadata = getattr(ai_message, "response_metadata", {}) or {}
        tool_calls = getattr(ai_message, "tool_calls", []) or []

        return LLMResponse(
            content=str(content),
            model=request.model or self.model,
            raw=ai_message,
            tool_calls=list(tool_calls),
            usage=response_metadata.get("token_usage", {})
            or response_metadata.get("usage", {}),
            metadata={"response_metadata": response_metadata},
        )

    def _build_client(self, request: LLMRequest) -> Any:
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise ImportError(
                "MiniMaxLLMProvider requires langchain-openai. "
                "Install it with: pip install langchain-openai"
            ) from exc

        api_key = self.api_key or os.getenv("MINIMAX_API_KEY")
        if not api_key:
            raise ValueError(
                "MiniMax API key is missing. Set MINIMAX_API_KEY or pass api_key."
            )

        options: dict[str, Any] = {
            "model": request.model or self.model,
            "base_url": self.base_url,
            "api_key": api_key,
            **self._client_options,
        }
        temperature = request.temperature if request.temperature is not None else self.temperature
        max_tokens = request.max_tokens if request.max_tokens is not None else self.max_tokens
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens is not None:
            options["max_tokens"] = max_tokens

        return ChatOpenAI(**options)

    @staticmethod
    def _to_langchain_messages(messages: list[Message]) -> list[Any]:
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

        converted = []
        for message in messages:
            if message.role == "system":
                converted.append(SystemMessage(content=message.content))
                continue
            if message.role == "user":
                converted.append(HumanMessage(content=message.content))
                continue
            if message.role == "assistant":
                converted.append(
                    AIMessage(
                        content=message.content,
                        tool_calls=message.metadata.get("tool_calls") or [],
                    )
                )
                continue
            if message.role == "tool":
                if not message.tool_call_id:
                    raise ValueError("Tool message requires tool_call_id.")
                converted.append(
                    ToolMessage(
                        content=message.content,
                        name=message.name,
                        tool_call_id=message.tool_call_id,
                    )
                )
                continue
            raise ValueError(f"Unsupported message role: {message.role}")
        return converted
