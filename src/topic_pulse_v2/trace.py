"""Simple JSONL trace logging."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


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
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "type": event_type,
        "session_id": session_id,
        "step_index": step_index,
        "data": data or {},
    }
    line = json.dumps(event, ensure_ascii=False, default=str) + "\n"
    existing_content = path.read_text(encoding="utf-8") if path.exists() else ""
    path.write_text(line + existing_content, encoding="utf-8")
