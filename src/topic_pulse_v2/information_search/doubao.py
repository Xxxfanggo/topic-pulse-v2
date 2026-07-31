"""Doubao AI search integration.

Official docs:
https://docs.volcengine.com/docs/87772/2272953?lang=zh
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DOUBAO_SEARCH_ENDPOINT = "https://open.feedcoopapi.com/search_api/web_search"
DEFAULT_API_KEY_ENV = "DOUBAO_SEARCH_API_KEY"

HttpTransport = Callable[
    [str, dict[str, Any], Mapping[str, str], float],
    tuple[int, Mapping[str, str], bytes],
]


class DoubaoSearchError(RuntimeError):
    """Raised when Doubao search cannot return a successful response."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response = dict(response or {})


@dataclass(slots=True)
class DoubaoSearchConfig:
    """Configuration for Doubao Search API Key access."""

    api_key: str | None = None
    endpoint: str = DOUBAO_SEARCH_ENDPOINT
    timeout: float = 30.0
    api_key_env: str = DEFAULT_API_KEY_ENV

    def resolve_api_key(self) -> str:
        api_key = self.api_key or os.getenv(self.api_key_env)
        if not api_key:
            raise ValueError(
                f"Doubao search API key is missing. Set {self.api_key_env} "
                "or pass api_key directly."
            )
        return api_key


@dataclass(slots=True)
class DoubaoWebResult:
    """One web search result returned by Doubao Search."""

    id: str
    sort_id: int | None = None
    title: str = ""
    site_name: str = ""
    url: str = ""
    snippet: str = ""
    summary: str = ""
    content: str = ""
    publish_time: str = ""
    logo_url: str = ""
    rank_score: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, payload: Mapping[str, Any]) -> DoubaoWebResult:
        return cls(
            id=str(payload.get("Id", "")),
            sort_id=payload.get("SortId"),
            title=str(payload.get("Title", "")),
            site_name=str(payload.get("SiteName", "")),
            url=str(payload.get("Url", "")),
            snippet=str(payload.get("Snippet", "")),
            summary=str(payload.get("Summary", "")),
            content=str(payload.get("Content", "")),
            publish_time=str(payload.get("PublishTime", "")),
            logo_url=str(payload.get("LogoUrl", "")),
            rank_score=payload.get("RankScore"),
            raw=dict(payload),
        )


@dataclass(slots=True)
class DoubaoSearchResponse:
    """Normalized Doubao Search response."""

    query: str
    search_type: str
    result_count: int
    web_results: list[DoubaoWebResult] = field(default_factory=list)
    search_context: dict[str, Any] = field(default_factory=dict)
    time_cost_ms: int | None = None
    log_id: str = ""
    request_id: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, payload: Mapping[str, Any]) -> DoubaoSearchResponse:
        result = payload.get("Result") or {}
        if not isinstance(result, Mapping):
            result = {}
        metadata = payload.get("ResponseMetadata") or {}
        if not isinstance(metadata, Mapping):
            metadata = {}
        search_context = result.get("SearchContext") or {}
        if not isinstance(search_context, Mapping):
            search_context = {}

        web_results = [
            DoubaoWebResult.from_api(item)
            for item in result.get("WebResults") or []
            if isinstance(item, Mapping)
        ]
        return cls(
            query=str(search_context.get("OriginQuery", "")),
            search_type=str(search_context.get("SearchType", "")),
            result_count=int(result.get("ResultCount") or len(web_results)),
            web_results=web_results,
            search_context=dict(search_context),
            time_cost_ms=result.get("TimeCost"),
            log_id=str(result.get("LogId", "")),
            request_id=str(metadata.get("RequestId", "")),
            raw=dict(payload),
        )


