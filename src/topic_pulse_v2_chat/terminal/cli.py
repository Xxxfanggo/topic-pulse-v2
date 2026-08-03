"""Command-line multi-turn chat loop backed by ReActAgent."""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import TextIO
from uuid import uuid4

from topic_pulse_v2_chat.web.react_service import ReactChatService


EXIT_COMMANDS = {"/exit", "/quit", "exit", "quit", "q", "退出"}


@dataclass(slots=True)
class TerminalChatApp:
    """Interactive terminal loop for chatting with the ReAct runtime."""

    chat_service: ReactChatService
    user_id: str
    input_func: Callable[[str], str] = input
    output: TextIO | None = None

    def run(self) -> int:
        session_id: str | None = None
        self._write("Topic Pulse Terminal Chat")
        self._write(f"user_id: {self.user_id}")
        self._write("输入 /exit、/quit 或 退出 可结束对话。")
        self._write("")

        while True:
            try:
                query = self.input_func("你> ").strip()
            except (EOFError, KeyboardInterrupt):
                self._write("\n已结束对话。")
                return 0

            if not query:
                continue
            if query.lower() in EXIT_COMMANDS:
                self._write("已结束对话。")
                return 0

            self._write("AI> 思考中...")
            try:
                result = self.chat_service.chat(
                    user_id=self.user_id,
                    message=query,
                    session_id=session_id,
                    metadata={"source": "terminal"},
                )
            except Exception as exc:  # pragma: no cover - keeps the interactive loop alive.
                self._write(f"AI> 调用失败：{exc}")
                continue

            session_id = result.session_id
            self._write(f"AI> {result.answer}")
            self._write(f"[session_id={session_id}, completed={result.completed}, steps={len(result.steps)}]")
            self._write("")

    def _write(self, message: str) -> None:
        print(message, file=self.output)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Topic Pulse terminal chat client.")
    parser.add_argument(
        "--user-id",
        default=os.getenv("TOPIC_PULSE_USER_ID"),
        help="User id for memory/session isolation. Defaults to TOPIC_PULSE_USER_ID or an anonymous id.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    user_id = args.user_id or f"terminal-{uuid4()}"
    app = TerminalChatApp(
        chat_service=ReactChatService(),
        user_id=user_id,
    )
    return app.run()
