"""Tool registration and management module."""

from .registry import ToolRegistry
from .tools import (
    DOUBAO_SEARCH_TOOL_NAME,
    HOT_TOPIC_SEARCH_TOOL_NAME,
    TOPIC_MARKDOWN_READ_DETAIL_TOOL_NAME,
    TOPIC_MARKDOWN_READ_SUMMARY_TOOL_NAME,
    TOPIC_MARKDOWN_STORE_TOOL_NAME,
    TOPIC_SCHEDULE_CREATE_TOOL_NAME,
    doubao_search,
    hot_topic_search,
    register_doubao_search_tool,
    register_hot_topic_search_tool,
    register_topic_markdown_read_tools,
    register_topic_markdown_store_tool,
    register_topic_schedule_create_tool,
    topic_markdown_read_detail,
    topic_markdown_read_summary,
    topic_markdown_store,
    topic_schedule_create,
)
from .types import ToolHandler, ToolSpec

__all__ = [
    "DOUBAO_SEARCH_TOOL_NAME",
    "HOT_TOPIC_SEARCH_TOOL_NAME",
    "TOPIC_MARKDOWN_READ_DETAIL_TOOL_NAME",
    "TOPIC_MARKDOWN_READ_SUMMARY_TOOL_NAME",
    "TOPIC_MARKDOWN_STORE_TOOL_NAME",
    "TOPIC_SCHEDULE_CREATE_TOOL_NAME",
    "ToolHandler",
    "ToolRegistry",
    "ToolSpec",
    "doubao_search",
    "hot_topic_search",
    "register_doubao_search_tool",
    "register_hot_topic_search_tool",
    "register_topic_markdown_read_tools",
    "register_topic_markdown_store_tool",
    "register_topic_schedule_create_tool",
    "topic_markdown_read_detail",
    "topic_markdown_read_summary",
    "topic_markdown_store",
    "topic_schedule_create",
]
