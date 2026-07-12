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

    @model_validator(mode="before")
    @classmethod
    def _validate_subgraph(cls, data: Any) -> Any:
        import re

        if not isinstance(data, dict):
            return data
        allowed = {"name", "path", "description"}
        for k in data:
            if k not in allowed:
                raise ValueError(f"[F-v3-agent-subgraph-invalid] Extra field {k!r} not allowed in subgraph spec")
        name = data.get("name")
        if name is None or not isinstance(name, str) or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
            raise ValueError("[F-v3-agent-subgraph-invalid] Subgraph name is missing or invalid")
        path = data.get("path")
        if path is None or not isinstance(path, str) or len(path) == 0:
            raise ValueError("[F-v3-agent-subgraph-invalid] Subgraph path is missing or invalid")
        description = data.get("description")
        if description is None or not isinstance(description, str) or len(description) == 0:
            raise ValueError("[F-v3-agent-subgraph-invalid] Subgraph description is missing or invalid")
        return data


class ReferenceSpec(BaseModel):
    """Reference resource declared on an Agent."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Z][A-Za-z0-9_-]*$")
    path: str = Field(min_length=1)
    summary: str = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _validate_reference(cls, data: Any) -> Any:
        import re

        if not isinstance(data, dict):
            return data
        allowed = {"id", "path", "summary"}
        for k in data:
            if k not in allowed:
                raise ValueError(f"[F-v3-resource-reference-invalid] Extra field {k!r} not allowed in reference spec")
        val_id = data.get("id")
        if val_id is None or not isinstance(val_id, str) or not re.match(r"^[A-Z][A-Za-z0-9_-]*$", val_id):
            raise ValueError("[F-v3-resource-reference-id-invalid] Reference id is missing or invalid")
        path = data.get("path")
        if path is None or not isinstance(path, str) or len(path) == 0:
            raise ValueError("[F-v3-resource-reference-invalid] Reference path is missing or invalid")
        summary = data.get("summary")
        if summary is None or not isinstance(summary, str) or len(summary) == 0:
            raise ValueError("[F-v3-resource-reference-summary-missing] Reference summary is missing or invalid")
        return data


class ExampleSpec(BaseModel):
    """Document example declared on an Agent frontmatter."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Z][A-Za-z0-9_-]*$")
    path: str = Field(min_length=1)
    summary: str = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _validate_example(cls, data: Any) -> Any:
        import re

        if not isinstance(data, dict):
            return data
        allowed = {"id", "path", "summary"}
        for k in data:
            if k not in allowed:
                raise ValueError(f"[F-v3-resource-example-invalid] Extra field {k!r} not allowed in example spec")
        val_id = data.get("id")
        if val_id is None or not isinstance(val_id, str) or not re.match(r"^[A-Z][A-Za-z0-9_-]*$", val_id):
            raise ValueError("[F-v3-resource-example-id-invalid] Example id is missing or invalid")
        path = data.get("path")
        if path is None or not isinstance(path, str) or len(path) == 0:
            raise ValueError("[F-v3-resource-example-path-missing] Example path is missing or invalid")
        summary = data.get("summary")
        if summary is None or not isinstance(summary, str) or len(summary) == 0:
            raise ValueError("[F-v3-resource-example-summary-missing] Example summary is missing or invalid")
        return data


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
    # Whole-graph default LLM role; agent phases inherit it unless they set
    # their own llm_role (skill-spec 00-FORMAT-GROUND-TRUTH §2).
    llm_role: str | None = None
    io: PhaseIOSchema
    phases: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    iterate: IterateSpec | None = None

    @field_validator("name", mode="before")
    @classmethod
    def _validate_name(cls, value: Any) -> Any:
        if value is not None:
            val_str = str(value)
            if len(val_str) == 0 or len(val_str) > 128:
                raise ValueError("[F-v3-graph-name-invalid] Graph name must be between 1 and 128 characters")
        return value


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
    io: PhaseIOSchema
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

    @field_validator("max_iterations", mode="before")
    @classmethod
    def _validate_max_iterations(cls, value: Any) -> Any:
        if value is not None:
            try:
                val = int(value)
                if not (1 <= val <= 50):
                    raise ValueError("[F-v3-agent-max-iterations-invalid] max_iterations must be between 1 and 50")
            except (ValueError, TypeError) as err:
                raise ValueError("[F-v3-agent-max-iterations-invalid] max_iterations must be an integer") from err
        return value

    # Priority switch: true makes the graph-level default llm_role win over
    # this node's own llm_role, WITHOUT rewriting/erasing the node value
    # (skill-spec 00-FORMAT-GROUND-TRUTH §5).
    use_graph_llm_role: bool = False
    system_prompt: str = ""

    @model_validator(mode="after")
    def _render_legacy_system_prompt(self) -> AgentNodeAST:
        if not self.system_prompt:
            step_lines = "\n".join(f"- {step.name}: {step.content}" for step in self.steps)
            protocol_lines = "\n".join(f"- {protocol.id}: {protocol.content}" for protocol in self.protocols)
            parts = [f"Role: {self.role}", f"Goal: {self.goal}"]
            if step_lines:
                parts.append("Steps:\n" + step_lines)
            if protocol_lines:
                parts.append("Protocols:\n" + protocol_lines)
            self.system_prompt = "\n\n".join(parts)
        return self


# Conventional fallback role looked up in the host's role registry when
# neither the node nor the graph names one (skill-spec 00-FORMAT-GROUND-TRUTH).
DEFAULT_LLM_ROLE = "graph_agent"


def effective_llm_role(phase_ast: AgentNodeAST, graph_llm_role: str | None) -> str:
    """Resolve the role an agent phase actually runs as.

    ``use_graph_llm_role`` on -> the graph-level default wins (the node's own
    ``llm_role`` stays in the file but is inactive). Off -> the node's own
    value wins, inheriting the graph default when the node has none. When
    neither names a role, fall back to ``DEFAULT_LLM_ROLE``.
    """
    if phase_ast.use_graph_llm_role:
        return graph_llm_role or DEFAULT_LLM_ROLE
    return phase_ast.llm_role or graph_llm_role or DEFAULT_LLM_ROLE


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
