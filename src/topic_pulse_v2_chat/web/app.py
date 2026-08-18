"""FastAPI application for the browser chat UI."""

from __future__ import annotations

import json
import logging
import re
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from uuid import uuid5, NAMESPACE_URL

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from topic_pulse_v2.auth import AuthService, AuthUser
from topic_pulse_v2.config import load_env_file, session_data_dir, topics_dir
from topic_pulse_v2.scheduler import SchedulerService, ScheduledJob, ScheduledTaskRegistry, SQLiteSchedulerStore
from topic_pulse_v2.scheduler.tasks import register_builtin_tasks
from topic_pulse_v2.session import MarkdownSessionHistoryStore, SessionMessage, SQLiteSessionStore
from topic_pulse_v2.topics import SQLiteTopicStore, TopicRecord
from topic_pulse_v2.process import SQLiteHotspotStore
from topic_pulse_v2_chat.web.schemas import (
    AuthLoginRequest,
    AuthMessageResponse,
    AuthRegisterVerifyRequest,
    AuthRequestCodeRequest,
    AuthTokenResponse,
    AuthUserResponse,
    ChatRequest,
    ChatResponse,
    CreateTopicRefreshJobRequest,
    HealthResponse,
    HotspotRankingItemResponse,
    HotspotTodayResponse,
    JobRunListResponse,
    JobRunResponse,
    SchedulerJobListResponse,
    SchedulerJobResponse,
    SessionChatMessage,
    SessionDetailResponse,
    SessionListResponse,
    SessionSummary,
    TopicDetailResponse,
    TopicListResponse,
    TopicSummary,
)
from topic_pulse_v2_chat.web.react_service import ReactChatService, react_result_steps_to_dict

FRONTEND_DIST_DIR = Path(__file__).resolve().parent / "frontend" / "dist"
TOPICS_DIR = topics_dir()
SESSION_DATA_DIR = session_data_dir()
logger = logging.getLogger(__name__)
load_env_file()


class ChatRuntime(Protocol):
    def chat(
        self,
        *,
        user_id: str,
        message: str,
        session_id: str | None = None,
        metadata: dict | None = None,
    ):
        ...


class SchedulerRuntime(Protocol):
    def start(self) -> None:
        ...

    def shutdown(self, *, wait: bool = False) -> None:
        ...

    def add_job(self, job: ScheduledJob) -> ScheduledJob:
        ...

    def pause_job(self, job_id: str) -> ScheduledJob:
        ...

    def resume_job(self, job_id: str) -> ScheduledJob:
        ...

    async def run_job_now(self, job_id: str):
        ...

    def list_jobs(self) -> list[ScheduledJob]:
        ...

    def list_runs(self, job_id: str | None = None, *, limit: int = 50):
        ...


class AuthRuntime(Protocol):
    def initialize(self) -> None:
        ...

    def request_registration_code(self, email: str) -> None:
        ...

    def register_with_code(self, *, email: str, code: str, password: str):
        ...

    def login(self, *, email: str, password: str):
        ...

    def authenticate_token(self, token: str) -> AuthUser:
        ...


_STREAM_END = object()
GUEST_USER_PREFIX = "guest_"
GUEST_SESSION_LIMIT = 3
GUEST_LIMIT_ERROR = "访客最多创建 3 个对话，请登录后继续。"
GUEST_SCHEDULE_ERROR = "访客不能创建定时调度任务，请登录后使用。"


def _next_stream_event(iterator):
    return next(iterator, _STREAM_END)


def _topic_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            if title:
                return title
    return fallback


def _topic_preview(content: str) -> str:
    paragraphs = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("- "):
            continue
        paragraphs.append(stripped)
        if len(" ".join(paragraphs)) > 140:
            break
    return " ".join(paragraphs)[:180]


def _topic_summary(path: Path, *, topic_id: str | None = None, title: str | None = None, updated_at: datetime | None = None) -> TopicSummary:
    content = path.read_text(encoding="utf-8")
    stat = path.stat()
    return TopicSummary(
        id=topic_id or path.stem,
        title=title or _topic_title(content, path.stem),
        filename=path.name,
        updated_at=(updated_at or datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)).isoformat(),
        size=stat.st_size,
        preview=_topic_preview(content),
    )


def _topic_store() -> SQLiteTopicStore:
    return SQLiteTopicStore(topics_dir=TOPICS_DIR)


def _hotspot_store() -> SQLiteHotspotStore:
    return SQLiteHotspotStore()


def _topic_summary_from_record(record: TopicRecord) -> TopicSummary:
    return _topic_summary(
        Path(record.markdown_path),
        topic_id=record.id,
        title=record.title,
        updated_at=record.updated_at,
    )


