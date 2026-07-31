"""Tool registration types."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

ToolHandler = Callable[..., Any]


@dataclass(slots=True)
class ToolSpec:
    """Metadata and callable for a registered tool."""

    name: str
    handler: ToolHandler
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    tags: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "tags": sorted(self.tags),
            "metadata": self.metadata,
        }
