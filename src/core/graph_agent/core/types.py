"""Shared lightweight types for GraphAgent orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
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
    # Logical model role resolved from llm_roles.yaml, mapped from the
    # manifest's ``llm_role`` field. ``tier`` remains for compatibility.
    llm_role: str | None = None
    # Task 6.1: when a phase wants to bypass the tier → role → model
    # resolution and pin itself to a specific registered model (for A/B
    # experiments or a single-model-role phase), it sets
    # ``model_override`` to a code from llm_roles.yaml's ``models:``
    # section. The resolver reads this **before** falling back to tier.
    model_override: str | None = None
    validator: Callable[..., tuple[bool, list[str]]] | None = None
    retry_target: str | None = None
    max_retries: int = 3
    user_prompt_template: str | None = None
    requires_llm: bool = True
    # Task 6.5: nudge budget default drops from 3 to 1 — the cognitive
    # guardrails are already strong, and three rounds of nudges per phase
    # was accumulating far more latency than it recovered in practice.
    # Skills that genuinely need the old behaviour can set
    # ``max_nudges: 3`` in their phase_config.
    max_nudges: int = 1
    dead_end_threshold: int = 3
    data_architecture: str | None = None
    subagent_enabled: bool = False
    subgraph: GraphAgentHarness | None = None
    context_bridge: ContextBridge | None = None
    references: list[str] = field(default_factory=list)
    skill_base_dir: Path | None = None
    # Opt-in mining permissions resolved from manifest.context_access.
    context_access: list[str] = field(default_factory=list)
    output_schema: type[BaseModel] | None = None
    output_schema_path: str | None = None
    md_type_dict: str | None = None


__all__ = ["ContextBridge", "Phase"]
