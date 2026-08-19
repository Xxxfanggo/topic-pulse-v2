"""Render notification payloads for outbound channels."""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .models import TopicRefreshNotification


@dataclass(slots=True)
class EmailMessagePayload:
    subject: str
    text_body: str
    html_body: str


def render_topic_refresh_email(event: TopicRefreshNotification) -> EmailMessagePayload:
    result = event.result or {}
    topic_title = str(result.get("topic_name") or event.topic_title or "关注话题").strip()
    new_count = int(result.get("new_count") or 0)
    existing_count = int(result.get("existing_count") or 0)
    summary = str(result.get("summary") or "").strip()
    new_items = _normalize_items(result.get("new_items"))
    subject = f"「{topic_title}」有 {new_count} 条新动态"
    topic_url = _topic_url(event.app_base_url, event.topic_id)
    updated_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")

    item_lines = _text_item_lines(new_items)
    if not item_lines and summary:
        item_lines = [summary]
    if not item_lines:
        item_lines = ["本次刷新发现了新增内容，请进入话题详情查看完整 Markdown 记忆。"]

    text_parts = [
        f"你关注的话题「{topic_title}」已刷新。",
        "",
        "新增动态：",
        *[f"{index + 1}. {line}" for index, line in enumerate(item_lines[:5])],
        "",
        f"新增数量：{new_count}",
        f"已有信息去重：{existing_count}",
        f"更新时间：{updated_at}",
    ]
    if topic_url:
        text_parts.extend(["", f"查看完整话题：{topic_url}"])

    html_items = "".join(f"<li>{html.escape(line)}</li>" for line in item_lines[:5])
    link_html = f'<p><a href="{html.escape(topic_url)}">查看完整话题</a></p>' if topic_url else ""
    html_body = (
        "<html><body>"
        f"<p>你关注的话题<strong>「{html.escape(topic_title)}」</strong>已刷新。</p>"
        "<p>新增动态：</p>"
        f"<ol>{html_items}</ol>"
        f"<p>新增数量：{new_count}<br>已有信息去重：{existing_count}<br>更新时间：{html.escape(updated_at)}</p>"
        f"{link_html}"
        "</body></html>"
    )
    return EmailMessagePayload(
        subject=subject,
        text_body="\n".join(text_parts),
        html_body=html_body,
    )


def _topic_url(app_base_url: str, topic_id: str) -> str:
    base = str(app_base_url or "").strip().rstrip("/")
    if not base or not topic_id:
        return ""
    return f"{base}/topics/{topic_id}"


def _normalize_items(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    items = []
    for item in value:
        if isinstance(item, str):
            title = item.strip()
            if title:
                items.append({"title": title, "summary": "", "source": "", "url": ""})
            continue
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("标题") or "").strip()
        if not title:
            continue
        items.append(
            {
                "title": title,
                "summary": str(item.get("summary") or item.get("摘要") or "").strip(),
                "source": str(item.get("source") or item.get("来源") or "").strip(),
                "url": str(item.get("url") or item.get("链接") or "").strip(),
            }
        )
    return items


def _text_item_lines(items: list[dict[str, str]]) -> list[str]:
    lines = []
    for item in items:
        line = item["title"]
        if item.get("summary"):
            line = f"{line}：{item['summary']}"
        if item.get("source"):
            line = f"{line}（{item['source']}）"
        if item.get("url"):
            line = f"{line} {item['url']}"
        lines.append(line)
    return lines

