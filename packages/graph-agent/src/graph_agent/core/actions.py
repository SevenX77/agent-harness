"""V2.1 Action and Tool registries."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from graph_agent.core.exceptions import GraphAgentFatalError


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
    def empty(cls) -> ActionRegistry:
        return cls({})

    def resolve(self, phase_id: str, name: str) -> Callable[..., object]:
        _validate_action_name(name)
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
    description: str | None = None
    args_schema: type[BaseModel] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolRegistry:
    root_tools: list[ToolDef] = field(default_factory=list)
    by_phase: dict[str, list[ToolDef]] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> ToolRegistry:
        return cls()

    def for_root(self) -> list[StructuredTool]:
        return [_structured_tool(tool) for tool in self.root_tools]

    def for_phase(self, phase_id: str) -> list[StructuredTool]:
        tools = [*self.root_tools, *self.by_phase.get(phase_id, [])]
        return [_structured_tool(tool) for tool in tools]


def _structured_tool(tool: ToolDef) -> StructuredTool:
    description = tool.description or inspect.getdoc(tool.func) or f"Tool: {tool.id}"
    return StructuredTool.from_function(
        func=tool.func,
        name=tool.id,
        description=description,
        args_schema=tool.args_schema,
        metadata=tool.metadata or None,
    )


def _validate_action_name(name: str) -> None:
    if (
        not isinstance(name, str)
        or not name
        or "/" in name
        or "\\" in name
        or "." in name
        or Path(name).is_absolute()
    ):
        raise GraphAgentFatalError(f"[F-v3-logic-action-name-invalid] invalid action name {name!r}")


__all__ = ["ActionDef", "ActionRegistry", "ToolDef", "ToolRegistry"]
