"""Built-in local tool implementations."""

from __future__ import annotations

from importlib import import_module
from pkgutil import iter_modules
from typing import TYPE_CHECKING

from .doubao_search import (
    DOUBAO_SEARCH_TOOL_NAME,
    doubao_search,
    register_doubao_search_tool,
)
from .topic_markdown_store import (
    TOPIC_MARKDOWN_STORE_TOOL_NAME,
    register_topic_markdown_store_tool,
    topic_markdown_store,
)
from .topic_markdown_read import (
    TOPIC_MARKDOWN_READ_DETAIL_TOOL_NAME,
    TOPIC_MARKDOWN_READ_SUMMARY_TOOL_NAME,
    register_topic_markdown_read_tools,
    topic_markdown_read_detail,
    topic_markdown_read_summary,
)

if TYPE_CHECKING:
    from topic_pulse_v2.tool_register.registry import ToolRegistry


def register_local_tools(registry: ToolRegistry, *, replace: bool = False) -> None:
    """Discover and register all local tool modules in this package."""

    for module_info in iter_modules(__path__):
        module = import_module(f"{__name__}.{module_info.name}")
        register_tool = getattr(module, "register_tool", None)
        if register_tool is not None:
            register_tool(registry, replace=replace)


__all__ = [
    "DOUBAO_SEARCH_TOOL_NAME",
    "TOPIC_MARKDOWN_READ_DETAIL_TOOL_NAME",
    "TOPIC_MARKDOWN_READ_SUMMARY_TOOL_NAME",
    "TOPIC_MARKDOWN_STORE_TOOL_NAME",
    "doubao_search",
    "register_doubao_search_tool",
    "register_local_tools",
    "register_topic_markdown_read_tools",
    "register_topic_markdown_store_tool",
    "topic_markdown_read_detail",
    "topic_markdown_read_summary",
    "topic_markdown_store",
]