def _topic_path(topic_id: str) -> Path:
    if not topic_id or any(separator in topic_id for separator in ("/", "\\", "..")):
        raise FileNotFoundError(topic_id)
    path = (TOPICS_DIR / f"{topic_id}.md").resolve()
    topics_root = TOPICS_DIR.resolve()
    if topics_root not in path.parents or path.suffix.lower() != ".md":
        raise FileNotFoundError(topic_id)
    return path


def _model_data(model) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _scheduler_job_response(job: ScheduledJob) -> SchedulerJobResponse:
    return SchedulerJobResponse(
        id=job.id,
        task_name=job.task_name,
        trigger=job.trigger,
        trigger_args=job.trigger_args,
        args=job.args,
        kwargs=job.kwargs,
        status=job.status,
        name=job.name,
        description=job.description,
        metadata=job.metadata,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
    )


def _job_run_response(run) -> JobRunResponse:
    return JobRunResponse(
        id=run.id,
        job_id=run.job_id,
        task_name=run.task_name,
        status=run.status,
        started_at=run.started_at.isoformat(),
        finished_at=run.finished_at.isoformat() if run.finished_at else None,
        duration_ms=run.duration_ms,
        error=run.error,
        result_summary=run.result_summary,
        metadata=run.metadata,
    )


def _topic_refresh_job_id(topic_id: str) -> str:
    return f"topic-refresh-{uuid5(NAMESPACE_URL, f'topic-pulse/topic/{topic_id}')}"


def _default_hotspot_refresh_job_id() -> str:
    return "hotspot-refresh-weibo-hourly"


def _ensure_default_hotspot_refresh_job(scheduler: SchedulerRuntime) -> None:
    for job in scheduler.list_jobs():
        metadata = job.metadata or {}
        if metadata.get("type") == "hotspot_refresh" and metadata.get("provider") == "weibo":
            return

    now = datetime.now(timezone.utc)
    scheduler.add_job(
        ScheduledJob(
            id=_default_hotspot_refresh_job_id(),
            task_name="refresh_hotspots",
            trigger="interval",
            trigger_args={"hours": 1},
            kwargs={"provider": "weibo"},
            status="active",
            name="Refresh Weibo hotspots hourly",
            description="Refresh today's platform-level hot news ranking from Weibo.",
            metadata={
                "type": "hotspot_refresh",
                "provider": "weibo",
            },
            created_at=now,
            updated_at=now,
        )
    )


def _find_topic_refresh_job(
    scheduler: SchedulerRuntime,
    topic_id: str,
    *,
    user_id: str | None = None,
) -> ScheduledJob | None:
    for job in scheduler.list_jobs():
        metadata = job.metadata or {}
        if metadata.get("type") == "topic_refresh" and metadata.get("topic_id") == topic_id:
            if user_id is not None and metadata.get("user_id") != user_id:
                continue
            return job
    return None


def _job_belongs_to_user(job: ScheduledJob, user_id: str) -> bool:
    metadata = job.metadata or {}
    return metadata.get("user_id") == user_id


def _get_user_scheduler_job(scheduler: SchedulerRuntime, job_id: str, user_id: str) -> ScheduledJob:
    for job in scheduler.list_jobs():
        if job.id == job_id and _job_belongs_to_user(job, user_id):
            return job
    raise LookupError(f"Scheduled job not found: {job_id}")


def _topic_refresh_trigger_args(request: CreateTopicRefreshJobRequest) -> tuple[str, dict]:
    if request.trigger == "interval":
        return "interval", {"minutes": request.interval_minutes}
    if request.trigger == "cron":
        if request.cron_hour is None or request.cron_minute is None:
            raise HTTPException(status_code=422, detail="cron_hour and cron_minute are required for cron trigger")
        return "cron", {"hour": request.cron_hour, "minute": request.cron_minute}
    raise HTTPException(status_code=422, detail="trigger must be one of: interval, cron")


def _stream_event(event_type: str, **payload) -> str:
    return json.dumps({"type": event_type, **payload}, ensure_ascii=False, default=str) + "\n"


def _public_reasoning_text(value: object, limit: int = 96) -> str:
    text = _strip_think_blocks(str(value or "")).strip()
    text = re.sub(r"\s+", " ", text)
    if not text or text in {"{}", "null", "None"}:
        return ""
    if len(text) > limit:
        return f"{text[:limit].rstrip()}..."
    return text


def _tool_display_name(name: object) -> str:
    mapping = {
        "doubao_search": "联网检索",
        "topic_markdown_read_summary": "读取话题摘要",
        "topic_markdown_read_detail": "读取话题详情",
        "topic_markdown_store": "更新话题记忆",
    }
    text = str(name or "").strip()
    return mapping.get(text, text or "工具调用")


def _tool_argument_hint(arguments: object) -> str:
    if not isinstance(arguments, dict):
        return ""
    for key in ("query", "topic_name", "path"):
        value = arguments.get(key)
        if value:
            return str(value).strip()
    return ""


def _text_chunks(content: str, size: int = 12):
    for index in range(0, len(content), size):
        yield content[index : index + size]


