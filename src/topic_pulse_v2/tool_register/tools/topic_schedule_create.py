"""Local tool for creating scheduled refresh jobs for tracked topics."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from topic_pulse_v2.config import database_path, topics_dir as default_topics_dir
from topic_pulse_v2.topics import (
    TopicRefreshScheduler,
    SQLiteTopicStore,
    create_persisted_topic_refresh_schedule,
    create_topic_refresh_schedule,
)

if TYPE_CHECKING:
    from topic_pulse_v2.tool_register.registry import ToolRegistry


TOPIC_SCHEDULE_CREATE_TOOL_NAME = "topic_schedule_create"
_active_scheduler: TopicRefreshScheduler | None = None


def set_active_topic_schedule_scheduler(scheduler: TopicRefreshScheduler | None) -> None:
    global _active_scheduler
    _active_scheduler = scheduler


def active_topic_schedule_scheduler() -> TopicRefreshScheduler | None:
    return _active_scheduler


def topic_schedule_create(
    topic_name: str,
    *,
    trigger: str = "interval",
    interval_minutes: int = 60,
    cron_hour: int | None = None,
    cron_minute: int | None = None,
    enabled: bool = True,
    user_id: str | None = None,
    db_path: str | None = None,
    root_dir: str | None = None,
) -> dict[str, Any]:
    """Create a persisted scheduler job for refreshing one tracked topic."""

    if not str(user_id or "").strip():
        raise ValueError("user_id is required for topic schedule creation.")

    scheduler = active_topic_schedule_scheduler()
    if scheduler is None:
        job, created = create_persisted_topic_refresh_schedule(
            user_id=str(user_id).strip(),
            topic_name=topic_name,
            trigger=trigger,
            interval_minutes=interval_minutes,
            cron_hour=cron_hour,
            cron_minute=cron_minute,
            enabled=enabled,
            db_path=db_path or database_path(),
            topics_dir=root_dir or default_topics_dir(),
        )
        active_immediately = False
    else:
        job, created = create_topic_refresh_schedule(
            scheduler=scheduler,
            topic_store=SQLiteTopicStore(
                db_path=db_path or database_path(),
                topics_dir=root_dir or default_topics_dir(),
            ),
            user_id=str(user_id).strip(),
            topic_name=topic_name,
            trigger=trigger,
            interval_minutes=interval_minutes,
            cron_hour=cron_hour,
            cron_minute=cron_minute,
            enabled=enabled,
        )
        active_immediately = job.status == "active"
    return {
        "created": created,
        "active_immediately": active_immediately,
        "note": _schedule_note(active_immediately),
        "job": _job_to_dict(job),
    }


def register_topic_schedule_create_tool(
    registry: ToolRegistry,
    *,
    replace: bool = False,
) -> None:
    """Register the topic schedule creation tool in a registry."""

    registry.register(
        TOPIC_SCHEDULE_CREATE_TOOL_NAME,
        topic_schedule_create,
        description=(
            "工具名：话题定时刷新任务创建。\n"
            "用途：为某个已经保存到本地 Markdown 记忆的关注话题创建定时刷新任务，"
            "等价于用户在话题详情页手动点击创建定时刷新。\n"
            "使用时机：用户明确要求对某个已关注话题设置自动刷新、定时跟踪、每天更新、"
            "每隔一段时间更新时调用。本工具只创建调度任务，实际刷新仍由 refresh_topic 执行。\n"
            "输入要求：topic_name 必须是当前用户已关注的话题名称；trigger 支持 interval 或 cron。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "topic_name": {
                    "type": "string",
                    "description": "需要创建定时刷新任务的已关注话题名称。",
                },
                "trigger": {
                    "type": "string",
                    "enum": ["interval", "cron"],
                    "description": "调度触发类型。interval 表示每隔一段时间，cron 表示每天固定时间。",
                    "default": "interval",
                },
                "interval_minutes": {
                    "type": "integer",
                    "description": "interval 模式下的刷新间隔分钟数。",
                    "default": 60,
                },
                "cron_hour": {
                    "type": "integer",
                    "description": "cron 模式下每天触发的小时，0-23。",
                },
                "cron_minute": {
                    "type": "integer",
                    "description": "cron 模式下每天触发的分钟，0-59。",
                },
                "enabled": {
                    "type": "boolean",
                    "description": "创建后是否启用任务。",
                    "default": True,
                },
            },
            "required": ["topic_name"],
        },
        tags={"local", "scheduler", "topic", "news", "定时任务", "话题追踪"},
        metadata={
            "provider": "local",
            "tool_display_name": "话题定时任务创建",
            "selection_hint": "用户要为已关注话题设置定时刷新或自动跟踪时调用。",
        },
        replace=replace,
    )


register_tool = register_topic_schedule_create_tool


def _job_to_dict(job) -> dict[str, Any]:
    return {
        "id": job.id,
        "task_name": job.task_name,
        "trigger": job.trigger,
        "trigger_args": job.trigger_args,
        "args": job.args,
        "kwargs": job.kwargs,
        "status": job.status,
        "name": job.name,
        "description": job.description,
        "metadata": job.metadata,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


def _schedule_note(active_immediately: bool) -> str:
    if active_immediately:
        return "任务已创建并注册到当前运行中的调度器，效果等同于在页面上手动创建定时刷新。"
    return "任务已持久化；如果当前 Web 进程未通过本工具拿到 scheduler_service，重启服务后会自动加载。"
