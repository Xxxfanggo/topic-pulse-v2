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
        description=(
            "工具名：豆包搜索。\n"
            "用途：用于联网查询公开网页信息，获取用户问题相关的搜索结果。\n"
            "使用时机：当用户表达查询、搜索、查找、了解、核实、获取最新信息、"
            "查询最近动态、追踪新闻进展、查看实时情况等意图时，应优先使用该工具。\n"
            "适用范围：可查询任何话题内容，包括新闻热点、人物动态、事件进展、"
            "天气、政策法规、公司产品、公开资料、事实核查和实时信息。\n"
            "不适用场景：如果问题只需要基于当前对话、已知本地上下文或已有文档回答，"
            "且不需要联网获取新信息，则不必调用该工具。\n"
            "输入要求：query 应包含完整查询意图，尽量保留用户给出的时间、地点、"
            "人物、事件、范围等限定条件。\n"
            "输出说明：返回结构化网页搜索结果，包括查询词、结果数量、网页标题、"
            "来源站点、链接、摘要、正文内容、发布时间和原始响应数据。"
        ),
        parameters={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "必填。需要联网查询的完整问题或关键词。应尽量保留用户原始查询意图，"
                        "例如：某新闻话题最新进展、某人物最近消息、今天某地天气。"
                    ),
                },
                "count": {
                    "type": "integer",
                    "description": "返回搜索结果数量，范围 1 到 50。一般查询用 10，深度追踪可适当增加。",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 50,
                },
                "need_content": {
                    "type": "boolean",
                    "description": "是否返回网页正文内容。需要摘要、分析或长期跟踪话题时建议设为 true。",
                },
                "need_url": {
                    "type": "boolean",
                    "description": "是否返回结果 URL。需要引用来源、去重或写入时间线时建议设为 true。",
                },
                "time_range": {
                    "type": "string",
                    "description": (
                        "搜索时间范围，传给 Doubao Search API。适合表达最近一天、最近一周、"
                        "最近一个月、指定日期区间等时效要求。"
                    ),
                },
            },
            "required": ["query"],
        },
        tags={
            "local",
            "search",
            "web",
            "internet",
            "query",
            "latest",
            "news",
            "research",
            "doubao",
            "联网查询",
            "搜索",
            "最新进展",
            "新闻",
            "豆包搜索",
        },
        metadata={
            "provider": "doubao",
            "tool_display_name": "豆包搜索",
            "selection_hint": (
                "用户表达查询、搜索、了解、查找、核实、最新、最近、新闻、热点、"
                "进展、天气、政策等意图时，应调用此工具。"
            ),
        },
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