def _partial_display_answer(content: str) -> str:
    answer = _strip_think_blocks(content).strip()
    if not answer:
        return ""

    final_answer = _partial_json_string_value(answer, "final_answer")
    if final_answer:
        nested = _partial_display_answer(final_answer)
        if nested:
            return nested
        if final_answer.lstrip().startswith("{"):
            return ""
        return final_answer

    summary = _partial_json_string_value(answer, "summary")
    if summary:
        return _strip_think_blocks(summary).strip()

    return ""


def _partial_json_string_value(content: str, key: str) -> str | None:
    key_match = re.search(rf'"{re.escape(key)}"\s*:\s*"', content)
    if not key_match:
        return None

    start = key_match.end()
    escaped = False
    chars: list[str] = []
    for char in content[start:]:
        if escaped:
            chars.append("\\" + char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            break
        chars.append(char)

    raw = "".join(chars)
    if not raw:
        return ""
    try:
        return json.loads(f'"{raw}"')
    except json.JSONDecodeError:
        return (
            raw.replace("\\n", "\n")
            .replace('\\"', '"')
            .replace("\\/", "/")
        )


def _display_answer(answer: str) -> str:
    answer = _strip_think_blocks(answer).strip()

    extracted_answer = _extract_json_string_value(answer, "final_answer")
    if extracted_answer is not None:
        return _display_answer(extracted_answer)

    payload = _answer_payload(answer)
    if payload is None:
        extracted_summary = _extract_json_text_field(answer, "summary", ("items", "next_action"))
        if extracted_summary:
            return extracted_summary
        return answer

    summary = str(payload.get("summary") or "").strip()
    if summary:
        nested_summary = _display_answer(summary)
        return nested_summary if nested_summary != summary else summary

    return answer


def _strip_mark_tags(content: str) -> str:
    return re.sub(r"</?mark>", "", content, flags=re.IGNORECASE)


def _display_answer_for_topic_update(answer: str, topic_update: dict) -> str:
    display_answer = _display_answer(answer)
    is_created = topic_update.get("status") == "created" or topic_update.get("operation") == "create"
    if is_created:
        return _strip_mark_tags(display_answer)
    return display_answer


def _answer_payload(answer: str) -> dict | None:
    answer = _strip_think_blocks(answer).strip()
    extracted_answer = _extract_json_string_value(answer, "final_answer")
    if extracted_answer is not None:
        return _answer_payload(extracted_answer)

    try:
        payload = json.loads(answer)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    summary = payload.get("summary")
    if isinstance(summary, str):
        nested_payload = _answer_payload(summary)
        if nested_payload and nested_payload.get("summary"):
            merged = dict(nested_payload)
            for key in ("query_key", "reference_data"):
                if key not in merged and payload.get(key):
                    merged[key] = payload[key]
            return merged
    return payload


def _answer_query_key(answer: str) -> str | None:
    payload = _answer_payload(answer)
    if not payload:
        return None
    value = payload.get("query_key")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _answer_reference_data(answer: str) -> list[dict[str, str]]:
    payload = _answer_payload(answer)
    if not payload:
        return []
    references = payload.get("reference_data")
    if not isinstance(references, list):
        return []

    normalized: list[dict[str, str]] = []
    seen_links: set[str] = set()
    for item in references:
        if not isinstance(item, dict):
            continue
        title = item.get("资料标题") or item.get("title")
        link = item.get("资料链接") or item.get("url") or item.get("link")
        if not title or not link:
            continue
        link_text = str(link).strip()
        if not link_text or link_text in seen_links:
            continue
        seen_links.add(link_text)
        normalized.append(
            {
                "title": str(title).strip(),
                "url": link_text,
            }
        )
    return normalized


def _answer_topic_update(answer: str) -> dict:
    payload = _answer_payload(answer)
    if not payload:
        return {}
    update = payload.get("topic_update")
    if not isinstance(update, dict):
        return {}

    def normalize_items(value) -> list[dict[str, str]]:
        if not isinstance(value, list):
            return []
        normalized = []
        for item in value:
            if isinstance(item, str):
                title = item.strip()
                if title:
                    normalized.append(
                        {
                            "date": "",
                            "title": title,
                            "source": "",
                            "url": "",
                            "summary": "",
                        }
                    )
                continue
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("标题") or "").strip()
            if not title:
                continue
            normalized.append(
                {
                    "date": str(item.get("date") or item.get("日期") or "").strip(),
                    "title": title,
                    "source": str(item.get("source") or item.get("来源") or "").strip(),
                    "url": str(item.get("url") or item.get("链接") or "").strip(),
                    "summary": str(item.get("summary") or item.get("摘要") or "").strip(),
                }
            )
        return normalized

    status = str(update.get("status") or "").strip()
    operation = str(update.get("operation") or "").strip()
    raw_new_items = normalize_items(update.get("new_items"))
    raw_initial_items = normalize_items(update.get("initial_items"))
    is_created = status == "created" or operation == "create"
    if is_created:
        initial_items = raw_initial_items or raw_new_items
        initial_count = int(update.get("initial_count") or update.get("new_count") or len(initial_items) or 0)
        return {
            "topic_name": str(update.get("topic_name") or update.get("话题") or "").strip(),
            "operation": operation or "create",
            "status": "created",
            "new_count": 0,
            "existing_count": 0,
            "new_items": [],
            "existing_items": [],
            "initial_count": initial_count,
            "initial_items": initial_items,
        }

    return {
        "topic_name": str(update.get("topic_name") or update.get("话题") or "").strip(),
        "operation": operation,
        "status": status,
        "new_count": int(update.get("new_count") or 0),
        "existing_count": int(update.get("existing_count") or 0),
        "new_items": raw_new_items,
        "existing_items": normalize_items(update.get("existing_items")),
    }


