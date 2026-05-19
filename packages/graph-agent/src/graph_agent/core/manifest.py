"""Pydantic v2.1 manifest and phase-node AST contracts.

V2.1 is a hard cut from schema 2.0.  The root ``GRAPH.md`` is the graph
manifest and never becomes a runtime node.  Phase nodes live under
``phases/*/{LOGIC,SUBGRAPH,SKILL}.md`` and are routed by physical file
name plus the YAML ``mode`` discriminator.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class GraphPhaseRef(BaseModel):
    """One phase reference declared in root ``GRAPH.md``."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    src: str = Field(min_length=1)
    depends_on: list[str] = Field(...)


class ContextBridge(BaseModel):
    """Subgraph boundary mapping placeholder retained for runtime dataclasses."""

    model_config = ConfigDict(extra="forbid")

    inputs: dict[str, str] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)


class SubagentSpec(BaseModel):
    """Sub-skill declared as a callable tool on a SKILL phase."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    path: str = Field(min_length=1)
    description: str = Field(min_length=1)


class GraphManifest(BaseModel):
    """Root V2.1 graph manifest parsed from ``GRAPH.md``."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["2.1"] = "2.1"
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    io_inputs_ref: str = "io/inputs.json"
    io_outputs_ref: str = "io/outputs.json"
    phases: list[GraphPhaseRef] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class _BaseNodeAST(BaseModel):
    """Fields shared by all V2.1 phase node AST variants."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    raw_blocks: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LogicNodeAST(_BaseNodeAST):
    """Deterministic Python phase node parsed from ``LOGIC.md``."""

    mode: Literal["logic"]
    python_callable: str = Field(min_length=1)


class SubgraphNodeAST(_BaseNodeAST):
    """Subgraph delegation phase node parsed from ``SUBGRAPH.md``."""

    mode: Literal["subgraph"]
    sub_skill_ref: str = Field(min_length=1)


class SkillNodeAST(_BaseNodeAST):
    """LLM ReAct phase node parsed from ``SKILL.md``."""

    mode: Literal["skill"]
    system_prompt: str = Field(min_length=1)
    exit_contract: str = Field(min_length=1)
    tools: list[str] = Field(default_factory=list)
    subagents: list[SubagentSpec] = Field(default_factory=list)


PhaseAST = Annotated[
    LogicNodeAST | SubgraphNodeAST | SkillNodeAST,
    Field(discriminator="mode"),
]


# Transitional public name for package imports.  This is not the old
# schema-2.0 discriminated union; it aliases the V2.1 root manifest only.
SkillManifest = GraphManifest


__all__ = [
    "ContextBridge",
    "GraphManifest",
    "GraphPhaseRef",
    "LogicNodeAST",
    "PhaseAST",
    "SkillManifest",
    "SkillNodeAST",
    "SubagentSpec",
    "SubgraphNodeAST",
]
