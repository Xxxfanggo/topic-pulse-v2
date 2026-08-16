"""Local Markdown memory tool for long-running news topic tracking."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from topic_pulse_v2.config import topics_dir
from topic_pulse_v2.topics import SQLiteTopicStore

if TYPE_CHECKING:
    from topic_pulse_v2.tool_register.registry import ToolRegistry

TOPIC_MARKDOWN_STORE_TOOL_NAME = "topic_markdown_store"
DEFAULT_ROOT = str(topics_dir())
SECTION_BASIC_INFO = "## 基本信息"
SECTION_SUMMARY = "## 摘要"
SECTION_TIMELINE = "## 时间线"
SECTION_FOLLOW_UP = "## 待跟进问题"


@dataclass(slots=True)
class TimelineItem:
    date: str
    title: str
    source: str = ""
    url: str = ""
    summary: str = ""


@dataclass(slots=True)
class TopicDocument:
    name: str
    path: str
    content: str
    summary: str = ""
    keywords: list[str] = field(default_factory=list)
    timeline_items: list[TimelineItem] = field(default_factory=list)


def topic_markdown_store(
    topic_name: str,
    *,
    latest_content: dict[str, Any] | list[Any] | str | None = None,
    timeline_items: list[dict[str, Any]] | None = None,
    keywords: list[str] | None = None,
    summary: str | None = None,
    root_dir: str = DEFAULT_ROOT,
    user_id: str | None = None,
    current_status: str = "持续关注",
    created_at: str | None = None,
    operation: str = "auto",
) -> dict[str, Any]:
    """Create or update a local Markdown memory file for a news topic."""

    if operation not in {"auto", "create", "update"}:
        raise ValueError("operation must be one of: auto, create, update.")
    store = _TopicMarkdownStore(root_dir, user_id=user_id)
    normalized_content = _normalize_latest_content(latest_content)
    inferred_keywords = keywords or _extract_keywords(normalized_content)
    inferred_summary = summary or _extract_summary(normalized_content)
    inferred_timeline_items = _timeline_items_from_payload(timeline_items) or _extract_timeline_items(normalized_content)
    topic_path = store.topic_path(topic_name)
    created = not topic_path.exists()
    actual_operation = "create" if created else "update"
    if operation == "update" and created:
        raise FileNotFoundError(f"topic does not exist, cannot update: {topic_name}")
    if operation == "create" and not created:
        actual_operation = "update"

    store.get_or_create_topic(
        topic_name,
        keywords=inferred_keywords,
        summary=inferred_summary,
        current_status=current_status,
        created_at=created_at,
    )
    if not created:
        store.update_basic_info(
            topic_name,
            keywords=inferred_keywords,
            current_status=current_status,
        )
    appended_items = store.append_timeline_items(topic_name, inferred_timeline_items)
    document_after = store.update_summary(topic_name, inferred_summary) if inferred_summary else store.read_topic(topic_name)
    topic_record = store.topic_record(topic_name)
    appended_keys = {store._timeline_key(item) for item in appended_items}
    existing_items = [
        item
        for item in document_after.timeline_items
        if store._timeline_key(item) not in appended_keys
    ]

    return {
        "topic_name": document_after.name,
        "topic_id": topic_record.id if topic_record else "",
        "path": document_after.path,
        "created": created,
        "operation": actual_operation,
        "keywords": document_after.keywords,
        "summary": document_after.summary,
        "appended_count": len(appended_items),
        "timeline_count": len(document_after.timeline_items),
        "appended_items": [_timeline_item_to_dict(item) for item in appended_items],
        "new_count": len(appended_items),
        "existing_count": len(existing_items),
        "new_items": [_timeline_item_to_dict(item) for item in appended_items],
        "existing_items": [_timeline_item_to_dict(item) for item in existing_items[:8]],
        "update_status": "created" if created else ("updated_with_new_items" if appended_items else "no_new_items"),
    }


def register_topic_markdown_store_tool(
    registry: ToolRegistry,
    *,
    replace: bool = False,
) -> None:
    """Register the topic Markdown store tool in a registry."""

    registry.register(
        TOPIC_MARKDOWN_STORE_TOOL_NAME,
        topic_markdown_store,
        description=(
            "工具名：话题 Markdown 存储。\n"
            "用途：用于把某一具体新闻话题的联网搜索结果记录到本地 Markdown 记忆中，"
            "并在后续搜索到最新内容后与本地已存储记忆合并更新。\n"
            "使用时机：当用户针对某一具体新闻话题完成联网搜索后，需要保存、记录、"
            "更新、沉淀、长期关注、维护时间线或同步本地记忆时，应使用该工具。\n"
            "适用范围：适合新闻事件、人物动态、公共事件、舆情热点、政策进展等"
            "需要持续追踪的具体话题。\n"
            "不适用场景：不用于联网查询本身；查询最新信息应先使用 doubao_search，"
            "再把搜索结果传给本工具存储和合并。\n"
            "输入要求：topic_name 必须是具体新闻话题名称；latest_content 应传入"
            "联网搜索或模型整理后的结构化内容，可包含 web_results、hot_news、"
            "热点新闻汇总、summary、overall_summary 等字段。\n"
            "输出说明：返回 Markdown 文件路径、摘要、关键词、追加条目数量和当前时间线数量。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "topic_name": {
                    "type": "string",
                    "description": "需要长期记录和更新的具体新闻话题名称。",
                },
                "latest_content": {
                    "type": "object",
                    "description": (
                        "联网搜索后的最新内容或结构化整理结果。可传 doubao_search 的返回值，"
                        "或包含 hot_news/热点新闻汇总/web_results 等字段的对象。"
                    ),
                },
                "timeline_items": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": (
                        "模型根据本地旧内容和联网新内容提炼后的时间线条目。"
                        "每条建议包含 date/title/source/url/summary 字段；如果不传，会尝试从 latest_content 中提取。"
                    ),
                },
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "话题关键词。未提供时会尝试从 latest_content 中提取。",
                },
                "summary": {
                    "type": "string",
                    "description": "话题摘要。未提供时会尝试从 latest_content 中提取。",
                },
                "root_dir": {
                    "type": "string",
                    "description": "Markdown 话题文件存储目录，默认 data/topics。",
                    "default": DEFAULT_ROOT,
                },
                "current_status": {
                    "type": "string",
                    "description": "话题当前状态，默认持续关注。",
                    "default": "持续关注",
                },
                "operation": {
                    "type": "string",
                    "enum": ["auto", "create", "update"],
                    "description": (
                        "写入操作。auto 表示文件不存在则创建、存在则更新；create 表示创建语义；"
                        "update 表示必须更新已有文件，文件不存在会报错。"
                    ),
                    "default": "auto",
                },
            },
            "required": ["topic_name"],
        },
        tags={
            "local",
            "markdown",
            "memory",
            "topic",
            "news",
            "timeline",
            "话题记忆",
            "本地记忆",
            "时间线",
            "新闻追踪",
        },
        metadata={
            "provider": "local",
            "tool_display_name": "话题 Markdown 存储",
            "selection_hint": (
                "用户需要把具体新闻话题的搜索结果保存到本地、更新本地记忆、"
                "合并最新进展或维护 Markdown 时间线时，应调用此工具。"
            ),
        },
        replace=replace,
    )


register_tool = register_topic_markdown_store_tool


class _TopicMarkdownStore:
    def __init__(self, root_dir: str | Path = DEFAULT_ROOT, *, user_id: str | None = None) -> None:
        self.root_dir = Path(root_dir).resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.user_id = str(user_id or "").strip() or None
        self.topic_store = SQLiteTopicStore(topics_dir=self.root_dir) if self.user_id else None

    def topic_path(self, topic_name: str) -> Path:
        if self.user_id and self.topic_store is not None:
            topic = self.topic_store.create_or_get_topic(
                user_id=self.user_id,
                title=topic_name,
            )
            return Path(topic.markdown_path).resolve()
        normalized_name = self._normalize_topic_name(topic_name)
        path = (self.root_dir / f"{normalized_name}.md").resolve()
        if self.root_dir not in path.parents and path != self.root_dir:
            raise ValueError("topic path must stay inside root_dir.")
        return path

    def get_or_create_topic(
        self,
        topic_name: str,
        *,
        keywords: list[str] | None = None,
        summary: str = "",
        current_status: str = "持续关注",
        created_at: str | None = None,
    ) -> TopicDocument:
        path = self.topic_path(topic_name)
        if path.exists():
            return self.read_topic(topic_name)
        return self.create_topic(
            topic_name,
            keywords=keywords,
            summary=summary,
            current_status=current_status,
            created_at=created_at,
        )

    def create_topic(
        self,
        topic_name: str,
        *,
        keywords: list[str] | None = None,
        summary: str = "",
        current_status: str = "持续关注",
        created_at: str | None = None,
    ) -> TopicDocument:
        path = self.topic_path(topic_name)
        timestamp = created_at or date.today().isoformat()
        content = self._build_template(
            topic_name=topic_name.strip(),
            keywords=keywords or [],
            summary=summary,
            current_status=current_status,
            created_at=timestamp,
            updated_at=timestamp,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self._touch_topic(topic_name)
        return self.read_topic(topic_name)

    def read_topic(self, topic_name: str) -> TopicDocument:
        path = self.topic_path(topic_name)
        if not path.exists():
            raise FileNotFoundError(f"topic does not exist: {topic_name}")
        content = path.read_text(encoding="utf-8")
        return TopicDocument(
            name=self._extract_title(content) or topic_name.strip(),
            path=str(path),
            content=content,
            summary=self._extract_section_body(content, SECTION_SUMMARY).strip(),
            keywords=self._extract_keywords(content),
            timeline_items=self._extract_existing_timeline_items(content),
        )

    def append_timeline_items(self, topic_name: str, items: list[TimelineItem]) -> list[TimelineItem]:
        if not items:
            return []
        document = self.get_or_create_topic(topic_name)
        existing_keys = {self._timeline_key(item) for item in document.timeline_items}
        new_items: list[TimelineItem] = []
        for item in items:
            if not item.date.strip() or not item.title.strip():
                continue
            key = self._timeline_key(item)
            if key in existing_keys:
                continue
            existing_keys.add(key)
            new_items.append(item)
        if not new_items:
            return []
        sorted_items = self._sort_timeline_items_desc(document.timeline_items + new_items)
        updated_body = self._timeline_body_from_items(sorted_items)
        content = self._replace_section_body(document.content, SECTION_TIMELINE, updated_body)
        content = self._set_basic_info_value(content, "最近更新时间", self._now())
        Path(document.path).write_text(content, encoding="utf-8")
        self._touch_topic(topic_name)
        return new_items

    def update_summary(self, topic_name: str, summary: str) -> TopicDocument:
        document = self.read_topic(topic_name)
        content = self._replace_section_body(
            document.content,
            SECTION_SUMMARY,
            f"\n{summary.strip() or '暂无摘要。'}\n",
        )
        content = self._set_basic_info_value(content, "最近更新时间", self._now())
        Path(document.path).write_text(content, encoding="utf-8")
        self._touch_topic(topic_name)
        return self.read_topic(topic_name)

    def update_basic_info(
        self,
        topic_name: str,
        *,
        keywords: list[str] | None = None,
        current_status: str | None = None,
    ) -> TopicDocument:
        document = self.read_topic(topic_name)
        content = document.content
        if keywords is not None:
            keyword_text = "、".join(keyword.strip() for keyword in keywords if keyword.strip())
            content = self._set_basic_info_value(content, "关键词", keyword_text)
        if current_status is not None:
            content = self._set_basic_info_value(content, "当前状态", current_status)
        content = self._set_basic_info_value(content, "最近更新时间", self._now())
        Path(document.path).write_text(content, encoding="utf-8")
        self._touch_topic(topic_name)
        return self.read_topic(topic_name)

    def topic_record(self, topic_name: str):
        if not self.user_id or self.topic_store is None:
            return None
        return self.topic_store.get_by_title(user_id=self.user_id, title=topic_name)

    def _touch_topic(self, topic_name: str) -> None:
        record = self.topic_record(topic_name)
        if record is not None and self.topic_store is not None:
            self.topic_store.touch_topic(record.id)

    @staticmethod
    def _normalize_topic_name(topic_name: str) -> str:
        name = topic_name.strip()
        if not name:
            raise ValueError("topic_name cannot be empty.")
        sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
        sanitized = re.sub(r"\s+", " ", sanitized).strip(" .")
        if not sanitized:
            raise ValueError("topic_name cannot be used as a file name.")
        return sanitized

    @staticmethod
    def _build_template(
        *,
        topic_name: str,
        keywords: list[str],
        summary: str,
        current_status: str,
        created_at: str,
        updated_at: str,
    ) -> str:
        keyword_text = "、".join(keyword.strip() for keyword in keywords if keyword.strip())
        summary_text = summary.strip() or "暂无摘要。"
        return (
            f"# {topic_name}\n\n"
            f"{SECTION_BASIC_INFO}\n\n"
            f"- 关注时间：{created_at}\n"
            f"- 关键词：{keyword_text}\n"
            f"- 当前状态：{current_status}\n"
            f"- 最近更新时间：{updated_at}\n\n"
            f"{SECTION_SUMMARY}\n\n"
            f"{summary_text}\n\n"
            f"{SECTION_TIMELINE}\n\n"
            "暂无时间线记录。\n\n"
            f"{SECTION_FOLLOW_UP}\n\n"
            "- \n"
        )

    @staticmethod
    def _extract_title(content: str) -> str:
        match = re.search(r"^#\s+(.+?)\s*$", content, flags=re.MULTILINE)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _extract_section_body(content: str, heading: str) -> str:
        pattern = re.compile(
            rf"^{re.escape(heading)}\s*\n(?P<body>.*?)(?=^##\s+|\Z)",
            flags=re.MULTILINE | re.DOTALL,
        )
        match = pattern.search(content)
        return match.group("body") if match else ""

    @staticmethod
    def _replace_section_body(content: str, heading: str, body: str) -> str:
        pattern = re.compile(
            rf"(^{re.escape(heading)}\s*\n)(?P<body>.*?)(?=^##\s+|\Z)",
            flags=re.MULTILINE | re.DOTALL,
        )
        if not pattern.search(content):
            suffix = "" if content.endswith("\n") else "\n"
            return f"{content}{suffix}\n{heading}\n{body}"
        return pattern.sub(lambda match: f"{match.group(1)}{body}", content, count=1)

    @staticmethod
    def _extract_keywords(content: str) -> list[str]:
        match = re.search(r"^- 关键词：(?P<value>.*)$", content, flags=re.MULTILINE)
        if not match:
            return []
        return [item.strip() for item in re.split(r"[、,，]", match.group("value")) if item.strip()]

    @classmethod
    def _extract_existing_timeline_items(cls, content: str) -> list[TimelineItem]:
        body = cls._extract_section_body(content, SECTION_TIMELINE)
        chunks = re.split(r"(?=^###\s+)", body, flags=re.MULTILINE)
        items: list[TimelineItem] = []
        for chunk in chunks:
            date_match = re.search(r"^###\s+(?P<date>.+?)\s*$", chunk, flags=re.MULTILINE)
            if not date_match:
                continue
            items.append(
                TimelineItem(
                    date=date_match.group("date").strip(),
                    title=cls._extract_bullet_value(chunk, "标题"),
                    source=cls._extract_bullet_value(chunk, "来源"),
                    url=cls._extract_bullet_value(chunk, "链接"),
                    summary=cls._extract_bullet_value(chunk, "摘要"),
                )
            )
        return items

    @staticmethod
    def _extract_bullet_value(chunk: str, label: str) -> str:
        match = re.search(rf"^- {re.escape(label)}：(?P<value>.*)$", chunk, flags=re.MULTILINE)
        return match.group("value").strip() if match else ""

    @staticmethod
    def _timeline_body_from_items(items: list[TimelineItem]) -> str:
        blocks = [_format_timeline_item(item).strip() for item in items]
        return "\n\n" + "\n\n".join(blocks).strip() + "\n\n"

    @staticmethod
    def _sort_timeline_items_desc(items: list[TimelineItem]) -> list[TimelineItem]:
        return sorted(items, key=lambda item: _timeline_sort_key(item.date), reverse=True)

    @staticmethod
    def _timeline_key(item: TimelineItem) -> tuple[str, str]:
        if item.url.strip():
            return ("url", item.url.strip().lower())
        return ("title", item.title.strip().lower())

    @staticmethod
    def _set_basic_info_value(content: str, label: str, value: str) -> str:
        pattern = re.compile(rf"^- {re.escape(label)}：.*$", flags=re.MULTILINE)
        replacement = f"- {label}：{value}"
        if pattern.search(content):
            return pattern.sub(replacement, content, count=1)
        body = _TopicMarkdownStore._extract_section_body(content, SECTION_BASIC_INFO)
        return _TopicMarkdownStore._replace_section_body(
            content,
            SECTION_BASIC_INFO,
            body.rstrip() + f"\n{replacement}\n\n",
        )

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")


def _normalize_latest_content(value: dict[str, Any] | list[Any] | str | None) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        if isinstance(value.get("result"), dict):
            return _normalize_latest_content(value["result"])
        if isinstance(value.get("answer"), str):
            try:
                return _normalize_latest_content(json.loads(value["answer"]))
            except json.JSONDecodeError:
                return value
        return value
    if isinstance(value, list):
        return {"items": value}
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {"summary": str(value)}
    return parsed if isinstance(parsed, dict) else {"items": parsed}


def _extract_keywords(content: dict[str, Any]) -> list[str]:
    keywords = content.get("keywords") or content.get("关键词")
    if isinstance(keywords, list):
        return [str(item).strip() for item in keywords if str(item).strip()]
    news_items = _news_items(content)
    extracted = [
        str(item.get("topic") or item.get("事件") or item.get("title") or item.get("标题")).strip()
        for item in news_items
        if isinstance(item, dict)
        and (item.get("topic") or item.get("事件") or item.get("title") or item.get("标题"))
    ]
    return extracted[:10]


def _extract_summary(content: dict[str, Any]) -> str:
    summary = (
        content.get("summary")
        or content.get("overall_summary")
        or content.get("key_takeaway")
        or content.get("摘要")
        or content.get("总体摘要")
        or content.get("核心结论")
    )
    if summary:
        return str(summary).strip()
    details = [
        str(item.get("summary") or item.get("详情") or item.get("snippet") or "").strip()
        for item in _news_items(content)[:2]
        if isinstance(item, dict)
    ]
    return "；".join(item for item in details if item)


def _extract_timeline_items(content: dict[str, Any]) -> list[TimelineItem]:
    items: list[TimelineItem] = []
    for item in _news_items(content):
        if not isinstance(item, dict):
            continue
        title = str(_item_value(item, "title", "Title", "topic", "event", "事件", "标题")).strip()
        if not title:
            continue
        items.append(
            TimelineItem(
                date=_date_from_item(item),
                title=title,
                source=str(_item_value(item, "site", "site_name", "SiteName", "source", "来源")).strip(),
                url=str(_item_value(item, "url", "Url", "链接")).strip(),
                summary=str(
                    _item_value(
                        item,
                        "summary",
                        "Summary",
                        "snippet",
                        "Snippet",
                        "content",
                        "Content",
                        "detail",
                        "details",
                        "详情",
                        "摘要",
                        "关键进展",
                    )
                ).strip(),
            )
        )
    return items


def _timeline_items_from_payload(items: list[dict[str, Any]] | None) -> list[TimelineItem]:
    if not items:
        return []
    return _extract_timeline_items({"timeline_items": items})


def _news_items(content: dict[str, Any]) -> list[Any]:
    if isinstance(content.get("result"), dict):
        return _news_items(content["result"])
    collected: list[Any] = []
    for key in ("hot_news", "热点新闻汇总", "web_results", "items", "timeline_items", "时间线"):
        value = content.get(key)
        if isinstance(value, list):
            collected.extend(value)
        elif isinstance(value, dict):
            nested_items = value.get("item") or value.get("items") or value.get("list") or value.get("data")
            if isinstance(nested_items, list):
                collected.extend(nested_items)
    structured_items = [item for item in collected if _looks_like_timeline_source(item)]
    return structured_items or collected


def _looks_like_timeline_source(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    title = _item_value(item, "title", "Title", "topic", "event", "事件", "标题")
    if not title:
        return False
    return bool(
        _item_value(item, "date", "日期", "time", "时间", "publish_time", "PublishTime")
        or _item_value(item, "summary", "Summary", "snippet", "Snippet", "详情", "摘要")
        or _item_value(item, "url", "Url", "链接")
        or _item_value(item, "site", "site_name", "SiteName", "source", "来源")
    )


def _date_from_item(item: dict[str, Any]) -> str:
    value = _item_value(
        item,
        "date",
        "日期",
        "time",
        "时间",
        "publish_time",
        "PublishTime",
    )
    if value:
        return str(value).strip()[:10]
    return date.today().isoformat()


def _item_value(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = item.get(key)
        if value:
            return value
    raw = item.get("raw")
    if isinstance(raw, dict):
        for key in keys:
            value = raw.get(key)
            if value:
                return value
    return ""


def _format_timeline_item(item: TimelineItem) -> str:
    return (
        f"### {item.date}\n\n"
        f"- 来源：{item.source}\n"
        f"- 标题：{item.title}\n"
        f"- 链接：{item.url}\n"
        f"- 摘要：{item.summary}\n"
    )


def _timeline_sort_key(value: str) -> str:
    match = re.search(r"\d{4}-\d{2}-\d{2}", value)
    if match:
        return match.group(0)
    match = re.search(r"\d{4}年\d{1,2}月\d{1,2}日", value)
    if match:
        year, month, day = re.findall(r"\d+", match.group(0))
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    return value


def _timeline_item_to_dict(item: TimelineItem) -> dict[str, Any]:
    return {
        "date": item.date,
        "title": item.title,
        "source": item.source,
        "url": item.url,
        "summary": item.summary,
    }
