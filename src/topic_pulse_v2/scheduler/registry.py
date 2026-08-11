"""Registry for scheduler task callables."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


TaskCallable = Callable[..., Any]


@dataclass(slots=True)
class ScheduledTask:
    name: str
    handler: TaskCallable
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class ScheduledTaskRegistry:
    """In-memory mapping from task names to executable callables."""

    def __init__(self) -> None:
        self._tasks: dict[str, ScheduledTask] = {}

    def register(
        self,
        name: str,
        handler: TaskCallable,
        *,
        description: str = "",
        metadata: dict[str, Any] | None = None,
        replace: bool = False,
    ) -> ScheduledTask:
        if not name:
            raise ValueError("Task name cannot be empty.")
        if name in self._tasks and not replace:
            raise ValueError(f"Task already registered: {name}")
        task = ScheduledTask(
            name=name,
            handler=handler,
            description=description,
            metadata=metadata or {},
        )
        self._tasks[name] = task
        return task

    def get(self, name: str) -> ScheduledTask:
        try:
            return self._tasks[name]
        except KeyError as exc:
            raise LookupError(f"Scheduled task not found: {name}") from exc

    def has(self, name: str) -> bool:
        return name in self._tasks

    def list(self) -> list[ScheduledTask]:
        return [self._tasks[name] for name in sorted(self._tasks)]
