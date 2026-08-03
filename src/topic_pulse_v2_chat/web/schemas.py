"""Request and response models for the web chat API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "topic_pulse_v2_chat.web"


class ChatMessage(BaseModel):
    role: str = Field(description="Message role, such as user or assistant.")
    content: str = Field(description="Message content.")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, description="User input message.")
    user_id: str = Field(min_length=1, description="Anonymous or logged-in user id.")
    session_id: str | None = Field(default=None, description="Optional chat session id.")
    history: list[ChatMessage] = Field(default_factory=list, description="Recent chat history.")


class ChatResponse(BaseModel):
    answer: str
    session_id: str
    user_id: str
    completed: bool
    steps: list[dict] = Field(default_factory=list)