class DoubaoSearchClient:
    """Client for Doubao Search Custom API using API Key authentication."""

    def __init__(
        self,
        config: DoubaoSearchConfig | None = None,
        *,
        transport: HttpTransport | None = None,
    ) -> None:
        self._config = config or DoubaoSearchConfig()
        self._transport = transport or self._urlopen_transport

    def web_search(
        self,
        query: str,
        *,
        count: int = 10,
        need_content: bool | None = None,
        need_url: bool | None = None,
        sites: list[str] | str | None = None,
        block_hosts: list[str] | str | None = None,
        auth_info_level: int | None = None,
        time_range: str | None = None,
        query_rewrite: bool | None = None,
        content_format: str | None = None,
        industry: str | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> DoubaoSearchResponse:
        """Search web pages with Doubao Search.

        Args follow the Volcengine Custom Search request schema. The default
        search type is ``web``; image search can be added later in this module.
        """

        request_payload = self._build_web_payload(
            query=query,
            count=count,
            need_content=need_content,
            need_url=need_url,
            sites=sites,
            block_hosts=block_hosts,
            auth_info_level=auth_info_level,
            time_range=time_range,
            query_rewrite=query_rewrite,
            content_format=content_format,
            industry=industry,
            extra=extra,
        )
        response_payload = self._post_json(request_payload)
        return DoubaoSearchResponse.from_api(response_payload)

    def _build_web_payload(
        self,
        *,
        query: str,
        count: int,
        need_content: bool | None,
        need_url: bool | None,
        sites: list[str] | str | None,
        block_hosts: list[str] | str | None,
        auth_info_level: int | None,
        time_range: str | None,
        query_rewrite: bool | None,
        content_format: str | None,
        industry: str | None,
        extra: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        if not query or not query.strip():
            raise ValueError("query cannot be empty.")
        if count < 1 or count > 50:
            raise ValueError("count must be between 1 and 50 for web search.")

        payload: dict[str, Any] = {
            "Query": query.strip(),
            "SearchType": "web",
            "Count": count,
        }
        filters: dict[str, Any] = {}
        if need_content is not None:
            filters["NeedContent"] = need_content
        if need_url is not None:
            filters["NeedUrl"] = need_url
        if sites:
            filters["Sites"] = self._join_hosts(sites)
        if block_hosts:
            filters["BlockHosts"] = self._join_hosts(block_hosts)
        if auth_info_level is not None:
            filters["AuthInfoLevel"] = auth_info_level
        if filters:
            payload["Filter"] = filters
        if time_range:
            payload["TimeRange"] = time_range
        if query_rewrite is not None:
            payload["QueryControl"] = {"QueryRewrite": query_rewrite}
        if content_format:
            payload["ContentFormats"] = content_format
        if industry:
            payload["Industry"] = industry
        if extra:
            payload.update(extra)
        return payload

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        api_key = self._config.resolve_api_key()
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        status_code, _, body = self._transport(
            self._config.endpoint,
            payload,
            headers,
            self._config.timeout,
        )
        try:
            data = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise DoubaoSearchError(
                "Doubao search returned invalid JSON.",
                status_code=status_code,
            ) from exc
        if not isinstance(data, dict):
            raise DoubaoSearchError(
                "Doubao search returned an unexpected response shape.",
                status_code=status_code,
            )

        error = self._extract_error(data)
        if status_code >= 400 or error:
            message = error.get("Message") or f"Doubao search failed with HTTP {status_code}."
            raise DoubaoSearchError(
                str(message),
                status_code=status_code,
                response=data,
            )
        return data

    @staticmethod
    def _urlopen_transport(
        endpoint: str,
        payload: dict[str, Any],
        headers: Mapping[str, str],
        timeout: float,
    ) -> tuple[int, Mapping[str, str], bytes]:
        request = Request(
            endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=dict(headers),
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.status, dict(response.headers), response.read()
        except HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()
        except URLError as exc:
            raise DoubaoSearchError(f"Doubao search request failed: {exc}") from exc

    @staticmethod
    def _extract_error(payload: Mapping[str, Any]) -> dict[str, Any]:
        metadata = payload.get("ResponseMetadata") or {}
        if not isinstance(metadata, Mapping):
            return {}
        error = metadata.get("Error") or {}
        return dict(error) if isinstance(error, Mapping) else {}

    @staticmethod
    def _join_hosts(hosts: list[str] | str) -> str:
        if isinstance(hosts, str):
            return hosts
        return "|".join(host.strip() for host in hosts if host.strip())


def doubao_ai_search(
    query: str,
    *,
    api_key: str | None = None,
    count: int = 10,
    **kwargs: Any,
) -> DoubaoSearchResponse:
    """Convenience function for one-off Doubao web searches."""

    client = DoubaoSearchClient(DoubaoSearchConfig(api_key=api_key))
    return client.web_search(query, count=count, **kwargs)
