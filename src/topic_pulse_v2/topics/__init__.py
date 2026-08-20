"""User-scoped topic persistence."""

from .schedule import (
    TopicRefreshScheduler,
    build_topic_refresh_job,
    create_persisted_topic_refresh_schedule,
    create_topic_refresh_schedule,
    find_topic_refresh_job,
    resolve_scheduled_topic,
    topic_refresh_job_id,
    topic_refresh_trigger_args,
)
from .hotspot import (
    HotspotAnalysisTopic,
    HotspotRankingItem,
    HotspotTopicContext,
    NormalizedHotNewsItem,
    SQLiteHotspotStore,
)
from .store import SQLiteTopicStore, TopicRecord

__all__ = [
    "SQLiteTopicStore",
    "TopicRecord",
    "TopicRefreshScheduler",
    "HotspotAnalysisTopic",
    "HotspotRankingItem",
    "HotspotTopicContext",
    "NormalizedHotNewsItem",
    "SQLiteHotspotStore",
    "build_topic_refresh_job",
    "create_persisted_topic_refresh_schedule",
    "create_topic_refresh_schedule",
    "find_topic_refresh_job",
    "resolve_scheduled_topic",
    "topic_refresh_job_id",
    "topic_refresh_trigger_args",
]
