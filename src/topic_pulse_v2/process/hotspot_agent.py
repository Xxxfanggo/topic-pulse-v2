"""Fixed-pipeline agent for background hotspot data accumulation."""

from __future__ import annotations

import json
import re
import secrets
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from topic_pulse_v2.db import Database, SQLiteDatabase
from topic_pulse_v2.information_search.hot_news import EmptyHotNewsProvider, HotNewsItem, HotNewsProvider
from topic_pulse_v2.llm_call import LLMClient, Message


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
class HotspotRunRequest:
    run_date: date | None = None
    captured_at: datetime | None = None
    provider: str = "default"


@dataclass(slots=True)
class HotspotRunResult:
    status: str
    date: str
    captured_at: str
    fetched_count: int = 0
    normalized_count: int = 0
    merged_topic_count: int = 0
    ranking_count: int = 0
    top_topics: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class _NormalizedHotNewsItem:
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
        path: str | Path = "data/topic_pulse.sqlite3",
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
        items: list[_NormalizedHotNewsItem],
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
        items: list[_NormalizedHotNewsItem],
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

    def close(self) -> None:
        self._database.close()

    def _existing_observations(self, topic_id: str) -> list[_NormalizedHotNewsItem]:
        rows = self._database.fetch_all(
            "SELECT * FROM hotspot_observations WHERE topic_id = ?",
            (topic_id,),
        )
        return [
            _NormalizedHotNewsItem(
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


class HotspotAgent:
    """A deterministic pipeline with one optional LLM analysis step."""

    def __init__(
        self,
        *,
        provider: HotNewsProvider | None = None,
        store: SQLiteHotspotStore | None = None,
        llm_client: LLMClient | None = None,
        llm_provider: str | None = None,
        llm_model: str | None = None,
    ) -> None:
        self._provider = provider or EmptyHotNewsProvider()
        self._store = store or SQLiteHotspotStore()
        self._llm_client = llm_client
        self._llm_provider = llm_provider
        self._llm_model = llm_model

    def run(self, request: HotspotRunRequest | None = None) -> HotspotRunResult:
        request = request or HotspotRunRequest()
        captured_at = request.captured_at or utc_now()
        run_date = request.run_date or captured_at.astimezone().date()
        errors: list[str] = []

        raw_items = self._fetch()
        normalized_items = self._normalize_items(raw_items, captured_at=captured_at)
        if not normalized_items:
            return HotspotRunResult(
                status="skipped",
                date=run_date.isoformat(),
                captured_at=_datetime_to_text(captured_at),
                fetched_count=len(raw_items),
                normalized_count=0,
                errors=[],
            )

        self._store.save_snapshots(
            provider=request.provider,
            snapshot_date=run_date,
            captured_at=captured_at,
            items=normalized_items,
        )
        context = self._store.load_today_context(run_date)
        analysis = self._analyze(normalized_items, context, run_date=run_date, captured_at=captured_at)
        if not analysis:
            errors.append("analysis returned no usable topics; deterministic fallback was used")
            analysis = self._fallback_analysis(normalized_items, context)
        persisted_ids = self._store.persist_analysis(
            snapshot_date=run_date,
            captured_at=captured_at,
            items=normalized_items,
            analysis_topics=analysis,
        )
        ranking = self._store.recalculate_daily_ranking(run_date)
        return HotspotRunResult(
            status="completed",
            date=run_date.isoformat(),
            captured_at=_datetime_to_text(captured_at),
            fetched_count=len(raw_items),
            normalized_count=len(normalized_items),
            merged_topic_count=len(persisted_ids),
            ranking_count=len(ranking),
            top_topics=[asdict(item) for item in ranking[:10]],
            errors=errors,
        )

    def _fetch(self) -> list[HotNewsItem]:
        if hasattr(self._provider, "fetch_hot_news"):
            return list(self._provider.fetch_hot_news())
        return list(self._provider.fetch_hot_news())

    def _normalize_items(
        self,
        items: list[HotNewsItem],
        *,
        captured_at: datetime,
    ) -> list[_NormalizedHotNewsItem]:
        normalized: list[_NormalizedHotNewsItem] = []
        seen: set[tuple[str, str]] = set()
        for item in items:
            title = _compact_text(item.title, 300)
            normalized_title = _normalize_title(title)
            if not title or not normalized_title:
                continue
            key = (normalized_title, item.url or "")
            if key in seen:
                continue
            seen.add(key)
            normalized.append(
                _NormalizedHotNewsItem(
                    id=f"item_{len(normalized) + 1}",
                    title=title,
                    normalized_title=normalized_title,
                    summary=_compact_text(item.summary, 1000),
                    url=str(item.url or "").strip(),
                    source=str(item.source or "").strip(),
                    rank=item.rank,
                    heat=item.heat,
                    published_at=item.published_at,
                    captured_at=item.captured_at or captured_at,
                    category=str(item.category or "").strip(),
                    raw=dict(item.raw or {}),
                )
            )
        return normalized

    def _analyze(
        self,
        items: list[_NormalizedHotNewsItem],
        context: list[HotspotTopicContext],
        *,
        run_date: date,
        captured_at: datetime,
    ) -> list[HotspotAnalysisTopic]:
        if self._llm_client is None:
            return self._fallback_analysis(items, context)
        try:
            response = self._llm_client.call(
                [
                    Message(role="system", content=self._system_prompt()),
                    Message(
                        role="user",
                        content=json.dumps(
                            {
                                "date": run_date.isoformat(),
                                "captured_at": _datetime_to_text(captured_at),
                                "new_items": [asdict(item) for item in items],
                                "existing_topics": [asdict(topic) for topic in context],
                            },
                            ensure_ascii=False,
                            default=str,
                        ),
                    ),
                ],
                provider=self._llm_provider,
                model=self._llm_model,
                temperature=0.1,
                max_tokens=4000,
                metadata={"task": "hotspot_analysis"},
            )
            return self._parse_analysis(response.content, items, context)
        except Exception:
            return self._fallback_analysis(items, context)

    @staticmethod
    def _system_prompt() -> str:
        return (
            "你是后台热点沉淀 Agent 的语义分析步骤。请把 new_items 与 existing_topics 归并为今日热点主题。"
            "只能基于输入内容，不要编造事实。只返回 JSON，不要 Markdown。格式："
            "{\"merged_topics\":[{\"canonical_title\":\"统一标题\",\"matched_item_ids\":[\"item_1\"],"
            "\"matched_existing_topic_id\":\"可为空\",\"summary\":\"摘要\",\"why_hot\":\"持续高热原因\","
            "\"category\":\"分类\",\"trend\":\"rising|steady|falling\",\"confidence\":0.0}]}"
        )

    def _parse_analysis(
        self,
        content: str,
        items: list[_NormalizedHotNewsItem],
        context: list[HotspotTopicContext],
    ) -> list[HotspotAnalysisTopic]:
        payload = self._extract_json_object(content)
        if not isinstance(payload, dict):
            return []
        raw_topics = payload.get("merged_topics")
        if not isinstance(raw_topics, list):
            return []
        item_ids = {item.id for item in items}
        context_ids = {topic.id for topic in context}
        parsed: list[HotspotAnalysisTopic] = []
        used_items: set[str] = set()
        for raw_topic in raw_topics:
            if not isinstance(raw_topic, dict):
                continue
            matched_ids = [
                str(item_id)
                for item_id in raw_topic.get("matched_item_ids", [])
                if str(item_id) in item_ids
            ]
            if not matched_ids:
                continue
            matched_existing = str(raw_topic.get("matched_existing_topic_id") or "").strip()
            if matched_existing and matched_existing not in context_ids:
                matched_existing = ""
            parsed.append(
                HotspotAnalysisTopic(
                    canonical_title=_compact_text(raw_topic.get("canonical_title") or "", 300),
                    matched_item_ids=matched_ids,
                    matched_existing_topic_id=matched_existing,
                    summary=_compact_text(raw_topic.get("summary") or "", 2000),
                    why_hot=_compact_text(raw_topic.get("why_hot") or "", 1000),
                    category=_compact_text(raw_topic.get("category") or "", 80),
                    trend=self._normalize_trend(raw_topic.get("trend")),
                    confidence=self._normalize_confidence(raw_topic.get("confidence")),
                )
            )
            used_items.update(matched_ids)
        remaining = [item for item in items if item.id not in used_items]
        parsed.extend(self._fallback_analysis(remaining, context))
        return parsed

    def _fallback_analysis(
        self,
        items: list[_NormalizedHotNewsItem],
        context: list[HotspotTopicContext],
    ) -> list[HotspotAnalysisTopic]:
        groups: list[tuple[list[_NormalizedHotNewsItem], str]] = []
        for item in items:
            matched_index = None
            for index, (_, normalized_title) in enumerate(groups):
                if self._similar(item.normalized_title, normalized_title):
                    matched_index = index
                    break
            if matched_index is None:
                groups.append(([item], item.normalized_title))
            else:
                groups[matched_index][0].append(item)

        topics: list[HotspotAnalysisTopic] = []
        for group_items, normalized_title in groups:
            existing = self._match_existing(normalized_title, context)
            title = existing.canonical_title if existing is not None else group_items[0].title
            summaries = [item.summary for item in group_items if item.summary]
            sources = {item.source for item in group_items if item.source}
            topics.append(
                HotspotAnalysisTopic(
                    canonical_title=title,
                    matched_item_ids=[item.id for item in group_items],
                    matched_existing_topic_id=existing.id if existing is not None else "",
                    summary=summaries[0] if summaries else title,
                    why_hot=f"本次采集中出现 {len(group_items)} 条相关记录，来源数 {len(sources)}。",
                    category=group_items[0].category,
                    trend="steady" if existing is not None else "rising",
                    confidence=0.6,
                )
            )
        return topics

    @staticmethod
    def _match_existing(
        normalized_title: str,
        context: list[HotspotTopicContext],
    ) -> HotspotTopicContext | None:
        for topic in context:
            if HotspotAgent._similar(normalized_title, topic.normalized_title):
                return topic
        return None

    @staticmethod
    def _similar(left: str, right: str) -> bool:
        if not left or not right:
            return False
        if left in right or right in left:
            return True
        return SequenceMatcher(None, left, right).ratio() >= 0.72

    @staticmethod
    def _normalize_trend(value: Any) -> str:
        text = str(value or "").strip().lower()
        return text if text in {"rising", "steady", "falling"} else "steady"

    @staticmethod
    def _normalize_confidence(value: Any) -> float:
        try:
            return max(0.0, min(float(value), 1.0))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _extract_json_object(content: str) -> dict[str, Any] | None:
        stripped = str(content or "").strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.IGNORECASE).strip()
            stripped = re.sub(r"```$", "", stripped).strip()
        try:
            parsed = json.loads(stripped)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass

        start = None
        depth = 0
        in_string = False
        escaped = False
        for index, char in enumerate(stripped):
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
                continue
            if char == "{":
                if depth == 0:
                    start = index
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0 and start is not None:
                    try:
                        parsed = json.loads(stripped[start : index + 1])
                    except json.JSONDecodeError:
                        return None
                    return parsed if isinstance(parsed, dict) else None
        return None
