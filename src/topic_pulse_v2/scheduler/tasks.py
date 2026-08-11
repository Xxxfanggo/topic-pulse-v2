"""Built-in scheduler task placeholders."""

from __future__ import annotations

from .registry import ScheduledTaskRegistry


def refresh_topic(topic_name: str) -> dict[str, str]:
    """Placeholder for a future topic refresh task."""

    return {
        "status": "skipped",
        "topic_name": topic_name,
        "reason": "refresh_topic is not implemented yet",
    }


def cleanup_trace_logs() -> dict[str, str]:
    """Placeholder for a future trace cleanup task."""

    return {
        "status": "skipped",
        "reason": "cleanup_trace_logs is not implemented yet",
    }


def register_builtin_tasks(registry: ScheduledTaskRegistry) -> None:
    registry.register(
        "refresh_topic",
        refresh_topic,
        description="Refresh one tracked topic.",
        replace=True,
    )
    registry.register(
        "cleanup_trace_logs",
        cleanup_trace_logs,
        description="Clean scheduler or agent trace logs.",
        replace=True,
    )
