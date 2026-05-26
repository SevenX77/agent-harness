"""Pydantic v2.1 manifest and phase-node AST contracts.

V2.1 is a hard cut from schema 2.0.  The root ``GRAPH.md`` is the graph
manifest and never becomes a runtime node.  Phase nodes live under
``phases/*/{LOGIC,SUBGRAPH,SKILL}.md`` and are routed by physical file
name plus the YAML ``mode`` discriminator.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from graph_agent.core.skill_resolver_protocol import SKILL_ID_PATTERN


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


class PhaseIOSchema(BaseModel):
    """Inline JSON Schema contract for a graph or phase boundary."""

    model_config = ConfigDict(extra="forbid")

    inputs: dict[str, Any] = Field(..., min_length=1)
    outputs: dict[str, Any] = Field(..., min_length=1)


class AgentRegistryItem(BaseModel):
    """Named registry binding available to an Agent body."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    target_skill: str = Field(pattern=SKILL_ID_PATTERN)
    description: str = Field(min_length=1)


class ReferenceSpec(BaseModel):
    """Reference resource declared on an Agent."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Z][A-Za-z0-9_-]*$")
    path: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class ExampleSpec(BaseModel):
    """Inline or document example declared on an Agent."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Z][A-Za-z0-9_-]*$")
    type: Literal["inline", "document"]
    content: str | None = None
    path: str | None = None
    summary: str | None = None


class AgentStep(BaseModel):
    """One ordered Agent step parsed from body XML."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    name: str = Field(min_length=1)
    content: str = Field(min_length=1)


class AgentProtocol(BaseModel):
    """One Agent protocol parsed from body XML."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    content: str = Field(min_length=1)


class SubagentSpec(BaseModel):
    """Sub-skill declared as a callable tool on a SKILL phase."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    target_skill: str = Field(pattern=SKILL_ID_PATTERN)
    description: str = Field(min_length=1)


class GraphManifest(BaseModel):
    """Root V2.1 graph manifest parsed from ``GRAPH.md``."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.3.0", "2.1"] = "2.1"
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    io_inputs_ref: str = "io/inputs.json"
    io_outputs_ref: str = "io/outputs.json"
    io: PhaseIOSchema | None = None
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
    target_skill: str = Field(pattern=SKILL_ID_PATTERN)
    io: PhaseIOSchema | None = None
    # V0.3 AST bool flag; not the legacy LLMPhase.validator module path.
    validator: bool = False


class AgentNodeAST(_BaseNodeAST):
    """V0.3.0 Agent phase node parsed from ``SKILL.md``."""

    mode: Literal["agent"]
    role: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    steps: list[AgentStep] = Field(default_factory=list)
    protocols: list[AgentProtocol] = Field(default_factory=list)
    io: PhaseIOSchema | None = None
    # V0.3 AST bool flag; not the legacy LLMPhase.validator module path.
    validator: bool = False
    tools: list[str] = Field(default_factory=list)
    subagents: list[SubagentSpec] = Field(default_factory=list)
    subgraphs: list[AgentRegistryItem] = Field(default_factory=list)
    references: list[ReferenceSpec] = Field(default_factory=list)
    examples: list[ExampleSpec] = Field(default_factory=list)
    max_iterations: int = Field(default=10, ge=1, le=50)
    llm_role: str | None = None
    system_prompt: str = ""

    @model_validator(mode="after")
    def _render_legacy_system_prompt(self) -> AgentNodeAST:
        if not self.system_prompt:
            step_lines = "\n".join(f"- {step.name}: {step.content}" for step in self.steps)
            protocol_lines = "\n".join(
                f"- {protocol.id}: {protocol.content}" for protocol in self.protocols
            )
            parts = [f"Role: {self.role}", f"Goal: {self.goal}"]
            if step_lines:
                parts.append("Steps:\n" + step_lines)
            if protocol_lines:
                parts.append("Protocols:\n" + protocol_lines)
            self.system_prompt = "\n\n".join(parts)
        return self


class SkillNodeAST(_BaseNodeAST):
    """LLM ReAct phase node parsed from ``SKILL.md``."""

    mode: Literal["skill"]
    system_prompt: str = Field(min_length=1)
    exit_contract: str = Field(min_length=1)
    tools: list[str] = Field(default_factory=list)
    subagents: list[SubagentSpec] = Field(default_factory=list)


PhaseAST = Annotated[
    LogicNodeAST | SubgraphNodeAST | AgentNodeAST | SkillNodeAST,
    Field(discriminator="mode"),
]


# Transitional public name for package imports.  This is not the old
# schema-2.0 discriminated union; it aliases the V2.1 root manifest only.
SkillManifest = GraphManifest


__all__ = [
    "ContextBridge",
    "AgentNodeAST",
    "AgentProtocol",
    "AgentRegistryItem",
    "AgentStep",
    "ExampleSpec",
    "GraphManifest",
    "GraphPhaseRef",
    "LogicNodeAST",
    "PhaseAST",
    "PhaseIOSchema",
    "ReferenceSpec",
    "SkillManifest",
    "SkillNodeAST",
    "SubagentSpec",
    "SubgraphNodeAST",
]
