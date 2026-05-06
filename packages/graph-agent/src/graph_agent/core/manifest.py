"""Pydantic v2 contract for SKILL.md manifest validation.

Single source of truth that replaces the four independent validation
sites (``core/parser.py``, ``core/loader.py``, ``core/compiler.py``,
``deerflow/skills/parser.py`` — see Studio Phase 0 plan at
``docs/superpowers/plans/2026-04-22-graph-agent-studio.md``).

Three-axis taxonomy
===================

After a 3-round Claude/Gemini architectural debate (2026-04-24), the
skill ecosystem is modelled on **three orthogonal axes**:

1. **Artifact Level** (file-level, discriminated by ``type:``):
   - ``type: agent``   — single-turn agent, DeerFlow Agent Loop driven,
                         has an ``agent_profile``, no phases/io.
   - ``type: graph``   — state-machine orchestration, declared ``io:``
                         and ordered ``phases:``.
   - ``type: persona`` — pure knowledge injection (no execution engine),
                         embedded into other skills via ``adopted_persona``
                         and compiled to ``Prompt -> LLM -> StructuredOutput``
                         (single-shot chain, NOT a ReAct loop).

2. **Phase Execution Level** (node-level, discriminated by ``mode:``
   inside each ``GraphSkillDef.phases`` entry, strictly mutually
   exclusive):
   - ``mode: llm``      — LLM-driven ReAct loop with ``agent_tools``.
   - ``mode: logic``    — deterministic Python runtime with
                          ``execute_steps`` (Python callable import paths).

   The 1.x ``mode: delegate`` (subgraph composition) and
   ``mode: parallel_delegate`` (fan-out) modes were removed in the
   v1-reset MVP-0 cleanup (B1, 2026-04-28). Static cross-skill
   composition will return in V2 via LangGraph's Send API.

3. **Delegation Mechanism** (tool-level, how a phase reaches other
   skills):
   - ``sub_skills`` field — removed by 2026-04-26 cohesion plan 方针 1.2:
     the schema field had no loader/runtime wiring, no production skill
     ever set it, and leaving the documented-but-dead surface in the
     schema mis-led authors. Re-add when the runtime ships.
   - ``LLMPhase.steps`` (and the former ``Step`` class) — historically
     removed by mistake, restored on 2026-04-26 as ``list[str]`` aligned
     with ``AgentProfile.steps``. This is prompt structure (the plan path
     the LLM should read), not a framework runtime execution unit. The
     loader renders it into the system_prompt body, like ``<reference>`` /
     ``<example>`` prompt tags. The old ``Step`` object class is removed
     to avoid implying false runtime contracts for per-step ``tools`` /
     ``validator`` fields.

Prompt Schema Extensions
========================

``domain_protocols`` capture numbered domain rules the model should cite.
``references`` declare local knowledge files the model may inspect later.
``few_shot_examples`` hold prompt-level examples; persona skills already
carry the same concept for persona injection. ``context_access`` declares
which prior-run context surfaces a prompt may request. Schema 2.0 only
exposes ``llm_role``; ``tier`` was removed in PR-B (2026-04-27).

Reference resolution
====================

``adopted_persona`` is a plain string that follows the Hybrid resolver
rules:

- ``"./subskills/format_scene"`` → strict nested (relative to the
  current SKILL.md file).
- ``"producer"`` (bare name) → **global registry only**; shadow copies
  at ``./subskills/producer`` are ignored. Bare name never falls back
  to local lookup (WYSIWYG, prevents silent behaviour drift on copy-paste).

The resolver itself lives in the compiler (not in this schema). This
module only declares the reference type.

Compiler rules enforced here
============================

Constraints that can be expressed structurally are enforced by
``extra='forbid'`` + the discriminated unions. Rules requiring cross-
field inspection use ``@model_validator``:

- Rule 1 (node-engine exclusivity): automatic via ``PhaseDef`` discriminator.
- Rule 3 (top-level structure): automatic via ``SkillManifest``
  discriminator + each variant's field surface.
- Rule 4 (persona purity): ``PersonaSkillDef`` declares only knowledge
  fields; ``extra='forbid'`` kills any attempt to add ``phases``,
  ``tools``, or execution-bearing keys.

Schema is version ``2.0``. The ``1.x`` vocabulary (``type: simple``,
untagged phases, ``tools:``) is intentionally removed — Phase 0 is an
all-at-once rewrite. Production SKILL.md files migrate in Task 0.3
(parser refactor).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

# =============================================================================
# Atomic structures (reused across artifact types / phase modes)
# =============================================================================


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
    """Top-level ``io:`` block — required on ``type: graph`` skills."""

    model_config = ConfigDict(extra="forbid")

    inputs: list[IoInput] = Field(default_factory=list)
    outputs: list[IoOutput] = Field(default_factory=list)


class ContextBridge(BaseModel):
    """Input/output wiring between parent and child skills.

    Retained for the upcoming A8 ContextBridge merge (T10), which will
    consolidate this Pydantic version with the dataclass mirror in
    ``core/types.py``. The 1.x DelegatePhase consumer was removed in
    MVP-0 B1; new V2 delegation will reuse this same model.

    MVP-2 T4: gained ``to_business_data_schema`` so child-skill
    BusinessData construction routes through the shared SchemaEngine
    instead of either side reaching for its own parser. Until V2
    delegation lands, the bridge carries only field names (``inputs`` is
    ``dict[str, str]`` mapping child field → parent path expression);
    the bridge therefore has no intrinsic type information and yields a
    permissive ``Any``-typed SchemaObject. Type-strict bridges arrive
    when the V2 delegation contract picks up the full child manifest.
    """

    model_config = ConfigDict(extra="forbid")

    inputs: dict[str, str] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)

    def to_business_data_schema(self, schema_engine: Any) -> Any:
        """Project the bridge's ``inputs`` into a SchemaEngine SchemaObject.

        The returned ``SchemaObject`` carries one declared field per
        bridge input keyed by the child-skill business name; descriptors
        are ``Any`` so the resulting Pydantic model accepts whatever the
        parent skill emits (V2 delegation will tighten this once parent
        and child manifests can be diffed for type compatibility).

        ``schema_engine`` is taken as a parameter rather than imported at
        module top to keep ``manifest.py`` a pure data layer (no
        runtime dependency cycle with ``schema_engine.py``); callers
        pass the loader's shared singleton via
        ``graph_agent.core.loader.get_schema_engine``.
        """
        # Lazy import keeps manifest.py a pure schema module — no
        # circular dependency with the schema_engine subsystem.
        from .schema_engine import SchemaObject

        fields = tuple((name, Any) for name in self.inputs)
        # MVP-2 T4 surface: the engine arg threads in for two reasons.
        #   1. It documents the contract (callers must own a SchemaEngine).
        #   2. It primes the engine's lru cache so a downstream
        #      ``schema_engine.get_pydantic_model(schema_obj)`` call returns
        #      a stable class identity. Calling get_pydantic_model here
        #      (rather than in the caller) keeps the caching policy local
        #      to the bridge.
        schema_obj = SchemaObject(
            fields=fields,
            required_fields=frozenset(self.inputs.keys()),
            schema_name="ContextBridgeBusinessData",
        )
        # Touch the engine so the model class is built and cached.
        schema_engine.get_pydantic_model(schema_obj)
        return schema_obj


# =============================================================================
# Phase multi-mode (discriminated union on ``mode:``)
# =============================================================================


class _BasePhase(BaseModel):
    """Fields shared by all three phase engines."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    model_override: str | None = None


