"""Pydantic v2 contract for SKILL.md manifest validation.

Single source of truth that replaces the four independent validation
sites (``core/parser.py``, ``core/loader.py``, ``core/compiler.py``,
``deerflow/skills/parser.py`` — see Studio Phase 0 plan at
``docs/superpowers/plans/2026-04-22-graph-agent-studio.md``).

Scope of *this* module (Task 0.1): define the shape. The integration
with the parsers (Task 0.3) and the reverse-serialisation (Task 0.2)
ship as separate PRs so the diff surface stays reviewable.

Vocabulary decisions
====================

The plan's first draft proposed ``type: graph|code`` and
``target: file|artifact_manager``. Every existing production skill
actually uses ``type: simple`` (not ``code``) and ``target: artifact``
(not ``artifact_manager``). Acceptance criterion for this module ("5
business skills all validate") requires the real vocabulary; the plan's
future-vocabulary proposal is deferred until an explicit migration.

Real phase_config fields (discovered by grep'ing ``skills/*/phases/``)
that the plan missed:

* ``max_iterations`` — agent-loop iteration cap (plan wrote ``max_retries``)
* ``subgraph`` — path to a child SKILL.md for composition
* ``context_bridge`` — input/output wiring for subgraph phases
* ``subagent_enabled`` — toggle for DeerFlow subagent middleware

Plan-originated *new* fields (not in any real skill yet) kept here as
optional so Studio can start writing them without a schema bump:

* ``Step`` entries with ``goal`` / ``when`` / ``skip_if`` / ``tools``
* ``PhaseConfig.model_override`` — phase-level model override by codename
* ``PhaseConfig.output_schema`` — Pydantic schema name for output validation

``extra="forbid"`` is set at every level so a typo'd key
(``max_iteration`` vs ``max_iterations``) fails loudly rather than
silently dropping the value.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


class IoInput(BaseModel):
    """A single declared input on ``io.inputs``."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    source: Literal["runtime"] = "runtime"
    type: str | None = None
    default: Any | None = None


class IoOutput(BaseModel):
    """A single declared output on ``io.outputs``."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    target: Literal["file", "artifact"]
    type: str | None = None
    path: str | None = None


class IoDeclaration(BaseModel):
    """Top-level ``io:`` block on graph-type skills."""

    model_config = ConfigDict(extra="forbid")

    inputs: list[IoInput] = Field(default_factory=list)
    outputs: list[IoOutput] = Field(default_factory=list)


class Step(BaseModel):
    """A single step inside a phase — Studio-introduced, not in legacy skills.

    ``when`` and ``skip_if`` are simpleeval expressions evaluated at
    run time with the phase's context as the namespace.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    goal: str | None = None
    tools: list[str] = Field(default_factory=list)
    validator: str | None = None
    when: str | None = None
    skip_if: str | None = None


class ContextBridge(BaseModel):
    """Input/output wiring for a subgraph-delegating phase."""

    model_config = ConfigDict(extra="forbid")

    inputs: dict[str, str] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)


class SubSkillSpec(BaseModel):
    """A dynamically-dispatchable sub-skill declared inside a phase.

    LLM-driven dispatch (the phase's agent chooses which named sub_skill
    to call) — contrast with ``subgraph:``, which is static composition
    decided at compile time. The two are mutually exclusive
    (F-subgraph-exclusive-sub-skills).
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    path: str = Field(min_length=1)


class PhaseConfig(BaseModel):
    """One ``<phase_config>`` block's worth of declarations.

    Every field is optional because a phase_config can be sparse in
    legitimate ways:

    * A code-only phase has just ``name`` + ``tools``.
    * A subgraph phase has ``name`` + ``subgraph`` + ``context_bridge``.
    * A full LLM phase has ``name`` + ``tier`` + ``tools`` +
      ``validator`` + loop caps.

    Business rules (e.g. "subgraph + tools mutually exclusive") live in
    the compiler, not in this schema.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    tier: Literal["premium", "balanced", "fast"] | None = None
    model_override: str | None = None
    type: str | None = None
    tools: list[str] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)
    sub_skills: list[SubSkillSpec] = Field(default_factory=list)
    validator: str | None = None
    retry_target: str | None = None
    max_retries: int | None = None
    max_iterations: int | None = None
    max_nudges: int | None = None
    output_schema: str | None = None
    subgraph: str | None = None
    context_bridge: ContextBridge | None = None
    subagent_enabled: bool | None = None


class _SkillManifestBase(BaseModel):
    """Shared fields across graph / simple skill types.

    Not exported — callers discriminate on ``type`` via ``SkillManifest``.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(max_length=1024)
    phases: list[PhaseConfig] = Field(default_factory=list)
    context_mapping: dict[str, str] = Field(default_factory=dict)
    license: str | None = None
    version: str | None = None
    author: str | None = None
    metadata: dict[str, Any] | None = None


class GraphSkillManifest(_SkillManifestBase):
    """A ``type: graph`` skill — multi-phase orchestration with declared io."""

    type: Literal["graph"]
    io: IoDeclaration


class SimpleSkillManifest(_SkillManifestBase):
    """A ``type: simple`` skill — single-turn agent, no formal io block.

    Simple skills read inputs through ``context_mapping`` template
    variables and emit their result via the agent's final tool call
    (``finish_task``). They have exactly one phase_config in practice
    but the schema does not enforce cardinality — the compiler does.
    """

    type: Literal["simple"]
    io: IoDeclaration | None = None


SkillManifest = Annotated[
    Union[GraphSkillManifest, SimpleSkillManifest],
    Field(discriminator="type"),
]
"""Discriminated union over ``type``. Use ``pydantic.TypeAdapter`` to
validate: ``TypeAdapter(SkillManifest).validate_python(data)``."""


__all__ = [
    "ContextBridge",
    "GraphSkillManifest",
    "IoDeclaration",
    "IoInput",
    "IoOutput",
    "PhaseConfig",
    "SimpleSkillManifest",
    "SkillManifest",
    "Step",
    "SubSkillSpec",
]
