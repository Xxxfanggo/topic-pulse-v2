"""Simple JSONL trace logging."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def resolve_trace_log_path(log_path: str | None, *, timestamp: datetime | None = None) -> Path | None:
    """Resolve a configured trace path to the date-partitioned JSONL file."""

    if not log_path:
        return None
    base_path = Path(log_path)
    current = timestamp or datetime.now()
    partition_name = f"{current.date().isoformat()}.jsonl"
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
    """Append one trace event to a JSONL log file."""

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
    with path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(line)