class LLMPhase(_BasePhase):
    """LLM-driven phase with a ReAct/Tool-calling loop.

    ``adopted_persona`` lives here. The originally-planned
    ``sub_skills`` field was dropped per 2026-04-26 cohesion plan 方针
    1.2 (schema declared, runtime never wired); re-add when the runtime
    ships. Static cross-skill composition (1.x ``mode: delegate`` /
    ``mode: parallel_delegate``) was removed in MVP-0 B1 (2026-04-28)
    and will return in V2 via LangGraph Send API.
    """

    mode: Literal["llm"]
    prompt: str | None = None
    user_prompt_template: str | None = None
    agent_tools: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    domain_protocols: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    few_shot_examples: list[str] = Field(default_factory=list)
    context_access: list[Literal["artifact", "working_memory"]] = Field(default_factory=list)
    llm_role: str | None = None
    adopted_persona: str | None = None
    max_iterations: int | None = Field(default=None, ge=1)
    max_retries: int | None = Field(default=None, ge=0)
    max_nudges: int | None = Field(default=None, ge=0)
    dead_end_threshold: int | None = Field(default=None, ge=1)
    validator: str | None = None
    validator_optional: bool = Field(
        default=False,
        description=(
            "Set True to explicitly opt out of business validation when "
            "a phase declares output_schema/output_example."
        ),
    )
    retry_target: str | None = None
    hoist_to: str | None = Field(
        default=None,
        description=(
            "Optional ctx key to inject validated business_data_parsed into "
            "after finish_task succeeds."
        ),
    )
    output_schema: str | None = None
    output_example: str | None = None
    output_schema_md: str | None = None
    output_example_md: str | None = None


