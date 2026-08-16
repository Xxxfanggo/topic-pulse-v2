"""Local hot-topic ranking search tool."""

from __future__ import annotations

import re
from datetime import date as date_type
from datetime import datetime
from typing import TYPE_CHECKING, Any

from topic_pulse_v2.config import database_path
from topic_pulse_v2.process import SQLiteHotspotStore

if TYPE_CHECKING:
    from topic_pulse_v2.tool_register.registry import ToolRegistry


HOT_TOPIC_SEARCH_TOOL_NAME = "hot_topic_search"


def hot_topic_search(
    query: str | None = None,
    *,
    date: str | None = None,
    limit: int = 10,
    db_path: str | None = None,
    store: SQLiteHotspotStore | None = None,
) -> dict[str, Any]:
    """Search locally persisted hot-topic rankings."""

    target_date = _parse_date(date)
    safe_limit = max(1, min(int(limit or 10), 50))
    owns_store = store is None
    hotspot_store = store or SQLiteHotspotStore(path=db_path or database_path())
    try:
        rows = hotspot_store.list_daily_ranking(target_date, limit=50)
    finally:
        if owns_store:
            hotspot_store.close()

    ranked_items = [_ranking_item(row, query or "") for row in rows]
    if query:
        matched_items = [item for item in ranked_items if item["match_score"] > 0]
        ranked_items = matched_items
    ranked_items.sort(key=lambda item: (item["match_score"], item["score"], -item["rank"]), reverse=True)
    limited_items = ranked_items[:safe_limit]
    return {
        "date": target_date.isoformat(),
        "query": query or "",
        "count": len(limited_items),
        "total_count": len(ranked_items),
        "items": limited_items,
    }


def register_hot_topic_search_tool(
    registry: ToolRegistry,
    *,
    replace: bool = False,
) -> None:
    """Register the local hot-topic ranking search tool."""

    registry.register(
        HOT_TOPIC_SEARCH_TOOL_NAME,
        hot_topic_search,
        description=(
            "工具名：本地热点排行查询。\n"
            "用途：读取系统后台已经爬取、归并和沉淀的今日热点排行数据，用于回答用户关于今日热点、热点排行、"
            "持续高热事件、某个热点是否在榜等问题。\n"
            "使用时机：当用户询问“今日热点”“现在热门事件”“热点排行”“微博热搜沉淀结果”“今天哪些事件持续高热”等内容时，"
            "优先调用本工具读取本地数据；如果本地没有结果，再考虑联网搜索或说明暂无本地沉淀。\n"
            "输入说明：query 可选，用于按热点标题、摘要、分类、热度原因做本地匹配；date 可选，格式 YYYY-MM-DD，默认今天；"
            "limit 控制返回数量，默认 10。\n"
            "输出说明：返回本地热点排行条目，包括 rank、score、title、summary、why_hot、category、trend、"
            "source_count、observation_count、first_seen_at、last_seen_at。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "可选。用于匹配本地热点标题、摘要、分类和热度原因的关键词。",
                },
                "date": {
                    "type": "string",
                    "description": "可选。要查询的排行日期，格式 YYYY-MM-DD；默认查询今天。",
                },
                "limit": {
                    "type": "integer",
                    "description": "最多返回的热点数量，范围 1 到 50，默认 10。",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 50,
                },
            },
        },
        tags={
            "local",
            "hotspot",
            "hot-topic",
            "ranking",
            "news",
            "read",
            "search",
            "本地热点",
            "热点排行",
            "今日热点",
            "热搜",
        },
        metadata={
            "provider": "local",
            "tool_display_name": "本地热点排行查询",
            "selection_hint": "用户询问今日热点、热点排行、持续高热事件或本地已沉淀热搜时，优先调用本工具。",
        },
        replace=replace,
    )


register_tool = register_hot_topic_search_tool


def _parse_date(value: str | None) -> date_type:
    text = str(value or "").strip()
    if not text:
        return datetime.now().astimezone().date()
    return date_type.fromisoformat(text)


def _ranking_item(row: dict[str, Any], query: str) -> dict[str, Any]:
    title = str(row.get("canonical_title") or "").strip()
    summary = str(row.get("summary") or "").strip()
    why_hot = str(row.get("why_hot") or "").strip()
    category = str(row.get("category") or "").strip()
    return {
        "topic_id": str(row.get("topic_id") or ""),
        "rank": int(row.get("rank") or 0),
        "score": float(row.get("score") or 0.0),
        "title": title,
        "summary": summary,
        "why_hot": why_hot,
        "category": category,
        "trend": str(row.get("trend") or "").strip(),
        "first_seen_at": str(row.get("first_seen_at") or ""),
        "last_seen_at": str(row.get("last_seen_at") or ""),
        "source_count": int(row.get("source_count") or 0),
        "observation_count": int(row.get("observation_count") or 0),
        "match_score": _match_score(query, " ".join([title, summary, why_hot, category])),
    }


def _match_score(query: str, haystack: str) -> int:
    query = str(query or "").lower().strip()
    haystack = str(haystack or "").lower()
    if not query:
        return 0
    score = 0
    if query in haystack:
        score += 10
    for token in re.split(r"[\s,，、。；;：:（）()]+", query):
        if len(token) >= 2 and token in haystack:
            score += 1
        for fragment in _cjk_fragments(token):
            if fragment in haystack:
                score += 1
    return score


def _cjk_fragments(value: str) -> list[str]:
    fragments: list[str] = []
    for segment in re.findall(r"[\u4e00-\u9fff]{2,}", value):
        for size in (3, 2):
            if len(segment) < size:
                continue
            fragments.extend(
                segment[index : index + size]
                for index in range(0, len(segment) - size + 1)
            )
    return fragments
