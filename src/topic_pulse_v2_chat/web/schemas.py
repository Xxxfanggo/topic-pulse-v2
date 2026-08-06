"""Request and response models for the web chat API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "topic_pulse_v2_chat.web"


class ChatMessage(BaseModel):
    role: str = Field(description="Message role, such as user or assistant.")
    content: str = Field(description="Message content.")


class SessionChatMessage(ChatMessage):
    created_at: str
    completed: bool | None = None
    query_key: str | None = None
    reference_data: list[dict[str, str]] = Field(default_factory=list)


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
    query_key: str | None = None
    reference_data: list[dict[str, str]] = Field(default_factory=list)
    steps: list[dict] = Field(default_factory=list)


class TopicSummary(BaseModel):
    id: str
    title: str
    filename: str
    updated_at: str
    size: int
    preview: str = ""


class TopicListResponse(BaseModel):
    topics: list[TopicSummary] = Field(default_factory=list)


class TopicDetailResponse(TopicSummary):
    content: str


class SessionSummary(BaseModel):
    id: str
    title: str
    updated_at: str
    message_count: int
    preview: str = ""


class SessionListResponse(BaseModel):
    sessions: list[SessionSummary] = Field(default_factory=list)


class SessionDetailResponse(SessionSummary):
    messages: list[SessionChatMessage] = Field(default_factory=list)