class LogicPhase(_BasePhase):
    """Deterministic Python-runtime phase, no LLM involvement.

    LogicPhase is a pure function from inputs to outputs. Retry has no
    semantic meaning here — same input → same output. If transient
    failures (HTTP, file IO) need retry, business code wraps it in
    try/except. Framework does not provide retry routing for logic
    phases.
    """

    mode: Literal["logic"]
    execute_steps: list[str] = Field(min_length=1)
    validator: str | None = None


PhaseDef = Annotated[
    LLMPhase | LogicPhase,
    Field(discriminator="mode"),
]
"""Discriminated union over ``mode``. Use
``pydantic.TypeAdapter(PhaseDef).validate_python(data)`` or reference
through ``GraphSkillDef.phases``."""


# =============================================================================
# Artifact-level types (discriminated union on ``type:``)
# =============================================================================


class _BaseSkill(BaseModel):
    """Shared metadata fields across all three artifact types."""

    model_config = ConfigDict(extra="forbid")
    _compiled_schemas: dict[str, Any] = PrivateAttr(default_factory=dict)

    schema_version: Literal["2.0"] = "2.0"
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(max_length=1024)
    license: str | None = None
    version: str | None = None
    author: str | None = None
    metadata: dict[str, Any] | None = None

    @property
    def compiled_schemas(self) -> dict[str, Any]:
        """Phase-2 injected SchemaObject map, keyed by phase name."""
        return self._compiled_schemas

    @compiled_schemas.setter
    def compiled_schemas(self, value: dict[str, Any]) -> None:
        self._compiled_schemas = value


class AgentProfile(BaseModel):
    """Anthropic-compatible role/goal/steps declaration for agent skills.

    The compiler assembles ``role`` + ``goal`` + ``steps`` + ``constraints``
    into the final System Prompt sent to DeerFlow's agent loop.
    """

    model_config = ConfigDict(extra="forbid")

    role: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    steps: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    domain_protocols: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    few_shot_examples: list[str] = Field(default_factory=list)
    context_access: list[Literal["artifact", "working_memory"]] = Field(default_factory=list)
    llm_role: str | None = None


