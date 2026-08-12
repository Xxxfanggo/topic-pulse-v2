"""Simple JSON-lines trace logging."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def resolve_trace_log_path(log_path: str | None, *, timestamp: datetime | None = None) -> Path | None:
    """Resolve a configured trace path to the date-partitioned log file."""

    if not log_path:
        return None
    base_path = Path(log_path)
    current = timestamp or datetime.now()
    partition_name = f"{current.date().isoformat()}.log"
    if base_path.suffix:
        partition_dir = base_path.parent / base_path.stem
    else:
        partition_dir = base_path
    return partition_dir / partition_name


def log_event(
    log_path: str | None,
    event_type: str,
    *,
    session_id: str | None = None,
    step_index: int | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    """Write one trace event to the daily log file, newest first."""

    if not log_path:
        return
    timestamp = datetime.now()
    path = resolve_trace_log_path(log_path, timestamp=timestamp)
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "timestamp": timestamp.isoformat(timespec="seconds"),
        "type": event_type,
        "session_id": session_id,
        "step_index": step_index,
        "data": data or {},
    }
    line = json.dumps(event, ensure_ascii=False, default=str) + "\n"
    existing_content = path.read_text(encoding="utf-8") if path.exists() else ""
    path.write_text(line + existing_content, encoding="utf-8", newline="\n")


def log_markdown(
    log_path: str | None,
    title: str,
    content: str,
    *,
    session_id: str | None = None,
    step_index: int | None = None,
) -> None:
    """Write one Markdown trace block to the daily log file, newest first."""

    if not log_path:
        return
    timestamp = datetime.now()
    path = resolve_trace_log_path(log_path, timestamp=timestamp)
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = [
        f"timestamp: {timestamp.isoformat(timespec='seconds')}",
        f"type: {title}",
        f"session_id: {session_id or ''}",
        f"step_index: {step_index if step_index is not None else ''}",
    ]
    block = (
        f"<!-- trace_markdown\n"
        f"{chr(10).join(metadata)}\n"
        f"-->\n\n"
        f"## {title}\n\n"
        f"{content.rstrip()}\n\n"
        f"<!-- /trace_markdown -->\n\n"
    )
    existing_content = path.read_text(encoding="utf-8") if path.exists() else ""
    path.write_text(block + existing_content, encoding="utf-8", newline="\n")
