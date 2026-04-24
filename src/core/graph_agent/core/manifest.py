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
   - ``mode: delegate`` — invokes another Graph/Agent skill via
                          ``subgraph:`` + ``context_bridge``; the child
                          skill owns its own iteration, so
                          ``max_iterations`` is forbidden on this mode.

3. **Delegation Mechanism** (tool-level, how a phase reaches other
   skills — these three are *mutually exclusive* per phase, not new
   artifact types):
   - ``subgraph:`` — compile-time composition (Edge control flow).
   - ``sub_skills:`` — semantic routing: the LLM picks at runtime
                       which registered skill to Tool-Call into.
   - ``subagent_enabled:`` — ad-hoc generation: the LLM spawns an
                             anonymous sub-agent with no SKILL.md.

Reference resolution
====================

``subgraph``, ``sub_skills[*]``, and ``adopted_persona`` are all plain
strings that follow the Hybrid resolver rules:

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
- Rule 2 (delegate determinism): ``DelegatePhase`` simply lacks the
  forbidden fields (``max_iterations``, ``prompt``, ``agent_tools``, ...).
- Rule 3 (top-level structure): automatic via ``SkillManifest``
  discriminator + each variant's field surface.
- Rule 4 (persona purity): ``PersonaSkillDef`` declares only knowledge
  fields; ``extra='forbid'`` kills any attempt to add ``phases``,
  ``tools``, or execution-bearing keys.
- Rule 5 (context_bridge static type check) — deferred to a dedicated
  ``validators/context_bridge.py`` module that consumes manifests; it
  is not a Pydantic validator because it needs the child manifest
  loaded (cross-file information).

Schema is version ``2.0``. The ``1.x`` vocabulary (``type: simple``,
untagged phases, ``tools:``) is intentionally removed — Phase 0 is an
all-at-once rewrite. Production SKILL.md files migrate in Task 0.3
(parser refactor).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


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


class Step(BaseModel):
    """A single conditional step inside an ``LLMPhase.steps``.

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
    """Input/output wiring for a ``DelegatePhase``.

    Only valid on ``mode: delegate``. The compiler's
    ``validators/context_bridge.py`` (Rule 5) statically type-checks
    these mappings against the child skill's ``io:`` declaration at
    load time.
    """

    model_config = ConfigDict(extra="forbid")

    inputs: dict[str, str] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)


# =============================================================================
# Phase multi-mode (discriminated union on ``mode:``)
# =============================================================================


class _BasePhase(BaseModel):
    """Fields shared by all three phase engines."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    tier: Literal["premium", "balanced", "fast"] | None = None
    model_override: str | None = None


class LLMPhase(_BasePhase):
    """LLM-driven phase with a ReAct/Tool-calling loop.

    All three delegation mechanisms (``sub_skills``, ``subagent_enabled``)
    plus ``adopted_persona`` live here. ``subgraph:`` does NOT — static
    composition is a different phase mode (``DelegatePhase``).
    """

    mode: Literal["llm"]
    prompt: str | None = None
    agent_tools: list[str] = Field(default_factory=list)
    sub_skills: list[str] = Field(default_factory=list)
    subagent_enabled: bool = False
    adopted_persona: str | None = None
    max_iterations: int | None = None
    max_retries: int | None = None
    max_nudges: int | None = None
    validator: str | None = None
    retry_target: str | None = None
    output_schema: str | None = None
    steps: list[Step] = Field(default_factory=list)


class LogicPhase(_BasePhase):
    """Deterministic Python-runtime phase, no LLM involvement.

    ``execute_steps`` holds Python callable import paths (e.g.
    ``"script.segmenter.prepare_chapter"``) which are invoked in order.
    This is NOT the ``LLMPhase.tools`` field — those entries need JSON
    Schema + Description for Function Calling, whereas ``execute_steps``
    only needs import paths. Conflating them was the core design flaw
    the 1.x vocabulary carried.
    """

    mode: Literal["logic"]
    execute_steps: list[str] = Field(min_length=1)
    validator: str | None = None


class DelegatePhase(_BasePhase):
    """Static-composition phase: invokes another Graph/Agent skill.

    The child skill owns its own iteration and prompt machinery, so
    ``max_iterations``, ``prompt``, ``agent_tools``, ``sub_skills``,
    and ``subagent_enabled`` are all *absent by construction* —
    ``extra='forbid'`` on ``_BasePhase`` rejects them.
    """

    mode: Literal["delegate"]
    subgraph: str = Field(min_length=1)
    context_bridge: ContextBridge


PhaseDef = Annotated[
    Union[LLMPhase, LogicPhase, DelegatePhase],
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

    schema_version: Literal["2.0"] = "2.0"
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(max_length=1024)
    license: str | None = None
    version: str | None = None
    author: str | None = None
    metadata: dict[str, Any] | None = None


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


class AgentSkillDef(_BaseSkill):
    """A ``type: agent`` skill — single-turn DeerFlow Agent Loop.

    Replaces the 1.x ``type: simple``. The rename signals the
    Anthropic-compatible surface area (role/goal/steps/constraints).
    """

    type: Literal["agent"]
    agent_profile: AgentProfile
    agent_tools: list[str] = Field(default_factory=list)
    sub_skills: list[str] = Field(default_factory=list)
    subagent_enabled: bool = False
    adopted_persona: str | None = None
    context_mapping: dict[str, str] = Field(default_factory=dict)


class GraphSkillDef(_BaseSkill):
    """A ``type: graph`` skill — multi-phase state-machine orchestration."""

    type: Literal["graph"]
    io: IoDeclaration
    phases: list[PhaseDef] = Field(min_length=1)
    context_mapping: dict[str, str] = Field(default_factory=dict)


class PersonaSkillDef(_BaseSkill):
    """A ``type: persona`` skill — pure knowledge injection, no execution.

    Compiled to a single-shot ``Prompt -> LLM -> StructuredOutput`` chain
    when referenced via ``adopted_persona``. Crucially lacks ``phases``,
    ``tools``, ``sub_skills``, and any other execution-bearing fields —
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
    Union[AgentSkillDef, GraphSkillDef, PersonaSkillDef],
    Field(discriminator="type"),
]
"""Discriminated union over ``type``. Use ``pydantic.TypeAdapter`` to
validate: ``TypeAdapter(SkillManifest).validate_python(data)``."""


__all__ = [
    "AgentProfile",
    "AgentSkillDef",
    "ContextBridge",
    "DelegatePhase",
    "GraphSkillDef",
    "IoDeclaration",
    "IoInput",
    "IoOutput",
    "LLMPhase",
    "LogicPhase",
    "PersonaSkillDef",
    "PhaseDef",
    "SkillManifest",
    "Step",
]
