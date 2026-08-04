"""Local Markdown memory read tools for news topic tracking."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .topic_markdown_store import (
    DEFAULT_ROOT,
    SECTION_BASIC_INFO,
    SECTION_SUMMARY,
    SECTION_TIMELINE,
    TOPIC_MARKDOWN_STORE_TOOL_NAME,
    _TopicMarkdownStore,
)

if TYPE_CHECKING:
    from topic_pulse_v2.tool_register.registry import ToolRegistry

TOPIC_MARKDOWN_READ_SUMMARY_TOOL_NAME = "topic_markdown_read_summary"
TOPIC_MARKDOWN_READ_DETAIL_TOOL_NAME = "topic_markdown_read_detail"


def topic_markdown_read_summary(
    query: str | None = None,
    *,
    root_dir: str = DEFAULT_ROOT,
    limit: int = 20,
) -> dict[str, Any]:
    """Read topic Markdown summaries so the LLM can judge local topic matches."""

    root = Path(root_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    topics = [_read_markdown_summary(path, query or "") for path in root.glob("*.md")]
    topics = sorted(
        topics,
        key=lambda item: (item["match_score"], item["updated_at"], item["topic_name"]),
        reverse=True,
    )
    if query:
        matched = [item for item in topics if item["match_score"] > 0]
        topics = matched or topics
    limited_topics = topics[: max(1, limit)]
    return {
        "root_dir": str(root),
        "query": query or "",
        "count": len(limited_topics),
        "total_count": len(topics),
        "topics": limited_topics,
    }


def topic_markdown_read_detail(
    *,
    topic_name: str | None = None,
    path: str | None = None,
    root_dir: str = DEFAULT_ROOT,
) -> dict[str, Any]:
    """Read full Markdown detail for one stored news topic."""

    root = Path(root_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    resolved_path = _resolve_topic_path(root, topic_name=topic_name, path=path)
    if not resolved_path.exists():
        raise FileNotFoundError(f"topic markdown does not exist: {resolved_path}")

    content = resolved_path.read_text(encoding="utf-8")
    timeline_items = _TopicMarkdownStore._extract_existing_timeline_items(content)
    return {
        "topic_name": _extract_title(content) or resolved_path.stem,
        "path": str(resolved_path),
        "basic_info": _extract_basic_info(content),
        "summary": _TopicMarkdownStore._extract_section_body(content, SECTION_SUMMARY).strip(),
        "timeline_count": len(timeline_items),
        "timeline_items": [
            {
                "date": item.date,
                "title": item.title,
                "source": item.source,
                "url": item.url,
                "summary": item.summary,
            }
            for item in timeline_items
        ],
        "content": content,
    }


def register_topic_markdown_read_tools(
    registry: ToolRegistry,
    *,
    replace: bool = False,
) -> None:
    """Register local Markdown memory read tools."""

    registry.register(
        TOPIC_MARKDOWN_READ_SUMMARY_TOOL_NAME,
        topic_markdown_read_summary,
        description=(
            "工具名：话题 Markdown 摘要读取。\n"
            "用途：读取 data/topics 下已存储话题 Markdown 文件的标题、基本信息和摘要，用于判断当前联网搜索的话题是否已有本地记忆。\n"
            "使用时机：在 doubao_search 获取某个具体新闻话题的最新结果之后，必须先调用本工具查看本地是否存在相关话题。\n"
            "工作方式：传入 query 后会扫描本地 Markdown 话题文件，并按标题、关键词、摘要与 query 的匹配程度排序返回候选话题。\n"
            "下一步：如果返回候选话题与当前搜索话题相关，再调用 topic_markdown_read_detail 读取完整内容；如果没有相关候选，再调用 topic_markdown_store 创建新文件。\n"
            f"注意：本工具只读取摘要，不负责写入；写入或更新请使用 {TOPIC_MARKDOWN_STORE_TOOL_NAME}。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "当前用户查询或联网搜索的话题名称，用于匹配本地已存储话题。",
                },
                "root_dir": {
                    "type": "string",
                    "description": "Markdown 话题文件存储目录，默认 data/topics。",
                    "default": DEFAULT_ROOT,
                },
                "limit": {
                    "type": "integer",
                    "description": "最多返回的候选话题数量。",
                    "default": 20,
                },
            },
        },
        tags={"local", "markdown", "memory", "topic", "news", "read", "summary", "本地记忆", "话题召回"},
        metadata={
            "provider": "local",
            "tool_display_name": "话题 Markdown 摘要读取",
            "selection_hint": "联网搜索后需要判断本地是否已有相关话题记忆时，优先调用本工具。",
        },
        replace=replace,
    )
    registry.register(
        TOPIC_MARKDOWN_READ_DETAIL_TOOL_NAME,
        topic_markdown_read_detail,
        description=(
            "工具名：话题 Markdown 详情读取。\n"
            "用途：读取某一个本地话题 Markdown 文件的完整内容，包括基本信息、摘要、时间线和原始 Markdown 文本。\n"
            "使用时机：topic_markdown_read_summary 已找到可能相关的本地话题后，调用本工具读取详情，再结合 doubao_search 的最新结果提炼更新内容。\n"
            f"下一步：读取详情后，如果需要合并最新进展，调用 {TOPIC_MARKDOWN_STORE_TOOL_NAME} 进行更新。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "topic_name": {
                    "type": "string",
                    "description": "要读取的本地话题名称。topic_name 和 path 至少提供一个。",
                },
                "path": {
                    "type": "string",
                    "description": "要读取的 Markdown 文件路径。必须位于 root_dir 目录内。",
                },
                "root_dir": {
                    "type": "string",
                    "description": "Markdown 话题文件存储目录，默认 data/topics。",
                    "default": DEFAULT_ROOT,
                },
            },
        },
        tags={"local", "markdown", "memory", "topic", "news", "read", "detail", "本地记忆", "话题详情"},
        metadata={
            "provider": "local",
            "tool_display_name": "话题 Markdown 详情读取",
            "selection_hint": "已确认本地存在相关话题，需要读取完整 Markdown 内容进行合并更新时调用。",
        },
        replace=replace,
    )


register_tool = register_topic_markdown_read_tools


def _read_markdown_summary(path: Path, query: str) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8")
    title = _extract_title(content) or path.stem
    basic_info = _extract_basic_info(content)
    summary = _TopicMarkdownStore._extract_section_body(content, SECTION_SUMMARY).strip()
    haystack = " ".join([title, summary, " ".join(basic_info.values())]).lower()
    score = _match_score(query, haystack)
    return {
        "topic_name": title,
        "path": str(path.resolve()),
        "basic_info": basic_info,
        "summary": summary,
        "keywords": _split_keywords(basic_info.get("关键词", "")),
        "created_at": basic_info.get("关注时间", ""),
        "updated_at": basic_info.get("最近更新时间", ""),
        "match_score": score,
    }


def _resolve_topic_path(root: Path, *, topic_name: str | None, path: str | None) -> Path:
    if path:
        resolved = Path(path).resolve()
    elif topic_name:
        resolved = _TopicMarkdownStore(root).topic_path(topic_name)
    else:
        raise ValueError("topic_name and path cannot both be empty.")
    if root not in resolved.parents:
        raise ValueError("topic markdown path must stay inside root_dir.")
    return resolved


def _extract_title(content: str) -> str:
    match = re.search(r"^#\s+(.+?)\s*$", content, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def _extract_basic_info(content: str) -> dict[str, str]:
    body = _TopicMarkdownStore._extract_section_body(content, SECTION_BASIC_INFO)
    info: dict[str, str] = {}
    for line in body.splitlines():
        match = re.match(r"^-\s*(?P<label>[^：:]+)[：:](?P<value>.*)$", line.strip())
        if match:
            info[match.group("label").strip()] = match.group("value").strip()
    return info


def _split_keywords(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[、,，\s]+", value) if item.strip()]


def _match_score(query: str, haystack: str) -> int:
    query = query.lower().strip()
    if not query:
        return 0
    score = 0
    if query in haystack:
        score += 10
    for token in re.split(r"[\s,，、。；;：:（）()]+", query):
        if len(token) >= 2 and token in haystack:
            score += 1
    return score
