"""Interfaces for hot news providers.

The concrete provider is intentionally left replaceable. The default provider
returns no items so the background pipeline can be wired before a real hot news
API is available.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
import os
import re
from typing import Any, Callable, Protocol


WEIBO_HOT_BASE_URL = "https://s.weibo.com"
WEIBO_HOT_ENDPOINT = f"{WEIBO_HOT_BASE_URL}/top/summary?cate=realtimehot"
DEFAULT_WEIBO_HOT_COOKIE = (
    "SUB=_2AkMWIuNSf8NxqwJRmP8dy2rhaoV2ygrEieKgfhKJJRMxHRl-yT9jqk86tRB6PaLNvQZR6zYUcYVT1zSjoSreQHidcUq7"
)


@dataclass(slots=True)
class HotNewsItem:
    """One raw hot-news item fetched from an external provider."""

    title: str
    summary: str = ""
    url: str = ""
    source: str = ""
    rank: int | None = None
    heat: float | None = None
    published_at: datetime | None = None
    captured_at: datetime | None = None
    category: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


class HotNewsProvider(Protocol):
    """Boundary implemented by user-owned hot news integrations."""

    def fetch_hot_news(self) -> list[HotNewsItem]:
        """Fetch today's hot news items."""


class EmptyHotNewsProvider:
    """Safe placeholder used until a real provider is injected."""

    def fetch_hot_news(self) -> list[HotNewsItem]:
        return []



def create_hot_news_provider(name: str = "default", **kwargs: Any) -> HotNewsProvider:
    """Create a hot-news provider by stable provider name."""

    provider_name = str(name or "default").strip().lower()
    if provider_name in {"", "default", "empty"}:
        return EmptyHotNewsProvider()
    if provider_name == "weibo":
        return WeiboHotNewsProvider(**kwargs)
    raise ValueError(f"Unsupported hot news provider: {name}")


class WeiboHotNewsProvider:
    """Fetch realtime hot-search items from Weibo."""

    def __init__(
        self,
        *,
        limit: int = 20,
        weight: float = 0.9,
        cookie: str = "",
        timeout: float = 10,
        transport: Callable[..., Any] | None = None,
    ) -> None:
        self.limit = limit
        self.weight = weight
        self.cookie = cookie or DEFAULT_WEIBO_HOT_COOKIE
        self.timeout = timeout
        self._transport = transport
        self.last_error = ""

    def fetch_hot_news(self) -> list[HotNewsItem]:
        """Fetch Weibo realtime hot-search items."""

        try:
            self.last_error = ""
            response = self._get_response()
            response.raise_for_status()
            html = self._response_text(response)
            if self._is_visitor_system_page(html):
                self.last_error = (
                    "Weibo returned Sina Visitor System instead of realtime hot data. "
                    "Set WEIBO_HOT_COOKIE or pass a valid cookie to WeiboHotNewsProvider."
                )
                return []
            records = self._parse_records(html)
            items: list[HotNewsItem] = []

            for index, record in enumerate(records):
                title = record["title"]
                href = record["href"]
                if not title or not href:
                    continue

                flag = record["flag"]
                flag_url = self._flag_url(flag)
                item_weight = round(self.weight * (self.limit - index), 2)
                url = self._absolute_url(href)
                raw: dict[str, Any] = {
                    "id": title,
                    "title": title,
                    "url": url,
                    "mobileUrl": url,
                    "extra": {},
                    "weight": item_weight,
                    "flag": flag,
                }
                if flag_url:
                    raw["extra"]["icon"] = {
                        "url": flag_url,
                        "scale": 1.5,
                    }

                items.append(
                    HotNewsItem(
                        title=title,
                        url=url,
                        source="weibo",
                        rank=index + 1,
                        heat=item_weight,
                        category="微博热搜",
                        raw=raw,
                    )
                )
                if len(items) >= self.limit:
                    break
            return items
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            return []

    def _get_response(self) -> Any:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/119.0.0.0 Safari/537.36"
            ),
            "Cookie": self.cookie,
            "referer": WEIBO_HOT_ENDPOINT,
        }
        if self._transport is None:
            import requests

            transport = requests.get
        else:
            transport = self._transport
        return transport(WEIBO_HOT_ENDPOINT, headers=headers, timeout=self.timeout)

    @staticmethod
    def _response_text(response: Any) -> str:
        """Decode response bytes defensively.

        Weibo pages may be served without a useful charset header, causing
        requests to expose mojibake through response.text. Prefer decoding the
        original bytes and choose the candidate that looks most like Chinese
        HTML.
        """

        content = getattr(response, "content", None)
        if not content:
            return str(getattr(response, "text", "") or "")
        if isinstance(content, str):
            return content

        header_encoding = WeiboHotNewsProvider._header_encoding(response)
        apparent_encoding = str(getattr(response, "apparent_encoding", "") or "").strip()
        response_encoding = str(getattr(response, "encoding", "") or "").strip()
        encodings = [
            header_encoding,
            response_encoding if response_encoding.lower() not in {"iso-8859-1", "latin-1"} else "",
            apparent_encoding,
            "utf-8",
            "gb18030",
        ]

        candidates: list[str] = []
        for encoding in encodings:
            if not encoding:
                continue
            try:
                candidates.append(content.decode(encoding, errors="replace"))
            except (LookupError, UnicodeDecodeError):
                continue
        text = str(getattr(response, "text", "") or "")
        if text:
            candidates.append(text)
        if not candidates:
            return content.decode("utf-8", errors="replace")
        return max(candidates, key=WeiboHotNewsProvider._decoded_text_score)

    @staticmethod
    def _header_encoding(response: Any) -> str:
        headers = getattr(response, "headers", {}) or {}
        content_type = ""
        if isinstance(headers, dict):
            content_type = str(headers.get("content-type") or headers.get("Content-Type") or "")
        match = re.search(r"charset=([\w.-]+)", content_type, flags=re.IGNORECASE)
        return match.group(1) if match else ""

    @staticmethod
    def _decoded_text_score(text: str) -> int:
        cjk_count = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
        structure_score = 100 if "pl_top_realtimehot" in text else 0
        replacement_penalty = text.count("\ufffd") * 20
        mojibake_penalty = text.count("Ã") * 10 + text.count("Â") * 10 + text.count("æ") * 5
        return structure_score + cjk_count - replacement_penalty - mojibake_penalty

    @staticmethod
    def _is_visitor_system_page(html: str) -> bool:
        lowered = html.lower()
        return (
            "sina visitor system" in lowered
            or "/visitor/genvisitor" in lowered
            or "passport.weibo.com/sso" in lowered
            or "passport.sinaimg.cn/js/fp" in lowered
        )

    def _parse_records(self, html: str) -> list[dict[str, str]]:
        try:
            return self._parse_records_with_bs4(html)
        except ModuleNotFoundError:
            return self._parse_records_with_stdlib(html)

    @staticmethod
    def _parse_records_with_bs4(html: str) -> list[dict[str, str]]:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("#pl_top_realtimehot table tbody tr")[1:]
        records: list[dict[str, str]] = []
        for row in rows:
            valid_link = WeiboHotNewsProvider._valid_link(row)
            if valid_link is None:
                continue
            title = valid_link.get_text(strip=True)
            href = valid_link.get("href")
            if not title or not href:
                continue
            records.append(
                {
                    "title": title,
                    "href": str(href),
                    "flag": WeiboHotNewsProvider._row_flag(row),
                }
            )
        return records

    @staticmethod
    def _parse_records_with_stdlib(html: str) -> list[dict[str, str]]:
        parser = _WeiboHotHTMLParser()
        parser.feed(html)
        return parser.records

    @staticmethod
    def _valid_link(row: Any) -> Any | None:
        for link in row.select("td.td-02 a"):
            href = link.get("href")
            if href and "javascript:void(0);" not in href:
                return link
        return None

    @staticmethod
    def _row_flag(row: Any) -> str:
        flag_cell = row.select_one("td.td-03")
        return flag_cell.get_text(strip=True) if flag_cell else ""

    @staticmethod
    def _flag_url(flag: str) -> str | None:
        flag_url_map = {
            "新": "https://simg.s.weibo.com/moter/flags/1_0.png",
            "热": "https://simg.s.weibo.com/moter/flags/2_0.png",
            "爆": "https://simg.s.weibo.com/moter/flags/4_0.png",
        }
        return flag_url_map.get(flag)

    @staticmethod
    def _absolute_url(href: str) -> str:
        if href.startswith("http://") or href.startswith("https://"):
            return href
        return f"{WEIBO_HOT_BASE_URL}{href}"