def _strip_think_blocks(content: str) -> str:
    return re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE)


def _extract_json_string_value(content: str, key: str) -> str | None:
    key_match = re.search(rf'"{re.escape(key)}"\s*:\s*"', content)
    if not key_match:
        return None

    start = key_match.end()
    escaped = False
    value_chars: list[str] = []
    for char in content[start:]:
        if escaped:
            value_chars.append("\\" + char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            try:
                return json.loads(f'"{"".join(value_chars)}"')
            except json.JSONDecodeError:
                return "".join(value_chars)
        value_chars.append(char)
    return None


def _extract_json_text_field(content: str, key: str, following_keys: tuple[str, ...]) -> str | None:
    key_match = re.search(rf'"{re.escape(key)}"\s*:\s*"', content)
    if not key_match:
        return None

    start = key_match.end()
    end_candidates = [
        match.start()
        for following_key in following_keys
        for match in (re.search(rf'"\s*,\s*"{re.escape(following_key)}"\s*:', content[start:]),)
        if match
    ]
    if not end_candidates:
        return None

    raw_value = content[start : start + min(end_candidates)]
    raw_value = raw_value.rstrip()
    if raw_value.endswith('"'):
        raw_value = raw_value[:-1]

    try:
        return json.loads(f'"{raw_value}"').strip()
    except json.JSONDecodeError:
        return (
            raw_value.replace("\\n", "\n")
            .replace('\\"', '"')
            .replace("\\/", "/")
            .strip()
        )


def _session_index_store() -> SQLiteSessionStore:
    return SQLiteSessionStore(sessions_dir=SESSION_DATA_DIR)


def _session_store(session_store: SQLiteSessionStore | None = None) -> MarkdownSessionHistoryStore:
    return MarkdownSessionHistoryStore(SESSION_DATA_DIR, session_store=session_store)


def _auth_user_response(user: AuthUser) -> AuthUserResponse:
    return AuthUserResponse(id=user.id, email=user.email, is_guest=user.is_guest)


def _auth_token_response(user: AuthUser, token: str) -> AuthTokenResponse:
    return AuthTokenResponse(
        access_token=token,
        user=_auth_user_response(user),
    )


def _guest_user_from_id(guest_id: str) -> AuthUser:
    value = str(guest_id or "").strip()
    if not re.fullmatch(r"guest_[A-Za-z0-9_.-]{8,96}", value):
        raise ValueError("Invalid guest id.")
    return AuthUser(
        id=value,
        email=f"{value[:18]}@guest.local",
        status="active",
        is_guest=True,
    )


def _visible_session_count(user_id: str) -> int:
    index_store = _session_index_store()
    store = _session_store(index_store)
    count = 0
    for record in index_store.list_sessions(user_id=user_id):
        path = Path(record.markdown_path)
        if not path.exists() or not path.is_file():
            continue
        messages = store.list(record.id, user_id=user_id)
        if _is_hidden_session(messages):
            continue
        count += 1
    return count


def _ensure_guest_can_create_session(user: AuthUser, session_id: str | None) -> None:
    if not user.is_guest:
        return
    if session_id and _session_index_store().get_session(user_id=user.id, session_id=session_id) is not None:
        return
    if _visible_session_count(user.id) >= GUEST_SESSION_LIMIT:
        raise HTTPException(status_code=403, detail=GUEST_LIMIT_ERROR)


def _ensure_registered_user(user: AuthUser) -> None:
    if user.is_guest:
        raise HTTPException(status_code=403, detail=GUEST_SCHEDULE_ERROR)



def _create_scheduler_service(chat_runtime: ChatRuntime | None = None) -> SchedulerService:
    registry = ScheduledTaskRegistry()
    register_builtin_tasks(registry, chat_runtime=chat_runtime)
    return SchedulerService(
        store=SQLiteSchedulerStore(),
        registry=registry,
        timezone="Asia/Shanghai",
        enabled=True,
    )


def _session_title(messages: list[SessionMessage], fallback: str) -> str:
    for message in messages:
        if _is_internal_session_message(message):
            continue
        if message.role != "user":
            continue
        title = " ".join(message.content.strip().split())
        if title:
            return title[:36]
    return fallback


def _session_preview(messages: list[SessionMessage]) -> str:
    for message in reversed(messages):
        if _is_internal_session_message(message):
            continue
        if message.role == "user":
            continue
        preview = " ".join(_display_answer(message.content).strip().split())
        if preview:
            return preview[:96]
    for message in reversed(messages):
        if _is_internal_session_message(message):
            continue
        preview = " ".join(message.content.strip().split())
        if preview:
            return preview[:96]
    return ""


def _visible_session_messages(messages: list[SessionMessage]) -> list[SessionMessage]:
    return [
        message
        for message in messages
        if not _is_internal_session_message(message)
    ]


def _is_internal_session_message(message: SessionMessage) -> bool:
    return (message.metadata or {}).get("visibility") == "internal"


def _session_messages(messages: list[SessionMessage]) -> list[SessionChatMessage]:
    formatted = []
    for message in _visible_session_messages(messages):
        topic_update = _answer_topic_update(message.content) if message.role == "assistant" else {}
        content = (
            _display_answer_for_topic_update(message.content, topic_update)
            if message.role == "assistant"
            else message.content
        )
        formatted.append(
            SessionChatMessage(
                role=message.role,
                content=content,
                created_at=message.created_at.isoformat(),
                completed=message.metadata.get("completed"),
                query_key=_answer_query_key(message.content) if message.role == "assistant" else None,
                reference_data=_answer_reference_data(message.content) if message.role == "assistant" else [],
                topic_update=topic_update,
            )
        )
    return formatted


def _is_hidden_session(messages: list[SessionMessage]) -> bool:
    for message in messages:
        metadata = message.metadata or {}
        if metadata.get("visibility") == "hidden" or metadata.get("source") == "scheduler":
            return True
    return False


def _session_summary(path: Path, store: MarkdownSessionHistoryStore, messages: list[SessionMessage] | None = None) -> SessionSummary:
    messages = messages if messages is not None else store.list(path.stem)
    stat = path.stat()
    return SessionSummary(
        id=path.stem,
        title=_session_title(messages, path.stem),
        updated_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        message_count=len(_visible_session_messages(messages)),
        preview=_session_preview(messages),
    )


def create_app(
    chat_runtime: ChatRuntime | None = None,
    scheduler_service: SchedulerRuntime | None = None,
    auth_service: AuthRuntime | None = None,
    auth_required: bool = True,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.scheduler_service = scheduler_service or _create_scheduler_service(app.state.chat_runtime)
        app.state.scheduler_service.start()
        _ensure_default_hotspot_refresh_job(app.state.scheduler_service)
        try:
            yield
        finally:
            app.state.scheduler_service.shutdown(wait=False)

    app = FastAPI(
        title="Topic Pulse Chat",
        description="Browser chat interface for Topic Pulse V2.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.chat_runtime = chat_runtime or ReactChatService()
    app.state.auth_service = auth_service or (AuthService() if auth_required else None)
    if app.state.auth_service is not None:
        app.state.auth_service.initialize()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def current_user(
        authorization: str | None = Header(default=None),
        x_guest_id: str | None = Header(default=None, alias="X-Guest-Id"),
    ) -> AuthUser:
        if not auth_required:
            return AuthUser(id="anonymous-user-1", email="anonymous@example.test", status="active")
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() == "bearer" and token:
            try:
                return app.state.auth_service.authenticate_token(token)
            except Exception as exc:
                raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
        if x_guest_id:
            try:
                return _guest_user_from_id(x_guest_id)
            except ValueError as exc:
                raise HTTPException(status_code=401, detail="Invalid guest id") from exc
        raise HTTPException(status_code=401, detail="Authentication required")

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    @app.post("/api/auth/register/request-code", response_model=AuthMessageResponse)
    def request_registration_code(request: AuthRequestCodeRequest) -> AuthMessageResponse:
        if app.state.auth_service is None:
            raise HTTPException(status_code=404, detail="Auth is disabled")
        try:
            app.state.auth_service.request_registration_code(request.email)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return AuthMessageResponse()

    @app.post("/api/auth/register/verify", response_model=AuthTokenResponse)
    def verify_registration(request: AuthRegisterVerifyRequest) -> AuthTokenResponse:
        if app.state.auth_service is None:
            raise HTTPException(status_code=404, detail="Auth is disabled")
        try:
            user, token = app.state.auth_service.register_with_code(
                email=request.email,
                code=request.code,
                password=request.password,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _auth_token_response(user, token)

    @app.post("/api/auth/login", response_model=AuthTokenResponse)
    def login(request: AuthLoginRequest) -> AuthTokenResponse:
        if app.state.auth_service is None:
            raise HTTPException(status_code=404, detail="Auth is disabled")
        try:
            user, token = app.state.auth_service.login(email=request.email, password=request.password)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail="Invalid email or password") from exc
        return _auth_token_response(user, token)

    @app.get("/api/auth/me", response_model=AuthUserResponse)
    def me(user: AuthUser = Depends(current_user)) -> AuthUserResponse:
        return _auth_user_response(user)

    @app.post("/api/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest, user: AuthUser = Depends(current_user)) -> ChatResponse:
        _ensure_guest_can_create_session(user, request.session_id)
        try:
            result = await run_in_threadpool(
                app.state.chat_runtime.chat,
                user_id=user.id,
                message=request.message,
                session_id=request.session_id,
                metadata={
                    "source": "web",
                    "history_length": len(request.history),
                },
            )
        except Exception as exc:
            logger.exception("Chat runtime failed.")
            raise HTTPException(
                status_code=503,
                detail="模型服务暂时不可用，请确认 API_KEY、网络连接和模型服务配置后重试。",
            ) from exc
        topic_update = _answer_topic_update(result.answer)
        return ChatResponse(
            answer=_display_answer_for_topic_update(result.answer, topic_update),
            session_id=result.session_id or "",
            user_id=user.id,
            completed=result.completed,
            query_key=_answer_query_key(result.answer),
            reference_data=_answer_reference_data(result.answer),
            topic_update=topic_update,
            steps=react_result_steps_to_dict(result),
        )

    @app.post("/api/chat/stream")
    async def stream_chat(request: ChatRequest, user: AuthUser = Depends(current_user)) -> StreamingResponse:
        _ensure_guest_can_create_session(user, request.session_id)

        async def event_generator():
            yield _stream_event("status", text="正在分析问题")
            result = None
            streamed_answer = ""
            raw_step_content = ""
            try:
                metadata = {
                    "source": "web_stream",
                    "history_length": len(request.history),
                }
                if hasattr(app.state.chat_runtime, "chat_stream"):
                    iterator = app.state.chat_runtime.chat_stream(
                        user_id=user.id,
                        message=request.message,
                        session_id=request.session_id,
                        metadata=metadata,
                    )
                    while True:
                        event = await run_in_threadpool(_next_stream_event, iterator)
                        if event is _STREAM_END:
                            break
                        if event.type == "status":
                            stage = event.data.get("stage")
                            if stage == "session_ready":
                                yield _stream_event("session", session_id=event.session_id or "")
                                continue
                            if stage == "llm_start":
                                raw_step_content = ""
                                yield _stream_event("status", text="正在分析问题")
                            continue
                        if event.type == "llm_delta":
                            raw_step_content += event.content or ""
                            visible_answer = _partial_display_answer(raw_step_content)
                            if visible_answer.startswith(streamed_answer):
                                delta = visible_answer[len(streamed_answer):]
                                if delta:
                                    streamed_answer = visible_answer
                                    yield _stream_event("delta", content=delta)
                            continue
                        if event.type == "tool_start":
                            tool_name = _tool_display_name(event.data.get("name"))
                            hint = _tool_argument_hint(event.data.get("arguments"))
                            reason = _public_reasoning_text(event.data.get("thought"))
                            yield _stream_event("status", text=f"正在{tool_name}")
                            yield _stream_event(
                                "agent_step",
                                step_index=event.step_index,
                                status="running",
                                title=f"正在{tool_name}",
                                detail=reason or (f"围绕「{hint}」获取支撑信息" if hint else "为回答补充必要信息"),
                                tool_name=event.data.get("name"),
                            )
                            continue
                        if event.type == "tool_end":
                            tool_name = _tool_display_name(event.data.get("name"))
                            success = bool(event.data.get("success"))
                            yield _stream_event("status", text="正在整合工具结果")
                            yield _stream_event(
                                "agent_step",
                                step_index=event.step_index,
                                status="done" if success else "error",
                                title=f"{tool_name}{'完成' if success else '失败'}",
                                detail="已拿到可用于生成回答的资料，正在归纳整理。" if success else str(event.data.get("error") or "工具执行失败"),
                                tool_name=event.data.get("name"),
                            )
                            continue
                        if event.type == "step_end":
                            reason = _public_reasoning_text(event.data.get("thought"))
                            if reason:
                                yield _stream_event(
                                    "agent_step",
                                    step_index=event.step_index,
                                    status="done" if event.data.get("completed") else "thinking",
                                    title="完成一轮判断" if event.data.get("completed") else "继续推理下一步",
                                    detail=reason,
                                )
                            continue
                        if event.type == "result":
                            result = event.result
                            break
                        if event.type == "error":
                            yield _stream_event("error", message=event.content or "请求失败")
                            return
                else:
                    result = await run_in_threadpool(
                        app.state.chat_runtime.chat,
                        user_id=user.id,
                        message=request.message,
                        session_id=request.session_id,
                        metadata=metadata,
                    )
            except Exception:
                logger.exception("Streaming chat runtime failed.")
                yield _stream_event(
                    "error",
                    message="模型服务暂时不可用，请确认 API_KEY、网络连接和模型服务配置后重试。",
                )
                return
            if result is None:
                yield _stream_event("error", message="请求失败：没有返回有效结果")
                return

            query_key = _answer_query_key(result.answer)
            reference_data = _answer_reference_data(result.answer)
            topic_update = _answer_topic_update(result.answer)
            answer = _display_answer_for_topic_update(result.answer, topic_update)
            steps = react_result_steps_to_dict(result)

            if query_key or reference_data:
                yield _stream_event(
                    "references",
                    query_key=query_key,
                    reference_data=reference_data,
                )
            if topic_update:
                yield _stream_event("topic_update", topic_update=topic_update)

            if not streamed_answer:
                yield _stream_event("status", text="正在生成回答")
            if answer:
                remaining_answer = answer[len(streamed_answer):] if answer.startswith(streamed_answer) else answer
                for chunk in _text_chunks(remaining_answer):
                    yield _stream_event("delta", content=chunk)
                    await asyncio.sleep(0.01)
            else:
                yield _stream_event("delta", content="已完成，但后端没有返回具体回答。")

            yield _stream_event(
                "done",
                session_id=result.session_id or "",
                user_id=user.id,
                completed=result.completed,
                query_key=query_key,
                reference_data=reference_data,
                topic_update=topic_update,
                steps=steps,
            )

        return StreamingResponse(
            event_generator(),
            media_type="application/x-ndjson",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/topics", response_model=TopicListResponse)
    def list_topics(user: AuthUser = Depends(current_user)) -> TopicListResponse:
        store = _topic_store()
        topics = [
            _topic_summary_from_record(record)
            for record in store.list_topics(user_id=user.id)
            if Path(record.markdown_path).exists()
        ]
        return TopicListResponse(topics=topics)

    @app.get("/api/topics/{topic_id}", response_model=TopicDetailResponse)
    def get_topic(topic_id: str, user: AuthUser = Depends(current_user)) -> TopicDetailResponse:
        try:
            record = _topic_store().get_topic(user_id=user.id, topic_id=topic_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="Topic not found") from exc
        path = Path(record.markdown_path)
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="Topic not found")
        summary = _topic_summary_from_record(record)
        return TopicDetailResponse(**_model_data(summary), content=path.read_text(encoding="utf-8"))

    @app.get("/api/hotspots/today", response_model=HotspotTodayResponse)
    def get_today_hotspots(
        limit: int = 10,
        user: AuthUser = Depends(current_user),
    ) -> HotspotTodayResponse:
        today = datetime.now().astimezone().date()
        safe_limit = max(1, min(int(limit or 10), 50))
        rows = _hotspot_store().list_daily_ranking(today, limit=safe_limit)
        updated_at = ""
        if rows:
            updated_at = max(str(row.get("updated_at") or "") for row in rows)
        return HotspotTodayResponse(
            date=today.isoformat(),
            updated_at=updated_at,
            items=[
                HotspotRankingItemResponse(
                    topic_id=str(row.get("topic_id") or ""),
                    rank=int(row.get("rank") or 0),
                    score=float(row.get("score") or 0.0),
                    title=str(row.get("canonical_title") or ""),
                    summary=str(row.get("summary") or ""),
                    why_hot=str(row.get("why_hot") or ""),
                    category=str(row.get("category") or ""),
                    trend=str(row.get("trend") or ""),
                    first_seen_at=str(row.get("first_seen_at") or ""),
                    last_seen_at=str(row.get("last_seen_at") or ""),
                    source_count=int(row.get("source_count") or 0),
                    observation_count=int(row.get("observation_count") or 0),
                )
                for row in rows
            ],
        )

    @app.get("/api/scheduler/jobs", response_model=SchedulerJobListResponse)
    def list_scheduler_jobs(user: AuthUser = Depends(current_user)) -> SchedulerJobListResponse:
        return SchedulerJobListResponse(
            jobs=[
                _scheduler_job_response(job)
                for job in app.state.scheduler_service.list_jobs()
                if _job_belongs_to_user(job, user.id)
            ]
        )

    @app.post("/api/topics/{topic_id}/schedule", response_model=SchedulerJobResponse)
    def create_topic_refresh_schedule(
        topic_id: str,
        request: CreateTopicRefreshJobRequest,
        user: AuthUser = Depends(current_user),
    ) -> SchedulerJobResponse:
        _ensure_registered_user(user)
        try:
            record = _topic_store().get_topic(user_id=user.id, topic_id=topic_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="Topic not found") from exc
        path = Path(record.markdown_path)
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="Topic not found")
        existing = _find_topic_refresh_job(app.state.scheduler_service, topic_id, user_id=user.id)
        if existing is not None:
            return _scheduler_job_response(existing)

        topic = _topic_summary_from_record(record)
        trigger, trigger_args = _topic_refresh_trigger_args(request)
        now = datetime.now(timezone.utc)
        job = ScheduledJob(
            id=_topic_refresh_job_id(topic_id),
            task_name="refresh_topic",
            trigger=trigger,
            trigger_args=trigger_args,
            kwargs={
                "topic_name": topic.title,
                "user_id": user.id,
            },
            status="active" if request.enabled else "paused",
            name=f"Refresh topic: {topic.title}",
            description="Refresh one tracked topic from the web and update local Markdown memory.",
            metadata={
                "type": "topic_refresh",
                "topic_id": topic.id,
                "topic_title": topic.title,
                "topic_filename": topic.filename,
                "user_id": user.id,
            },
            created_at=now,
            updated_at=now,
        )
        return _scheduler_job_response(app.state.scheduler_service.add_job(job))

    @app.get("/api/topics/{topic_id}/schedule", response_model=SchedulerJobResponse | None)
    def get_topic_refresh_schedule(topic_id: str, user: AuthUser = Depends(current_user)):
        try:
            record = _topic_store().get_topic(user_id=user.id, topic_id=topic_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="Topic not found") from exc
        path = Path(record.markdown_path)
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="Topic not found")
        job = _find_topic_refresh_job(app.state.scheduler_service, topic_id, user_id=user.id)
        return _scheduler_job_response(job) if job is not None else None

    @app.post("/api/scheduler/jobs/{job_id}/pause", response_model=SchedulerJobResponse)
    def pause_scheduler_job(job_id: str, user: AuthUser = Depends(current_user)) -> SchedulerJobResponse:
        _ensure_registered_user(user)
        try:
            _get_user_scheduler_job(app.state.scheduler_service, job_id, user.id)
            job = app.state.scheduler_service.pause_job(job_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="Scheduled job not found") from exc
        return _scheduler_job_response(job)

    @app.post("/api/scheduler/jobs/{job_id}/resume", response_model=SchedulerJobResponse)
    def resume_scheduler_job(job_id: str, user: AuthUser = Depends(current_user)) -> SchedulerJobResponse:
        _ensure_registered_user(user)
        try:
            _get_user_scheduler_job(app.state.scheduler_service, job_id, user.id)
            job = app.state.scheduler_service.resume_job(job_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="Scheduled job not found") from exc
        return _scheduler_job_response(job)

    @app.post("/api/scheduler/jobs/{job_id}/run", response_model=JobRunResponse)
    async def run_scheduler_job(job_id: str, user: AuthUser = Depends(current_user)) -> JobRunResponse:
        _ensure_registered_user(user)
        try:
            _get_user_scheduler_job(app.state.scheduler_service, job_id, user.id)
            run = await app.state.scheduler_service.run_job_now(job_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="Scheduled job not found") from exc
        return _job_run_response(run)

    @app.get("/api/scheduler/jobs/{job_id}/runs", response_model=JobRunListResponse)
    def list_scheduler_job_runs(job_id: str, user: AuthUser = Depends(current_user)) -> JobRunListResponse:
        try:
            _get_user_scheduler_job(app.state.scheduler_service, job_id, user.id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="Scheduled job not found")
        return JobRunListResponse(
            runs=[_job_run_response(run) for run in app.state.scheduler_service.list_runs(job_id)]
        )

    @app.get("/api/sessions", response_model=SessionListResponse)
    def list_sessions(user: AuthUser = Depends(current_user)) -> SessionListResponse:
        index_store = _session_index_store()
        store = _session_store(index_store)
        sessions = []
        for record in index_store.list_sessions(user_id=user.id):
            path = Path(record.markdown_path)
            if not path.exists() or not path.is_file():
                continue
            messages = store.list(record.id, user_id=user.id)
            if _is_hidden_session(messages):
                continue
            sessions.append(_session_summary(path, store, messages))
        return SessionListResponse(sessions=sessions)

    @app.get("/api/sessions/{session_id}", response_model=SessionDetailResponse)
    def get_session(session_id: str, user: AuthUser = Depends(current_user)) -> SessionDetailResponse:
        index_store = _session_index_store()
        store = _session_store(index_store)
        try:
            record = index_store.require_session(user_id=user.id, session_id=session_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="Session not found") from exc
        path = Path(record.markdown_path)
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="Session not found")
        messages = store.list(session_id, user_id=user.id)
        if _is_hidden_session(messages):
            raise HTTPException(status_code=404, detail="Session not found")
        summary = _session_summary(path, store, messages)
        return SessionDetailResponse(
            **_model_data(summary),
            messages=_session_messages(messages),
        )

    if FRONTEND_DIST_DIR.exists():
        assets_dir = FRONTEND_DIST_DIR / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa_fallback(path: str) -> FileResponse:
            index_path = FRONTEND_DIST_DIR / "index.html"
            return FileResponse(index_path)

    return app


app = create_app()
