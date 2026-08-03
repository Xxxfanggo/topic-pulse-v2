"""FastAPI application for the browser chat UI."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from topic_pulse_v2_chat.web.schemas import ChatRequest, ChatResponse, HealthResponse

FRONTEND_DIST_DIR = Path(__file__).resolve().parent / "frontend" / "dist"


def create_app() -> FastAPI:
    app = FastAPI(
        title="Topic Pulse Chat",
        description="Browser chat interface for Topic Pulse V2.",
        version="0.1.0",
    )
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
    def chat(request: ChatRequest) -> ChatResponse:
        session_id = request.session_id or str(uuid4())
        return ChatResponse(
            session_id=session_id,
            answer=(
                "前后端框架已就绪。当前是占位回复，后续会在这里接入 "
                "ReActAgent 与本地工具调用。"
            ),
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
