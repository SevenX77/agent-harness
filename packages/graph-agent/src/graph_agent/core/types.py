"""Shared lightweight types for GraphAgent orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from graph_agent.core.manifest import ContextBridge

if TYPE_CHECKING:
    from graph_agent.core.io_manager import IODef


@dataclass
class Phase:
    """A single work phase in a multi-phase workflow."""

    name: str
    system_prompt: str | None = None
    tools: list[Callable[..., str]] = field(default_factory=list)
    max_iterations: int = 20
    max_tool_calls: int = 0
    # Runtime field; loader translates manifest's `llm_role` (LLMPhase)
    # or `agent_profile.llm_role` (AgentSkillDef) into this `tier`. Other
    # phase modes (logic / delegate / parallel_delegate) get the default
    # "balanced". The name `tier` is internal-only — schema 2.0 only
    # exposes `llm_role` to authors.
    tier: str = "balanced"
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
    subgraph: Any | None = None
    # Parallel delegate runtime fields (PR-7).
    # Resolved at loader time per Gemini design Q1c: structures stay in
    # memory, the reducer path is dotted-string and imported at execute time
    # (Callable cannot be msgpack-serialised by LangGraph checkpointer).
    parallel_subgraphs: list[Any] = field(default_factory=list)
    reducer_path: str | None = None
    tolerance: float = 0.0
    context_bridge: ContextBridge | None = None
    references: list[str] = field(default_factory=list)
    skill_base_dir: Path | None = None
    # Opt-in mining permissions resolved from manifest.context_access.
    context_access: list[str] = field(default_factory=list)
    output_schema: type[BaseModel] | None = None
    output_schema_path: str | None = None
    md_type_dict: str | None = None
    # MVP-2 T7-bis: declarative io.outputs hoist routing.
    #
    # Currently defaults to no routing; PR-5 owns reconnecting declarative
    # ``io.outputs`` hoist specs from the V0.3 graph manifest. When non-empty
    # the phase executor calls ``IOManager.resolve_hoist`` at phase exit
    # and writes resulting ``io_errors`` into ``state['flow'].io_errors``
    # via ``StateManager.update_framework``. Empty list = no hoist
    # routing requested (legacy phases without declarative io).
    io_specs: list[IODef] = field(default_factory=list)


__all__ = ["Phase"]
