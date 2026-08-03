"""FastAPI application for the browser chat UI."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from topic_pulse_v2_chat.web.schemas import ChatRequest, ChatResponse, HealthResponse
from topic_pulse_v2_chat.web.react_service import ReactChatService, react_result_steps_to_dict

FRONTEND_DIST_DIR = Path(__file__).resolve().parent / "frontend" / "dist"


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
        return ChatResponse(
            answer=result.answer,
            session_id=result.session_id or "",
            user_id=request.user_id,
            completed=result.completed,
            steps=react_result_steps_to_dict(result),
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
