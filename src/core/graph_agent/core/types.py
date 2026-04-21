"""Shared lightweight types for GraphAgent orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from .harness import GraphAgentHarness


@dataclass
class ContextBridge:
    """Declarative context mapping between parent and child skills.

    - inputs: parent context key -> child runtime input name
    - outputs: child context key -> parent context key
    """

    inputs: dict[str, str] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)


@dataclass
class Phase:
    """A single work phase in a multi-phase workflow."""

    name: str
    system_prompt: str | None = None
    tools: list[Callable[..., str]] = field(default_factory=list)
    max_iterations: int = 20
    max_tool_calls: int = 0
    tier: str = "balanced"
    validator: Callable[..., tuple[bool, list[str]]] | None = None
    retry_target: str | None = None
    max_retries: int = 3
    user_prompt_template: str | None = None
    requires_llm: bool = True
    max_nudges: int = 3
    dead_end_threshold: int = 3
    data_architecture: str | None = None
    subagent_enabled: bool = False
    subgraph: GraphAgentHarness | None = None
    context_bridge: ContextBridge | None = None
    output_schema: type[BaseModel] | None = None
    output_schema_path: str | None = None
    md_type_dict: str | None = None


__all__ = ["ContextBridge", "Phase"]
