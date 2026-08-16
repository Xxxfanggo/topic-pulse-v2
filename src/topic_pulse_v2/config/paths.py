"""Shared filesystem paths for runtime data."""

from __future__ import annotations

import os
from pathlib import Path

from .env import load_env_file


load_env_file()

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def app_data_dir() -> Path:
    """Return the root directory for persisted runtime data."""

    configured = os.getenv("TOPIC_PULSE_DATA_DIR")
    return Path(configured).expanduser() if configured else PROJECT_ROOT / "data"


def database_path() -> Path:
    return app_data_dir() / "topic_pulse.sqlite3"


def topics_dir() -> Path:
    return app_data_dir() / "topics"


def session_data_dir() -> Path:
    return app_data_dir() / "session"


def logs_dir() -> Path:
    return app_data_dir() / "logs"


def react_trace_log_path() -> Path:
    return logs_dir() / "react_trace.jsonl"


def hotspot_trace_log_path() -> Path:
    return logs_dir() / "hotspot_agent_trace.jsonl"
