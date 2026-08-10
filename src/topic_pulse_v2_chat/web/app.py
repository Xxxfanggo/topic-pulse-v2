"""FastAPI application for the browser chat UI."""

from __future__ import annotations

import json
import logging
import re
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from topic_pulse_v2.session import MarkdownSessionHistoryStore, SessionMessage
from topic_pulse_v2_chat.web.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
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
TOPICS_DIR = Path(__file__).resolve().parents[3] / "data" / "topics"
SESSION_DATA_DIR = Path(__file__).resolve().parents[2] / "topic_pulse_v2" / "session" / "data"
logger = logging.getLogger(__name__)


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


_STREAM_END = object()


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


def _topic_summary(path: Path) -> TopicSummary:
    content = path.read_text(encoding="utf-8")
    stat = path.stat()
    return TopicSummary(
        id=path.stem,
        title=_topic_title(content, path.stem),
        filename=path.name,
        updated_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        size=stat.st_size,
        preview=_topic_preview(content),
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


def _stream_event(event_type: str, **payload) -> str:
    return json.dumps({"type": event_type, **payload}, ensure_ascii=False, default=str) + "\n"


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
        return nested or final_answer

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

    return {
        "topic_name": str(update.get("topic_name") or update.get("话题") or "").strip(),
        "operation": str(update.get("operation") or "").strip(),
        "status": str(update.get("status") or "").strip(),
        "new_count": int(update.get("new_count") or 0),
        "existing_count": int(update.get("existing_count") or 0),
        "new_items": normalize_items(update.get("new_items")),
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


def _session_store() -> MarkdownSessionHistoryStore:
    return MarkdownSessionHistoryStore(SESSION_DATA_DIR)


def _session_title(messages: list[SessionMessage], fallback: str) -> str:
    for message in messages:
        if message.role != "user":
            continue
        title = " ".join(message.content.strip().split())
        if title:
            return title[:36]
    return fallback


def _session_preview(messages: list[SessionMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            continue
        preview = " ".join(_display_answer(message.content).strip().split())
        if preview:
            return preview[:96]
    for message in reversed(messages):
        preview = " ".join(message.content.strip().split())
        if preview:
            return preview[:96]
    return ""


def _session_messages(messages: list[SessionMessage]) -> list[SessionChatMessage]:
    formatted = []
    for message in messages:
        content = _display_answer(message.content) if message.role == "assistant" else message.content
        formatted.append(
            SessionChatMessage(
                role=message.role,
                content=content,
                created_at=message.created_at.isoformat(),
                completed=message.metadata.get("completed"),
                query_key=_answer_query_key(message.content) if message.role == "assistant" else None,
                reference_data=_answer_reference_data(message.content) if message.role == "assistant" else [],
                topic_update=_answer_topic_update(message.content) if message.role == "assistant" else {},
            )
        )
    return formatted


def _session_summary(path: Path, store: MarkdownSessionHistoryStore) -> SessionSummary:
    messages = store.list(path.stem)
    stat = path.stat()
    return SessionSummary(
        id=path.stem,
        title=_session_title(messages, path.stem),
        updated_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        message_count=len(messages),
        preview=_session_preview(messages),
    )


def create_app(chat_runtime: ChatRuntime | None = None) -> FastAPI:
    app = FastAPI(
        title="Topic Pulse Chat",
        description="Browser chat interface for Topic Pulse V2.",
        version="0.1.0",
    )
    app.state.chat_runtime = chat_runtime or ReactChatService()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    @app.post("/api/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest) -> ChatResponse:
        try:
            result = await run_in_threadpool(
                app.state.chat_runtime.chat,
                user_id=request.user_id,
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
        return ChatResponse(
            answer=_display_answer(result.answer),
            session_id=result.session_id or "",
            user_id=request.user_id,
            completed=result.completed,
            query_key=_answer_query_key(result.answer),
            reference_data=_answer_reference_data(result.answer),
            topic_update=_answer_topic_update(result.answer),
            steps=react_result_steps_to_dict(result),
        )

    @app.post("/api/chat/stream")
    async def stream_chat(request: ChatRequest) -> StreamingResponse:
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
                        user_id=request.user_id,
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
                            yield _stream_event("status", text="正在检索和整理资料")
                            continue
                        if event.type == "tool_end":
                            yield _stream_event("status", text="正在整合工具结果")
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
                        user_id=request.user_id,
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

            answer = _display_answer(result.answer)
            query_key = _answer_query_key(result.answer)
            reference_data = _answer_reference_data(result.answer)
            topic_update = _answer_topic_update(result.answer)
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
                user_id=request.user_id,
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
    def list_topics() -> TopicListResponse:
        if not TOPICS_DIR.exists():
            return TopicListResponse()
        topics = [_topic_summary(path) for path in sorted(TOPICS_DIR.glob("*.md"), key=lambda item: item.stat().st_mtime, reverse=True)]
        return TopicListResponse(topics=topics)

    @app.get("/api/topics/{topic_id}", response_model=TopicDetailResponse)
    def get_topic(topic_id: str) -> TopicDetailResponse:
        path = _topic_path(topic_id)
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="Topic not found")
        summary = _topic_summary(path)
        return TopicDetailResponse(**_model_data(summary), content=path.read_text(encoding="utf-8"))

    @app.get("/api/sessions", response_model=SessionListResponse)
    def list_sessions() -> SessionListResponse:
        store = _session_store()
        if not SESSION_DATA_DIR.exists():
            return SessionListResponse()
        paths = [
            path
            for path in SESSION_DATA_DIR.glob("*.md")
            if path.is_file() and not path.name.startswith(".")
        ]
        sessions = [
            _session_summary(path, store)
            for path in sorted(paths, key=lambda item: item.stat().st_mtime, reverse=True)
        ]
        return SessionListResponse(sessions=sessions)

    @app.get("/api/sessions/{session_id}", response_model=SessionDetailResponse)
    def get_session(session_id: str) -> SessionDetailResponse:
        store = _session_store()
        path = store.path_for(session_id)
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="Session not found")
        summary = _session_summary(path, store)
        return SessionDetailResponse(
            **_model_data(summary),
            messages=_session_messages(store.list(session_id)),
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
