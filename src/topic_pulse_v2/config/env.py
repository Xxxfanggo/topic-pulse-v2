"""Small .env loader for local development."""

from __future__ import annotations

import os
from pathlib import Path


def load_env_file(path: str | Path | None = None, *, override: bool = False) -> Path | None:
    """Load KEY=VALUE pairs from a .env file into os.environ."""

    env_path = Path(path) if path else _default_env_path()
    if not env_path.exists() or not env_path.is_file():
        return None

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or (key in os.environ and not override):
            continue
        os.environ[key] = _clean_env_value(value.strip())
    return env_path


def _default_env_path() -> Path:
    explicit = os.getenv("TOPIC_PULSE_ENV_FILE")
    if explicit:
        return Path(explicit)
    return Path(__file__).resolve().parents[3] / ".env"


def _clean_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    return value
