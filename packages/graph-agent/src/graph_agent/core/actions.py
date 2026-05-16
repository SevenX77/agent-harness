"""V2.1 Action and Tool registries."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from langchain_core.tools import StructuredTool


@dataclass(frozen=True)
class ActionDef:
    id: str
    phase_id: str
    path: Path
    func: Callable[..., object]


class ActionRegistry:
    def __init__(self, by_phase: dict[str, dict[str, ActionDef]] | None = None) -> None:
        self._by_phase = by_phase or {}

    @classmethod
    def empty(cls) -> "ActionRegistry":
        return cls({})

    def resolve(self, phase_id: str, name: str) -> Callable[..., object]:
        try:
            phase_actions = self._by_phase[phase_id]
        except KeyError as exc:
            raise KeyError(f"unknown phase_id {phase_id!r}") from exc
        try:
            return phase_actions[name].func
        except KeyError as exc:
            raise KeyError(f"unknown action {name!r} in phase {phase_id!r}") from exc

    def for_phase(self, phase_id: str) -> dict[str, ActionDef]:
        return dict(self._by_phase.get(phase_id, {}))


@dataclass(frozen=True)
class ToolDef:
    id: str
    phase_id: str | None
    path: Path
    func: Callable[..., object]


@dataclass(frozen=True)
class ToolRegistry:
    root_tools: list[ToolDef] = field(default_factory=list)
    by_phase: dict[str, list[ToolDef]] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> "ToolRegistry":
        return cls()

    def for_root(self) -> list[StructuredTool]:
        return [_structured_tool(tool) for tool in self.root_tools]

    def for_phase(self, phase_id: str) -> list[StructuredTool]:
        tools = [*self.root_tools, *self.by_phase.get(phase_id, [])]
        return [_structured_tool(tool) for tool in tools]


def _structured_tool(tool: ToolDef) -> StructuredTool:
    description = inspect.getdoc(tool.func) or f"Tool: {tool.id}"
    return StructuredTool.from_function(func=tool.func, name=tool.id, description=description)


__all__ = ["ActionDef", "ActionRegistry", "ToolDef", "ToolRegistry"]
