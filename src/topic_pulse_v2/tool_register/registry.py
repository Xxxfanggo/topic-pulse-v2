"""Registry for internal and external tools."""

from __future__ import annotations

from collections.abc import Iterable

from .types import ToolHandler, ToolSpec


class ToolRegistry:
    """In-memory registry for tool metadata and callables."""

    def __init__(self, *, auto_register_local_tools: bool = True) -> None:
        self._tools: dict[str, ToolSpec] = {}
        if auto_register_local_tools:
            self.register_local_tools()

    def register_local_tools(self, *, replace: bool = False) -> None:
        """Register all local tools found in the built-in tools package."""

        from .tools import register_local_tools

        register_local_tools(self, replace=replace)

    def register(
        self,
        name: str,
        handler: ToolHandler,
        *,
        description: str = "",
        parameters: dict | None = None,
        tags: Iterable[str] | None = None,
        metadata: dict | None = None,
        replace: bool = False,
    ) -> ToolSpec:
        if not name:
            raise ValueError("Tool name cannot be empty.")
        if name in self._tools and not replace:
            raise ValueError(f"Tool already registered: {name}")

        spec = ToolSpec(
            name=name,
            handler=handler,
            description=description,
            parameters=parameters or {},
            tags=set(tags or ()),
            metadata=metadata or {},
        )
        self._tools[name] = spec
        return spec

    def unregister(self, name: str) -> None:
        self._tools.pop(name)

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise LookupError(f"Tool not found: {name}") from exc

    def has(self, name: str) -> bool:
        return name in self._tools

    def list(self) -> list[ToolSpec]:
        return [self._tools[name] for name in sorted(self._tools)]

    def search(self, query: str = "", *, tags: Iterable[str] | None = None) -> list[ToolSpec]:
        query_lower = query.lower().strip()
        required_tags = set(tags or ())
        results: list[ToolSpec] = []

        for spec in self.list():
            if required_tags and not required_tags.issubset(spec.tags):
                continue
            haystack = f"{spec.name} {spec.description}".lower()
            if query_lower and query_lower not in haystack:
                continue
            results.append(spec)

        return results

    def as_llm_tools(self) -> list[dict]:
        """Export registered tools in a common JSON-schema-like shape."""

        return [
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                },
            }
            for spec in self.list()
        ]