class AgentSkillDef(_BaseSkill):
    """A ``type: agent`` skill — single-turn DeerFlow Agent Loop.

    Replaces the 1.x ``type: simple``. The rename signals the
    Anthropic-compatible surface area (role/goal/steps/constraints).
    """

    type: Literal["agent"]
    agent_profile: AgentProfile
    model_override: str | None = None
    agent_tools: list[str] = Field(default_factory=list)
    adopted_persona: str | None = None
    user_prompt_template: str | None = None
    context_mapping: dict[str, str] = Field(default_factory=dict)


class GraphSkillDef(_BaseSkill):
    """A ``type: graph`` skill — multi-phase state-machine orchestration."""

    type: Literal["graph"]
    io: IoDeclaration
    phases: list[PhaseDef] = Field(min_length=1)
    context_mapping: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_phase_names_unique(self) -> GraphSkillDef:
        """Cohesion plan 方针 1.7 (2026-04-26): LangGraph node names are
        keyed off ``f'{phase.name}_execute'``; duplicate phase names
        silently overwrite each other's routing edges, so the second
        phase becomes unreachable. Reject duplicates at parse time.
        """
        seen: set[str] = set()
        duplicates: list[str] = []
        for phase in self.phases:
            if phase.name in seen and phase.name not in duplicates:
                duplicates.append(phase.name)
            seen.add(phase.name)
        if duplicates:
            raise ValueError(
                f"Duplicate phase name(s) in GraphSkillDef.phases: "
                f"{duplicates!r}. LangGraph routes nodes by phase.name + "
                "'_execute'; duplicate names overwrite each other's edges, "
                "making the second occurrence unreachable. Rename so each "
                "phase has a unique name."
            )
        return self

    @model_validator(mode="after")
    def _check_retry_targets_resolve(self) -> GraphSkillDef:
        """Cohesion plan 方针 1.6 (2026-04-26): ``retry_target`` on an
        LLMPhase must point to a phase that exists in the same
        GraphSkillDef. A typo / dangling reference would crash the
        runtime when ``RetryRouter`` tries to look it up; surface the
        problem at parse time instead.
        """
        phase_names = {p.name for p in self.phases}
        bad: list[str] = []
        for phase in self.phases:
            target = getattr(phase, "retry_target", None)
            if target is not None and target not in phase_names:
                bad.append(f"{phase.name}.retry_target -> {target!r}")
        if bad:
            raise ValueError(
                "Dangling retry_target reference(s): "
                + "; ".join(bad)
                + ". retry_target must name a phase declared in this "
                "GraphSkillDef.phases (a self-loop is allowed)."
            )
        return self


class PersonaSkillDef(_BaseSkill):
    """A ``type: persona`` skill — pure knowledge injection, no execution.

    Compiled to a single-shot ``Prompt -> LLM -> StructuredOutput`` chain
    when referenced via ``adopted_persona``. Crucially lacks ``phases``,
    ``tools``, and any other execution-bearing fields —
    ``extra='forbid'`` enforces purity.

    ``few_shot_examples`` is a list (not a concatenated string) so the
    compiler can materialise them as pre-filled ``messages`` history on
    providers that support it (e.g. Anthropic API), rather than wedging
    them into the System Prompt.
    """

    type: Literal["persona"]
    role_profile: str = Field(min_length=1)
    evaluation_rubrics: str | None = None
    few_shot_examples: list[str] = Field(default_factory=list)


SkillManifest = Annotated[
    AgentSkillDef | GraphSkillDef | PersonaSkillDef,
    Field(discriminator="type"),
]
"""Discriminated union over ``type``. Use ``pydantic.TypeAdapter`` to
validate: ``TypeAdapter(SkillManifest).validate_python(data)``."""


__all__ = [
    "AgentProfile",
    "AgentSkillDef",
    "ContextBridge",
    "GraphSkillDef",
    "IoDeclaration",
    "IoInput",
    "IoOutput",
    "LLMPhase",
    "LogicPhase",
    "PersonaSkillDef",
    "PhaseDef",
    "SkillManifest",
]