class _WeiboHotHTMLParser(HTMLParser):
    """Small fallback parser for Weibo hot-search table rows."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[dict[str, str]] = []
        self._in_hot_root = False
        self._root_depth = 0
        self._in_row = False
        self._cell_class = ""
        self._links: list[dict[str, str]] = []
        self._flag_parts: list[str] = []
        self._current_href = ""
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: value or "" for key, value in attrs}
        if tag == "div" and attrs_dict.get("id") == "pl_top_realtimehot":
            self._in_hot_root = True
            self._root_depth = 1
            return
        if not self._in_hot_root:
            return
        self._root_depth += 1
        if tag == "tr":
            self._in_row = True
            self._links = []
            self._flag_parts = []
            return
        if not self._in_row:
            return
        if tag == "td":
            self._cell_class = attrs_dict.get("class", "")
            return
        if tag == "a" and self._has_cell_class("td-02"):
            self._current_href = attrs_dict.get("href", "")
            self._text_parts = []

    def handle_endtag(self, tag: str) -> None:
        if not self._in_hot_root:
            return
        if tag == "a" and self._in_row and self._has_cell_class("td-02"):
            text = "".join(self._text_parts).strip()
            if self._current_href and text:
                self._links.append({"href": self._current_href, "title": text})
            self._current_href = ""
            self._text_parts = []
        elif tag == "td":
            self._cell_class = ""
        elif tag == "tr" and self._in_row:
            self._finish_row()
        self._root_depth -= 1
        if self._root_depth <= 0:
            self._in_hot_root = False

    def handle_data(self, data: str) -> None:
        if not self._in_hot_root or not self._in_row:
            return
        if self._has_cell_class("td-02") and self._current_href:
            self._text_parts.append(data)
        elif self._has_cell_class("td-03"):
            self._flag_parts.append(data)

    def _finish_row(self) -> None:
        self._in_row = False
        valid_link = None
        for link in self._links:
            href = link["href"]
            if href and "javascript:void(0);" not in href:
                valid_link = link
                break
        if valid_link is None:
            return
        self.records.append(
            {
                "title": valid_link["title"],
                "href": valid_link["href"],
                "flag": "".join(self._flag_parts).strip(),
            }
        )

    def _has_cell_class(self, class_name: str) -> bool:
        return class_name in self._cell_class.split()
