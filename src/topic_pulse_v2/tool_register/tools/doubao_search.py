"""Local Doubao search tool."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from topic_pulse_v2.information_search import (
    DoubaoSearchClient,
    DoubaoSearchConfig,
    DoubaoSearchResponse,
)

if TYPE_CHECKING:
    from topic_pulse_v2.tool_register.registry import ToolRegistry

DOUBAO_SEARCH_TOOL_NAME = "doubao_search"


def doubao_search(
    query: str,
    *,
    count: int = 10,
    need_content: bool | None = None,
    need_url: bool | None = None,
    time_range: str | None = None,
    api_key: str | None = None,
    timeout: float = 30.0,
    client: DoubaoSearchClient | None = None,
) -> dict[str, Any]:
    """Search the web through Doubao and return JSON-serializable data."""

    search_client = client or DoubaoSearchClient(
        DoubaoSearchConfig(api_key=api_key, timeout=timeout)
    )
    response = search_client.web_search(
        query,
        count=count,
        need_content=need_content,
        need_url=need_url,
        time_range=time_range,
    )
    return _response_to_dict(response)


def register_doubao_search_tool(
    registry: ToolRegistry,
    *,
    replace: bool = False,
) -> None:
    """Register the local Doubao search tool in a registry."""

    registry.register(
        DOUBAO_SEARCH_TOOL_NAME,
        doubao_search,
        description="豆包搜索：调用 Doubao Search web_search 进行联网搜索。",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词或问题。",
                },
                "count": {
                    "type": "integer",
                    "description": "返回结果数量，范围 1 到 50。",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 50,
                },
                "need_content": {
                    "type": "boolean",
                    "description": "是否返回网页正文内容。",
                },
                "need_url": {
                    "type": "boolean",
                    "description": "是否返回结果 URL。",
                },
                "time_range": {
                    "type": "string",
                    "description": "搜索时间范围，传给 Doubao Search API。",
                },
            },
            "required": ["query"],
        },
        tags={"local", "search", "web", "doubao", "豆包搜索"},
        metadata={"provider": "doubao", "tool_display_name": "豆包搜索"},
        replace=replace,
    )


register_tool = register_doubao_search_tool


def _response_to_dict(response: DoubaoSearchResponse) -> dict[str, Any]:
    return {
        "query": response.query,
        "search_type": response.search_type,
        "result_count": response.result_count,
        "time_cost_ms": response.time_cost_ms,
        "log_id": response.log_id,
        "request_id": response.request_id,
        "search_context": response.search_context,
        "web_results": [
            {
                "id": item.id,
                "sort_id": item.sort_id,
                "title": item.title,
                "site_name": item.site_name,
                "url": item.url,
                "snippet": item.snippet,
                "summary": item.summary,
                "content": item.content,
                "publish_time": item.publish_time,
                "logo_url": item.logo_url,
                "rank_score": item.rank_score,
                "raw": item.raw,
            }
            for item in response.web_results
        ],
        "raw": response.raw,
    }
