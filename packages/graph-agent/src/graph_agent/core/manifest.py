"""Pydantic v0.3.0 manifest and phase-node AST contracts."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from graph_agent.core.skill_resolver_protocol import SKILL_ID_PATTERN


class GraphPhaseRef(BaseModel):
    """Legacy topology carrier retained for old imports only."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    src: str = Field(min_length=1)
    depends_on: list[str] = Field(...)
    output: bool = False


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
    """Named subgraph binding available to an Agent body."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    path: str = Field(min_length=1)
    description: str = Field(min_length=1)


class ReferenceSpec(BaseModel):
    """Reference resource declared on an Agent."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Z][A-Za-z0-9_-]*$")
    path: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class ExampleSpec(BaseModel):
    """Document example declared on an Agent frontmatter."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Z][A-Za-z0-9_-]*$")
    path: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class AgentExample(BaseModel):
    """One inline Agent example parsed from body XML."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Z][A-Za-z0-9_-]*$")
    content: str = Field(min_length=1)


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


class IterateAccumulateSpec(BaseModel):
    """Declarative loop accumulator spec."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    var: str = Field(min_length=1)
    init: Any
    from_: str = Field(alias="from", min_length=1)
    merge: Literal["append", "extend", "merge", "replace"]


class IterateSpec(BaseModel):
    """Unified MVP1 iterate declaration for graph or phase runtime."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["batch", "loop"]
    over: str = Field(min_length=1)
    item_var: str = Field(min_length=1)
    range: tuple[int, int] | None = None
    concurrency: int = Field(default=1, ge=1)
    accumulate: IterateAccumulateSpec | None = None


class GraphManifest(BaseModel):
    """Root V0.3.0 graph manifest parsed from ``GRAPH.md``."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["v0.3.0"]
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    io: PhaseIOSchema
    phases: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    iterate: IterateSpec | None = None


class BatchSpec(BaseModel):
    """Declarative batch processing spec for a phase."""

    model_config = ConfigDict(extra="forbid")

    iterator: str = Field(min_length=1)
    item_var: str = Field(min_length=1)
    concurrency: int = Field(default=1, ge=1)


class _BaseNodeAST(BaseModel):
    """Fields shared by all V2.1 phase node AST variants."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    raw_blocks: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    allow_sequential_overwrite: list[str] = Field(default_factory=list)
    batch: BatchSpec | None = None
    iterate: IterateSpec | None = None


class LogicNodeAST(_BaseNodeAST):
    """Deterministic Python phase node parsed from ``LOGIC.md``."""

    mode: Literal["logic"]
    io: PhaseIOSchema
    actions: list[str] = Field(default_factory=list, min_length=1)
    validator: StrictBool = False


class SubgraphNodeAST(_BaseNodeAST):
    """Subgraph delegation phase node parsed from ``SUBGRAPH.md``."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    mode: Literal["subgraph"]
    target_skill: str = Field(alias="path", min_length=1)
    io: PhaseIOSchema
    # V0.3 AST bool flag; not the legacy LLMPhase.validator module path.
    validator: StrictBool = False

    @property
    def path(self) -> str:
        return self.target_skill

    @field_validator("target_skill")
    @classmethod
    def _path_not_blank(cls, value: str) -> str:
        # Subgraph path may be relative (resolved against the skill root by the
        # loader) or absolute; the loader enforces that it stays within root.
        if not value.strip():
            raise ValueError("subgraph path must not be blank")
        return value


class AgentNodeAST(_BaseNodeAST):
    """V0.3.0 Agent phase node parsed from ``SKILL.md``."""

    mode: Literal["agent"]
    role: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    steps: list[AgentStep] = Field(default_factory=list)
    protocols: list[AgentProtocol] = Field(default_factory=list)
    io: PhaseIOSchema | None = None
    # V0.3 AST bool flag; not the legacy LLMPhase.validator module path.
    validator: StrictBool = False
    tools: list[str] = Field(default_factory=list)
    subagents: list[SubagentSpec] = Field(default_factory=list)
    subgraphs: list[AgentRegistryItem] = Field(default_factory=list)
    references: list[ReferenceSpec] = Field(default_factory=list)
    examples: list[ExampleSpec] = Field(default_factory=list)
    examples_inline: list[AgentExample] = Field(default_factory=list)
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


PhaseAST = Annotated[
    LogicNodeAST | SubgraphNodeAST | AgentNodeAST,
    Field(discriminator="mode"),
]


# Transitional public name for package imports.  This is not the old
# schema-2.0 discriminated union; it aliases the V2.1 root manifest only.
SkillManifest = GraphManifest


__all__ = [
    "BatchSpec",
    "ContextBridge",
    "AgentNodeAST",
    "AgentExample",
    "AgentProtocol",
    "AgentRegistryItem",
    "AgentStep",
    "ExampleSpec",
    "GraphManifest",
    "GraphPhaseRef",
    "IterateAccumulateSpec",
    "IterateSpec",
    "LogicNodeAST",
    "PhaseAST",
    "PhaseIOSchema",
    "ReferenceSpec",
    "SkillManifest",
    "SubagentSpec",
    "SubgraphNodeAST",
]
