"""Built-in scheduler tasks."""

from __future__ import annotations

import json
import re
from typing import Protocol

from topic_pulse_v2.information_search import create_hot_news_provider
from topic_pulse_v2.process.hotspot_agent import HotspotAgent, HotspotRunRequest

from .registry import ScheduledTaskRegistry


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


def refresh_topic(
    topic_name: str,
    *,
    chat_runtime: ChatRuntime | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
) -> dict:
    """Refresh one tracked topic by reusing the existing chat runtime."""

    if not user_id:
        return {
            "status": "skipped",
            "topic_name": topic_name,
            "new_count": 0,
            "reason": "user_id is required for topic refresh",
        }

    if chat_runtime is None:
        return {
            "status": "skipped",
            "topic_name": topic_name,
            "new_count": 0,
            "reason": "chat_runtime is not configured",
        }

    message = (
        f"请更新一下「{topic_name}」这个已关注话题的最新动态，"
        "必须结合本地已有话题记忆和最新互联网信息，去重后写回本地 Markdown 话题记忆。"
    )
    result = chat_runtime.chat(
        user_id=user_id,
        message=message,
        session_id=session_id,
        metadata={
            "source": "scheduler",
            "task": "refresh_topic",
            "topic_name": topic_name,
        },
    )
    topic_update = _extract_topic_update(getattr(result, "answer", ""))
    new_count = int(topic_update.get("new_count") or 0)
    existing_count = int(topic_update.get("existing_count") or 0)
    resolved_topic_name = str(topic_update.get("topic_name") or topic_name).strip()

    return {
        "status": "completed" if getattr(result, "completed", False) else "incomplete",
        "topic_name": resolved_topic_name,
        "new_count": new_count,
        "existing_count": existing_count,
        "update_status": topic_update.get("status", ""),
        "session_id": getattr(result, "session_id", None),
        "summary": _extract_summary(getattr(result, "answer", "")),
    }


def cleanup_trace_logs() -> dict[str, str]:
    """Placeholder for a future trace cleanup task."""

    return {
        "status": "skipped",
        "reason": "cleanup_trace_logs is not implemented yet",
    }


def refresh_hotspots(
    *,
    hotspot_agent: HotspotAgent | None = None,
    provider: str = "weibo",
) -> dict:
    """Refresh and persist today's platform-level hot news ranking."""

    agent = hotspot_agent or HotspotAgent(provider=create_hot_news_provider(provider))
    result = agent.run(HotspotRunRequest(provider=provider))
    return {
        "status": result.status,
        "date": result.date,
        "captured_at": result.captured_at,
        "fetched_count": result.fetched_count,
        "normalized_count": result.normalized_count,
        "merged_topic_count": result.merged_topic_count,
        "ranking_count": result.ranking_count,
        "top_topics": result.top_topics,
        "errors": result.errors,
    }


def register_builtin_tasks(
    registry: ScheduledTaskRegistry,
    *,
    chat_runtime: ChatRuntime | None = None,
    hotspot_agent: HotspotAgent | None = None,
) -> None:
    registry.register(
        "refresh_topic",
        lambda topic_name, **kwargs: refresh_topic(
            topic_name,
            chat_runtime=chat_runtime,
            **kwargs,
        ),
        description="Refresh one tracked topic.",
        replace=True,
    )
    # registry.register(
    #     "cleanup_trace_logs",
    #     cleanup_trace_logs,
    #     description="Clean scheduler or agent trace logs.",
    #     replace=True,
    # )
    registry.register(
        "refresh_hotspots",
        lambda **kwargs: refresh_hotspots(
            hotspot_agent=hotspot_agent,
            **kwargs,
        ),
        description="Refresh today's platform-level hot news ranking.",
        replace=True,
    )


def _extract_topic_update(answer: str) -> dict:
    payload = _answer_payload(answer)
    if not isinstance(payload, dict):
        return {}
    topic_update = payload.get("topic_update")
    return topic_update if isinstance(topic_update, dict) else {}


def _extract_summary(answer: str) -> str:
    payload = _answer_payload(answer)
    if isinstance(payload, dict):
        summary = payload.get("summary")
        if isinstance(summary, str) and summary.strip():
            return _strip_think_blocks(summary).strip()
    return _strip_think_blocks(str(answer or "")).strip()[:500]


def _answer_payload(answer: str) -> dict | None:
    answer = _strip_think_blocks(str(answer or "")).strip()
    if not answer:
        return None
    try:
        payload = json.loads(answer)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    final_answer = payload.get("final_answer")
    if isinstance(final_answer, str):
        nested = _answer_payload(final_answer)
        if nested is not None:
            return nested
    summary = payload.get("summary")
    if isinstance(summary, str):
        nested_summary = _answer_payload(summary)
        if nested_summary is not None:
            return nested_summary
    return payload


def _strip_think_blocks(content: str) -> str:
    return re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE)
