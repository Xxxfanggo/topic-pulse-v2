"""Persistence and topic models for platform-level hotspots."""

from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from topic_pulse_v2.db import Database, SQLiteDatabase


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _datetime_to_text(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _datetime_from_text(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _load_json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    return json.loads(value)


def _normalize_title(value: str) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[#【】\[\]（）()《》<>:：,，.!！?？;；\"'“”‘’、|/\\]", " ", text)
    text = re.sub(
        r"\b(热搜|热点|最新|今日|今天|突发|爆料|新闻|登上|冲上|回应|官方|通报)\b",
        " ",
        text,
    )
    return re.sub(r"\s+", " ", text).strip()


def _compact_text(value: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)]}..."


@dataclass(slots=True)
class HotspotTopicContext:
    id: str
    canonical_title: str
    normalized_title: str
    summary: str = ""
    why_hot: str = ""
    category: str = ""
    trend: str = ""
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    source_count: int = 0
    observation_count: int = 0


@dataclass(slots=True)
class HotspotAnalysisTopic:
    canonical_title: str
    matched_item_ids: list[str] = field(default_factory=list)
    matched_existing_topic_id: str = ""
    summary: str = ""
    why_hot: str = ""
    category: str = ""
    trend: str = "steady"
    confidence: float = 0.0


@dataclass(slots=True)
class HotspotRankingItem:
    topic_id: str
    rank: int
    score: float
    canonical_title: str
    summary: str = ""
    why_hot: str = ""
    source_count: int = 0
    observation_count: int = 0


@dataclass(slots=True)
class NormalizedHotNewsItem:
    id: str
    title: str
    normalized_title: str
    summary: str = ""
    url: str = ""
    source: str = ""
    rank: int | None = None
    heat: float | None = None
    published_at: datetime | None = None
    captured_at: datetime | None = None
    category: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


class SQLiteHotspotStore:
    """SQLite persistence for hotspot snapshots, topics, observations and rankings."""

    def __init__(
        self,
        database: Database | None = None,
        *,
        path: str | Path | None = None,
    ) -> None:
        self._database = database or SQLiteDatabase(path)

    def initialize(self) -> None:
        self._database.initialize()
        self._database.execute_script(
            """
            CREATE TABLE IF NOT EXISTS hot_news_snapshots (
                id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                snapshot_date TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                title TEXT NOT NULL,
                normalized_title TEXT NOT NULL,
                summary TEXT NOT NULL,
                url TEXT NOT NULL,
                source TEXT NOT NULL,
                rank INTEGER,
                heat REAL,
                published_at TEXT NOT NULL,
                category TEXT NOT NULL,
                raw TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS hotspot_topics (
                id TEXT PRIMARY KEY,
                topic_date TEXT NOT NULL,
                canonical_title TEXT NOT NULL,
                normalized_title TEXT NOT NULL,
                summary TEXT NOT NULL,
                why_hot TEXT NOT NULL,
                category TEXT NOT NULL,
                trend TEXT NOT NULL,
                confidence REAL NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                source_count INTEGER NOT NULL,
                observation_count INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS hotspot_observations (
                id TEXT PRIMARY KEY,
                topic_id TEXT NOT NULL,
                topic_date TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                title TEXT NOT NULL,
                normalized_title TEXT NOT NULL,
                summary TEXT NOT NULL,
                url TEXT NOT NULL,
                source TEXT NOT NULL,
                rank INTEGER,
                heat REAL,
                published_at TEXT NOT NULL,
                category TEXT NOT NULL,
                raw TEXT NOT NULL,
                FOREIGN KEY(topic_id) REFERENCES hotspot_topics(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS daily_hotspot_rankings (
                ranking_date TEXT NOT NULL,
                topic_id TEXT NOT NULL,
                rank INTEGER NOT NULL,
                score REAL NOT NULL,
                summary TEXT NOT NULL,
                why_hot TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(ranking_date, topic_id),
                FOREIGN KEY(topic_id) REFERENCES hotspot_topics(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_hot_news_snapshots_date
                ON hot_news_snapshots(snapshot_date, captured_at DESC);
            CREATE INDEX IF NOT EXISTS idx_hotspot_topics_date_score
                ON hotspot_topics(topic_date, last_seen_at DESC);
            CREATE INDEX IF NOT EXISTS idx_hotspot_observations_topic
                ON hotspot_observations(topic_id, captured_at DESC);
            CREATE INDEX IF NOT EXISTS idx_daily_hotspot_rankings_date
                ON daily_hotspot_rankings(ranking_date, rank);
            """
        )

    def save_snapshots(
        self,
        *,
        provider: str,
        snapshot_date: date,
        captured_at: datetime,
        items: list[NormalizedHotNewsItem],
    ) -> None:
        self.initialize()
        with self._database.transaction():
            for item in items:
                self._database.execute(
                    """
                    INSERT INTO hot_news_snapshots (
                        id, provider, snapshot_date, captured_at, title,
                        normalized_title, summary, url, source, rank, heat,
                        published_at, category, raw
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"snap_{secrets.token_urlsafe(16)}",
                        provider,
                        snapshot_date.isoformat(),
                        _datetime_to_text(captured_at),
                        item.title,
                        item.normalized_title,
                        item.summary,
                        item.url,
                        item.source,
                        item.rank,
                        item.heat,
                        _datetime_to_text(item.published_at),
                        item.category,
                        _dump_json(item.raw),
                    ),
                )

    def load_today_context(self, snapshot_date: date) -> list[HotspotTopicContext]:
        self.initialize()
        rows = self._database.fetch_all(
            """
            SELECT * FROM hotspot_topics
            WHERE topic_date = ?
            ORDER BY last_seen_at DESC
            """,
            (snapshot_date.isoformat(),),
        )
        return [
            HotspotTopicContext(
                id=row["id"],
                canonical_title=row["canonical_title"],
                normalized_title=row["normalized_title"],
                summary=row["summary"],
                why_hot=row["why_hot"],
                category=row["category"],
                trend=row["trend"],
                first_seen_at=_datetime_from_text(row["first_seen_at"]),
                last_seen_at=_datetime_from_text(row["last_seen_at"]),
                source_count=int(row["source_count"] or 0),
                observation_count=int(row["observation_count"] or 0),
            )
            for row in rows
        ]

    def persist_analysis(
        self,
        *,
        snapshot_date: date,
        captured_at: datetime,
        items: list[NormalizedHotNewsItem],
        analysis_topics: list[HotspotAnalysisTopic],
    ) -> list[str]:
        self.initialize()
        item_by_id = {item.id: item for item in items}
        topic_ids: list[str] = []
        with self._database.transaction():
            for topic in analysis_topics:
                matched_items = [item_by_id[item_id] for item_id in topic.matched_item_ids if item_id in item_by_id]
                if not matched_items:
                    continue
                topic_id = topic.matched_existing_topic_id.strip() or f"hot_{secrets.token_urlsafe(14)}"
                topic_ids.append(topic_id)
                previous = self._database.fetch_one(
                    "SELECT * FROM hotspot_topics WHERE id = ?",
                    (topic_id,),
                )
                first_seen = (
                    _datetime_from_text(previous["first_seen_at"])
                    if previous is not None
                    else captured_at
                ) or captured_at
                observations = self._existing_observations(topic_id) + matched_items
                sources = {item.source for item in observations if item.source}
                canonical_title = topic.canonical_title.strip() or matched_items[0].title
                normalized = _normalize_title(canonical_title) or matched_items[0].normalized_title
                self._database.execute(
                    """
                    INSERT INTO hotspot_topics (
                        id, topic_date, canonical_title, normalized_title,
                        summary, why_hot, category, trend, confidence,
                        first_seen_at, last_seen_at, source_count,
                        observation_count, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        canonical_title = excluded.canonical_title,
                        normalized_title = excluded.normalized_title,
                        summary = excluded.summary,
                        why_hot = excluded.why_hot,
                        category = excluded.category,
                        trend = excluded.trend,
                        confidence = excluded.confidence,
                        last_seen_at = excluded.last_seen_at,
                        source_count = excluded.source_count,
                        observation_count = excluded.observation_count,
                        updated_at = excluded.updated_at
                    """,
                    (
                        topic_id,
                        snapshot_date.isoformat(),
                        canonical_title,
                        normalized,
                        _compact_text(topic.summary, 2000),
                        _compact_text(topic.why_hot, 1000),
                        topic.category.strip(),
                        topic.trend.strip() or "steady",
                        float(topic.confidence or 0.0),
                        _datetime_to_text(first_seen),
                        _datetime_to_text(captured_at),
                        len(sources),
                        len(observations),
                        _datetime_to_text(utc_now()),
                    ),
                )
                for item in matched_items:
                    self._database.execute(
                        """
                        INSERT INTO hotspot_observations (
                            id, topic_id, topic_date, captured_at, title,
                            normalized_title, summary, url, source, rank, heat,
                            published_at, category, raw
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            f"obs_{secrets.token_urlsafe(16)}",
                            topic_id,
                            snapshot_date.isoformat(),
                            _datetime_to_text(captured_at),
                            item.title,
                            item.normalized_title,
                            item.summary,
                            item.url,
                            item.source,
                            item.rank,
                            item.heat,
                            _datetime_to_text(item.published_at),
                            item.category,
                            _dump_json(item.raw),
                        ),
                    )
        return topic_ids

    def recalculate_daily_ranking(self, snapshot_date: date, *, limit: int = 50) -> list[HotspotRankingItem]:
        self.initialize()
        topics = self._database.fetch_all(
            "SELECT * FROM hotspot_topics WHERE topic_date = ?",
            (snapshot_date.isoformat(),),
        )
        scored: list[tuple[float, dict[str, Any]]] = []
        for topic in topics:
            observations = self._database.fetch_all(
                """
                SELECT * FROM hotspot_observations
                WHERE topic_id = ?
                ORDER BY captured_at DESC
                """,
                (topic["id"],),
            )
            score = self._score_topic(topic, observations)
            scored.append((score, topic))
        scored.sort(key=lambda item: item[0], reverse=True)

        now = _datetime_to_text(utc_now())
        ranking: list[HotspotRankingItem] = []
        with self._database.transaction():
            self._database.execute(
                "DELETE FROM daily_hotspot_rankings WHERE ranking_date = ?",
                (snapshot_date.isoformat(),),
            )
            for index, (score, topic) in enumerate(scored[:limit], start=1):
                self._database.execute(
                    """
                    INSERT INTO daily_hotspot_rankings (
                        ranking_date, topic_id, rank, score, summary,
                        why_hot, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_date.isoformat(),
                        topic["id"],
                        index,
                        round(score, 3),
                        topic["summary"],
                        topic["why_hot"],
                        now,
                    ),
                )
                ranking.append(
                    HotspotRankingItem(
                        topic_id=topic["id"],
                        rank=index,
                        score=round(score, 3),
                        canonical_title=topic["canonical_title"],
                        summary=topic["summary"],
                        why_hot=topic["why_hot"],
                        source_count=int(topic["source_count"] or 0),
                        observation_count=int(topic["observation_count"] or 0),
                    )
                )
        return ranking

    def list_daily_ranking(self, ranking_date: date, *, limit: int = 10) -> list[dict[str, Any]]:
        self.initialize()
        rows = self._database.fetch_all(
            """
            SELECT
                r.ranking_date,
                r.rank,
                r.score,
                r.summary,
                r.why_hot,
                r.updated_at,
                t.id AS topic_id,
                t.canonical_title,
                t.category,
                t.trend,
                t.first_seen_at,
                t.last_seen_at,
                t.source_count,
                t.observation_count
            FROM daily_hotspot_rankings r
            JOIN hotspot_topics t ON t.id = r.topic_id
            WHERE r.ranking_date = ?
            ORDER BY r.rank ASC
            LIMIT ?
            """,
            (ranking_date.isoformat(), limit),
        )
        return [dict(row) for row in rows]

    def close(self) -> None:
        self._database.close()

    def _existing_observations(self, topic_id: str) -> list[NormalizedHotNewsItem]:
        rows = self._database.fetch_all(
            "SELECT * FROM hotspot_observations WHERE topic_id = ?",
            (topic_id,),
        )
        return [
            NormalizedHotNewsItem(
                id=row["id"],
                title=row["title"],
                normalized_title=row["normalized_title"],
                summary=row["summary"],
                url=row["url"],
                source=row["source"],
                rank=row["rank"],
                heat=row["heat"],
                published_at=_datetime_from_text(row["published_at"]),
                captured_at=_datetime_from_text(row["captured_at"]),
                category=row["category"],
                raw=_load_json(row["raw"], {}),
            )
            for row in rows
        ]

    @staticmethod
    def _score_topic(topic: dict[str, Any], observations: list[dict[str, Any]]) -> float:
        if not observations:
            return 0.0
        ranks = [int(row["rank"]) for row in observations if row.get("rank")]
        heats = [float(row["heat"]) for row in observations if row.get("heat") is not None]
        sources = {row["source"] for row in observations if row.get("source")}
        hours = {
            (_datetime_from_text(row["captured_at"]) or utc_now()).strftime("%Y-%m-%dT%H")
            for row in observations
        }
        latest_rank = ranks[0] if ranks else 50
        current_rank_score = max(0.0, 100.0 - min(latest_rank, 50) * 2.0)
        persistence_score = min(len(hours) / 12.0, 1.0) * 100.0
        source_score = min(len(sources) / 5.0, 1.0) * 100.0
        heat_score = min((max(heats) if heats else 0.0) / 10000.0, 1.0) * 100.0
        trend = str(topic.get("trend") or "")
        trend_score = 100.0 if trend == "rising" else 65.0 if trend == "steady" else 35.0
        return (
            0.30 * current_rank_score
            + 0.25 * persistence_score
            + 0.20 * source_score
            + 0.15 * heat_score
            + 0.10 * trend_score
        )
