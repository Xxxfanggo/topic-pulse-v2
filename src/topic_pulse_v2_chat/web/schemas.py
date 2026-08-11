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
    topic_update: dict = Field(default_factory=dict)


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
    topic_update: dict = Field(default_factory=dict)
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


class CreateTopicRefreshJobRequest(BaseModel):
    trigger: str = Field(default="interval", description="Scheduler trigger type: interval or cron.")
    interval_minutes: int = Field(default=60, ge=1, description="Refresh interval in minutes.")
    cron_hour: int | None = Field(default=None, ge=0, le=23, description="Cron hour for daily refresh.")
    cron_minute: int | None = Field(default=None, ge=0, le=59, description="Cron minute for daily refresh.")
    enabled: bool = Field(default=True, description="Whether the created topic refresh job is active.")


class SchedulerJobResponse(BaseModel):
    id: str
    task_name: str
    trigger: str
    trigger_args: dict = Field(default_factory=dict)
    args: list = Field(default_factory=list)
    kwargs: dict = Field(default_factory=dict)
    status: str
    name: str = ""
    description: str = ""
    metadata: dict = Field(default_factory=dict)
    created_at: str
    updated_at: str


class SchedulerJobListResponse(BaseModel):
    jobs: list[SchedulerJobResponse] = Field(default_factory=list)


class JobRunResponse(BaseModel):
    id: str
    job_id: str
    task_name: str
    status: str
    started_at: str
    finished_at: str | None = None
    duration_ms: float | None = None
    error: str = ""
    result_summary: str = ""
    metadata: dict = Field(default_factory=dict)


class JobRunListResponse(BaseModel):
    runs: list[JobRunResponse] = Field(default_factory=list)
