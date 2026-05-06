"""Schema validation tests for ``SkillManifest`` (Studio Phase 0 Task 0.1).

The manifest is the single source of truth for SKILL.md shape. These
tests lock in the three-axis taxonomy agreed on 2026-04-24:

* Three artifact types (``agent`` / ``graph`` / ``persona``) validate
  and discriminate correctly.
* Three phase modes (``llm`` / ``logic`` / ``delegate``) are mutually
  exclusive by construction.
* ``extra="forbid"`` rejects typos and cross-mode contamination at
  every level.
* The compiler rules that can be expressed structurally (Rules 1–4
  from ``manifest.py``'s docstring) fire as ``ValidationError`` at
  parse time — no silent drop.

Rule 5 (``context_bridge`` static type check across parent/child skill
``io:`` schemas) is deferred to a dedicated validators module and is
NOT covered here.

Production SKILL.md round-trip tests are deferred to Task 0.3 when
``core/parser.py`` is refactored to emit manifest-shaped dicts — the
1.x vocabulary those files currently use is intentionally invalid
against schema_version 2.0.
"""

from __future__ import annotations

import pytest
from graph_agent.core.manifest import (
    AgentProfile,
    AgentSkillDef,
    ContextBridge,
    GraphSkillDef,
    LLMPhase,
    LogicPhase,
    PersonaSkillDef,
    SkillManifest,
)
from pydantic import TypeAdapter, ValidationError

# DelegatePhase / ParallelDelegatePhase removed in MVP-0 B1 (2026-04-28).


_SKILL_ADAPTER = TypeAdapter(SkillManifest)


# =============================================================================
# Fixtures — minimal well-formed dicts for each artifact type
# =============================================================================


def _base_agent_dict() -> dict:
    return {
        "name": "sample-agent",
        "description": "A fixture agent skill for manifest validation tests.",
        "type": "agent",
        "agent_profile": {
            "role": "Senior code reviewer",
            "goal": "Identify defects in staged changes and propose minimal fixes.",
            "steps": ["Read diff", "Check invariants", "Emit report"],
            "constraints": ["No speculative refactors."],
        },
    }


def _base_graph_dict() -> dict:
    return {
        "name": "sample-graph",
        "description": "A fixture graph skill for manifest validation tests.",
        "type": "graph",
        "io": {
            "inputs": [{"name": "input_a", "source": "runtime", "type": "str"}],
            "outputs": [{"name": "out_a", "target": "file", "path": "out.json"}],
        },
        "phases": [
            {
                "mode": "llm",
                "name": "phase_one",
                "llm_role": "balanced",
                "prompt": "Do the thing.",
            }
        ],
    }


def _base_persona_dict() -> dict:
    return {
        "name": "sample-persona",
        "description": "A fixture persona for manifest validation tests.",
        "type": "persona",
        "role_profile": "You are a senior producer with ten years in short drama.",
    }


# =============================================================================
# Artifact-level discriminator
# =============================================================================


class TestArtifactDiscriminator:
    """The ``type`` field drives which variant the union picks."""

    def test_type_agent_yields_agent_class(self):
        m = _SKILL_ADAPTER.validate_python(_base_agent_dict())
        assert isinstance(m, AgentSkillDef)
        assert m.type == "agent"
        assert m.schema_version == "2.0"
        assert isinstance(m.agent_profile, AgentProfile)

    def test_type_graph_yields_graph_class(self):
        m = _SKILL_ADAPTER.validate_python(_base_graph_dict())
        assert isinstance(m, GraphSkillDef)
        assert m.type == "graph"
        assert len(m.phases) == 1

    def test_type_persona_yields_persona_class(self):
        m = _SKILL_ADAPTER.validate_python(_base_persona_dict())
        assert isinstance(m, PersonaSkillDef)
        assert m.type == "persona"
        assert m.few_shot_examples == []

    def test_legacy_simple_type_rejected(self):
        """``type: simple`` was removed in schema 2.0 — must not validate."""
        data = _base_agent_dict()
        data["type"] = "simple"
        with pytest.raises(ValidationError) as exc:
            _SKILL_ADAPTER.validate_python(data)
        assert "type" in str(exc.value).lower()

    def test_unknown_type_rejected(self):
        data = _base_graph_dict()
        data["type"] = "script"
        with pytest.raises(ValidationError):
            _SKILL_ADAPTER.validate_python(data)


# =============================================================================
# Rule 3 — top-level structure enforcement
# =============================================================================


class TestTopLevelStructureRules:
    """Each artifact type's field surface is distinct; cross-contamination fails."""

    def test_agent_cannot_have_phases(self):
        data = _base_agent_dict()
        data["phases"] = [{"mode": "llm", "name": "x", "prompt": "p"}]
        with pytest.raises(ValidationError) as exc:
            _SKILL_ADAPTER.validate_python(data)
        assert "phases" in str(exc.value)

    def test_agent_cannot_have_io(self):
        data = _base_agent_dict()
        data["io"] = {"inputs": [], "outputs": []}
        with pytest.raises(ValidationError) as exc:
            _SKILL_ADAPTER.validate_python(data)
        assert "io" in str(exc.value)

    def test_graph_requires_io(self):
        data = _base_graph_dict()
        del data["io"]
        with pytest.raises(ValidationError) as exc:
            _SKILL_ADAPTER.validate_python(data)
        assert "io" in str(exc.value).lower()

    def test_graph_requires_at_least_one_phase(self):
        data = _base_graph_dict()
        data["phases"] = []
        with pytest.raises(ValidationError) as exc:
            _SKILL_ADAPTER.validate_python(data)
        assert "phases" in str(exc.value).lower()

    def test_agent_requires_agent_profile(self):
        data = _base_agent_dict()
        del data["agent_profile"]
        with pytest.raises(ValidationError) as exc:
            _SKILL_ADAPTER.validate_python(data)
        assert "agent_profile" in str(exc.value)


# =============================================================================
# Rule 4 — persona purity (no execution-bearing fields)
# =============================================================================


class TestPersonaPurity:
    """Persona skills must not carry execution fields."""

    def test_persona_cannot_have_phases(self):
        data = _base_persona_dict()
        data["phases"] = [{"mode": "llm", "name": "x", "prompt": "p"}]
        with pytest.raises(ValidationError) as exc:
            _SKILL_ADAPTER.validate_python(data)
        assert "phases" in str(exc.value)

    def test_persona_cannot_have_agent_tools(self):
        data = _base_persona_dict()
        data["agent_tools"] = ["some.tool"]
        with pytest.raises(ValidationError) as exc:
            _SKILL_ADAPTER.validate_python(data)
        assert "agent_tools" in str(exc.value)

    def test_persona_purity_after_sub_skills_removal(self):
        """Cohesion plan 方针 1.2 (2026-04-26): ``sub_skills`` was
        removed from the schema because no production runtime ever
        wired it. The earlier ``test_persona_cannot_have_sub_skills``
        regression test was reworked to cover ``agent_tools`` instead;
        keep this second method (with a distinct name to avoid Python
        silently overriding the first ``test_persona_cannot_have_agent_tools``
        above) so the 1.2 motivation stays in the diff history.
        """
        data = _base_persona_dict()
        data["agent_tools"] = ["pkg.f"]
        with pytest.raises(ValidationError) as exc:
            _SKILL_ADAPTER.validate_python(data)
        assert "agent_tools" in str(exc.value)

    def test_persona_cannot_have_io(self):
        data = _base_persona_dict()
        data["io"] = {"inputs": [], "outputs": []}
        with pytest.raises(ValidationError) as exc:
            _SKILL_ADAPTER.validate_python(data)
        assert "io" in str(exc.value)

    def test_persona_few_shot_examples_is_list(self):
        data = _base_persona_dict()
        data["few_shot_examples"] = [
            "Input: chapter 1 --- Output: [critical feedback]",
            "Input: chapter 2 --- Output: [praise + 2 tweaks]",
        ]
        m = _SKILL_ADAPTER.validate_python(data)
        assert isinstance(m, PersonaSkillDef)
        assert len(m.few_shot_examples) == 2


# =============================================================================
# Phase mode discriminator
# =============================================================================


class TestAgentSkillExtensions:
    """Fields added for 1.x → 2.0 migration of production agent skills."""

    def test_agent_user_prompt_template_accepted(self):
        data = _base_agent_dict()
        data["user_prompt_template"] = "Review the diff: {diff}"
        m = _SKILL_ADAPTER.validate_python(data)
        assert isinstance(m, AgentSkillDef)
        assert m.user_prompt_template == "Review the diff: {diff}"

    def test_agent_model_override_accepted(self):
        data = _base_agent_dict()
        data["model_override"] = "CL47T"
        m = _SKILL_ADAPTER.validate_python(data)
        assert isinstance(m, AgentSkillDef)
        assert m.model_override == "CL47T"


class TestLLMPhaseUserPromptTemplate:
    """``user_prompt_template`` is per-turn template — separate from ``prompt``."""

    def test_llm_phase_user_prompt_template_accepted(self):
        m = _SKILL_ADAPTER.validate_python({
            **_base_graph_dict(),
            "phases": [{
                "mode": "llm",
                "name": "segment",
                "prompt": "You are a segmenter.",
                "user_prompt_template": "Segment: {chapter_content}",
            }],
        })
        assert m.phases[0].user_prompt_template == "Segment: {chapter_content}"

    def test_logic_phase_cannot_have_user_prompt_template(self):
        data = _base_graph_dict()
        data["phases"] = [{
            "mode": "logic",
            "name": "bad",
            "execute_steps": ["x.y"],
            "user_prompt_template": "Nope: {x}",
        }]
        with pytest.raises(ValidationError) as exc:
            _SKILL_ADAPTER.validate_python(data)
        assert "user_prompt_template" in str(exc.value)

class TestPhaseModeDiscriminator:
    """Each ``mode:`` value picks exactly one phase class."""

    def test_llm_mode_yields_llm_phase(self):
        m = _SKILL_ADAPTER.validate_python({
            **_base_graph_dict(),
            "phases": [{
                "mode": "llm",
                "name": "plan",
                "prompt": "You are a planner.",
                "agent_tools": ["read_file", "write_file"],
                "max_iterations": 5,
            }],
        })
        phase = m.phases[0]
        assert isinstance(phase, LLMPhase)
        assert phase.max_iterations == 5

    def test_logic_mode_yields_logic_phase(self):
        m = _SKILL_ADAPTER.validate_python({
            **_base_graph_dict(),
            "phases": [{
                "mode": "logic",
                "name": "setup",
                "execute_steps": ["script.segmenter.prepare_chapter"],
            }],
        })
        phase = m.phases[0]
        assert isinstance(phase, LogicPhase)
        assert phase.execute_steps == ["script.segmenter.prepare_chapter"]

    def test_unknown_mode_rejected(self):
        data = _base_graph_dict()
        data["phases"] = [{"mode": "python", "name": "x"}]
        with pytest.raises(ValidationError) as exc:
            _SKILL_ADAPTER.validate_python(data)
        assert "mode" in str(exc.value).lower()

    def test_missing_mode_rejected(self):
        data = _base_graph_dict()
        data["phases"] = [{"name": "x", "prompt": "p"}]
        with pytest.raises(ValidationError) as exc:
            _SKILL_ADAPTER.validate_python(data)
        assert "mode" in str(exc.value).lower()


# =============================================================================
# Rule 1 — phase engines are mutually exclusive
# =============================================================================


class TestPhaseEngineExclusivity:
    """A phase declared as one mode cannot carry another mode's fields."""

    def test_logic_phase_cannot_have_prompt(self):
        data = _base_graph_dict()
        data["phases"] = [{
            "mode": "logic",
            "name": "bad",
            "execute_steps": ["x.y.z"],
            "prompt": "You are...",
        }]
        with pytest.raises(ValidationError) as exc:
            _SKILL_ADAPTER.validate_python(data)
        assert "prompt" in str(exc.value)

    def test_logic_phase_agent_tools_replaces_removed_sub_skills_contract(self):
        data = _base_graph_dict()
        data["phases"] = [{
            "mode": "logic",
            "name": "bad",
            "execute_steps": ["x.y.z"],
            "agent_tools": ["t1"],
        }]
        with pytest.raises(ValidationError) as exc:
            _SKILL_ADAPTER.validate_python(data)
        assert "agent_tools" in str(exc.value)

    def test_logic_phase_cannot_have_agent_tools(self):
        """Cohesion plan 方针 1.2 (2026-04-26): ``sub_skills`` was
        removed from the schema because no production runtime ever
        wired it. The logic-phase determinism guarantee is now
        demonstrated via ``agent_tools`` (also forbidden on logic)."""
        data = _base_graph_dict()
        data["phases"] = [{
            "mode": "logic",
            "name": "bad",
            "execute_steps": ["x.y.z"],
            "agent_tools": ["pkg.f"],
        }]
        with pytest.raises(ValidationError) as exc:
            _SKILL_ADAPTER.validate_python(data)
        assert "agent_tools" in str(exc.value)

    def test_logic_phase_requires_execute_steps(self):
        data = _base_graph_dict()
        data["phases"] = [{"mode": "logic", "name": "bad"}]
        with pytest.raises(ValidationError) as exc:
            _SKILL_ADAPTER.validate_python(data)
        assert "execute_steps" in str(exc.value)

    def test_llm_phase_cannot_have_execute_steps(self):
        data = _base_graph_dict()
        data["phases"] = [{
            "mode": "llm",
            "name": "bad",
            "prompt": "p",
            "execute_steps": ["x.y"],
        }]
        with pytest.raises(ValidationError) as exc:
            _SKILL_ADAPTER.validate_python(data)
        assert "execute_steps" in str(exc.value)

    def test_llm_phase_cannot_have_subgraph(self):
        """Regression guard: 1.x ``subgraph:`` field must not slip back in
        on LLMPhase via ``extra='forbid'``."""
        data = _base_graph_dict()
        data["phases"] = [{
            "mode": "llm",
            "name": "bad",
            "prompt": "p",
            "subgraph": "./x",
        }]
        with pytest.raises(ValidationError) as exc:
            _SKILL_ADAPTER.validate_python(data)
        assert "subgraph" in str(exc.value)


# =============================================================================
# Delegation mechanisms — DelegatePhase + ParallelDelegatePhase tests removed
# in MVP-0 B1 (2026-04-28); the modes themselves are gone.
# =============================================================================


class TestDelegationMechanisms:
    """LLM phases expose three ways to reach other skills."""

    def test_sub_skills_field_rejected(self):
        """Cohesion plan 方针 1.2 (2026-04-26): ``sub_skills`` was
        removed from the schema because no production skill ever set
        it and the loader never wired it through to the runtime — i.e.
        it was a documented field with zero observable behavior. Until
        the runtime materialises (skill_tool_factory.build_skill_tool
        injection into Phase.tools), the schema rejects the field
        outright so authors can't write code that silently no-ops."""
        with pytest.raises(ValidationError) as exc:
            _SKILL_ADAPTER.validate_python({
                **_base_graph_dict(),
                "phases": [{
                    "mode": "llm",
                    "name": "dispatcher",
                    "prompt": "Route to the right tool.",
                    "sub_skills": ["producer"],
                }],
            })
        assert "sub_skills" in str(exc.value)

    def test_removed_subagent_enabled_rejected(self):
        m = _SKILL_ADAPTER.validate_python({
            **_base_graph_dict(),
            "phases": [{
                "mode": "llm",
                "name": "x",
                "prompt": "p",
            }],
        })
        assert not hasattr(m.phases[0], "subagent_enabled")

        with pytest.raises(ValidationError) as exc:
            _SKILL_ADAPTER.validate_python({
                **_base_graph_dict(),
                "phases": [{
                    "mode": "llm",
                    "name": "x",
                    "prompt": "p",
                    "subagent_enabled": True,
                }],
            })
        assert "subagent_enabled" in str(exc.value)


# =============================================================================
# Persona injection — adopted_persona field
# =============================================================================


class TestAdoptedPersonaInjection:
    """LLM phases and agent skills can inject a persona."""

    def test_llm_phase_adopted_persona(self):
        m = _SKILL_ADAPTER.validate_python({
            **_base_graph_dict(),
            "phases": [{
                "mode": "llm",
                "name": "review",
                "prompt": "Review this plan.",
                "adopted_persona": "producer",
            }],
        })
        assert m.phases[0].adopted_persona == "producer"

    def test_llm_phase_adopted_persona_relative_path(self):
        m = _SKILL_ADAPTER.validate_python({
            **_base_graph_dict(),
            "phases": [{
                "mode": "llm",
                "name": "review",
                "prompt": "Review this plan.",
                "adopted_persona": "./subskills/villain_designer",
            }],
        })
        assert m.phases[0].adopted_persona == "./subskills/villain_designer"

    def test_agent_skill_adopted_persona(self):
        data = _base_agent_dict()
        data["adopted_persona"] = "producer"
        m = _SKILL_ADAPTER.validate_python(data)
        assert isinstance(m, AgentSkillDef)
        assert m.adopted_persona == "producer"

    def test_logic_phase_cannot_have_adopted_persona(self):
        data = _base_graph_dict()
        data["phases"] = [{
            "mode": "logic",
            "name": "bad",
            "execute_steps": ["x.y"],
            "adopted_persona": "producer",
        }]
        with pytest.raises(ValidationError) as exc:
            _SKILL_ADAPTER.validate_python(data)
        assert "adopted_persona" in str(exc.value)

# =============================================================================
# extra='forbid' at every level
# =============================================================================


class TestExtraForbid:
    """Unknown keys fail loudly at every level — catches typos & drift."""

    def test_unknown_top_level_key_rejected(self):
        data = _base_graph_dict()
        data["descriptionx"] = "typo"
        with pytest.raises(ValidationError) as exc:
            _SKILL_ADAPTER.validate_python(data)
        assert "descriptionx" in str(exc.value)

    def test_unknown_agent_profile_key_rejected(self):
        data = _base_agent_dict()
        data["agent_profile"]["persona"] = "x"
        with pytest.raises(ValidationError) as exc:
            _SKILL_ADAPTER.validate_python(data)
        assert "persona" in str(exc.value)

    def test_unknown_io_input_key_rejected(self):
        data = _base_graph_dict()
        data["io"]["inputs"] = [{"name": "x", "source": "runtime", "kind": "str"}]
        with pytest.raises(ValidationError):
            _SKILL_ADAPTER.validate_python(data)

    def test_unknown_context_bridge_key_rejected(self):
        """ContextBridge model still uses ``extra='forbid'``; verify directly
        since the 1.x ``mode: delegate`` consumer was removed in MVP-0 B1."""
        with pytest.raises(ValidationError) as exc:
            ContextBridge.model_validate({"inputs": {}, "outputs": {}, "extras": {}})
        assert "extras" in str(exc.value)


class TestContextBridgeSchemaEngineIntegration:
    """MVP-2 T4: ContextBridge.to_business_data_schema must route through SchemaEngine.

    These tests pin the bridge → SchemaEngine wiring so future
    refactors can't quietly bring back an in-bridge schema parser.
    """

    def test_to_business_data_schema_returns_schema_object(self):
        from graph_agent.core.schema_engine import SchemaEngine, SchemaObject

        bridge = ContextBridge(
            inputs={"chapter_text": "parent.text", "chapter_id": "parent.id"},
        )
        engine = SchemaEngine()

        schema = bridge.to_business_data_schema(engine)

        assert isinstance(schema, SchemaObject)
        assert schema.schema_name == "ContextBridgeBusinessData"
        # Both bridge inputs surface as fields on the resulting schema.
        field_names = [name for name, _typ in schema.fields]
        assert field_names == ["chapter_text", "chapter_id"]
        # All bridge inputs are treated as required until V2 delegation
        # ships per-input optional/default metadata.
        assert schema.required_fields == frozenset({"chapter_text", "chapter_id"})

    def test_to_business_data_schema_calls_schema_engine(self):
        """The engine arg is exercised, not just stored — calling
        ``get_pydantic_model`` warms the engine's lru cache so a later
        engine call by the same caller hits a stable class identity."""
        from graph_agent.core.schema_engine import SchemaEngine

        bridge = ContextBridge(inputs={"x": "parent.x"})

        calls: list[str] = []

        class _SpyEngine(SchemaEngine):
            def get_pydantic_model(self, schema):  # type: ignore[override]
                calls.append("get_pydantic_model")
                return super().get_pydantic_model(schema)

        spy = _SpyEngine()
        bridge.to_business_data_schema(spy)

        assert calls == ["get_pydantic_model"], (
            "ContextBridge.to_business_data_schema must touch SchemaEngine "
            "(it's the proof the bridge no longer carries its own parser); "
            f"got call sequence {calls!r}."
        )

    def test_to_business_data_schema_handles_empty_inputs(self):
        from graph_agent.core.schema_engine import SchemaEngine

        bridge = ContextBridge()  # no inputs declared
        engine = SchemaEngine()

        schema = bridge.to_business_data_schema(engine)

        assert schema.fields == ()
        assert schema.required_fields == frozenset()

    def test_context_bridge_has_no_underscore_framework_fields(self):
        """Invariant: ContextBridge surface declares only business wiring.

        Framework metadata travels in ``state['flow']`` (FrameworkState);
        ContextBridge wires *business* data only. A regression that adds
        a ``_thread_id``-style attribute here would violate the
        BusinessData purity invariant from MVP-1 design §1.
        """
        declared = set(ContextBridge.model_fields.keys())
        assert declared == {"inputs", "outputs"}, (
            f"ContextBridge surface drifted; expected {{inputs, outputs}}, "
            f"got {declared!r}."
        )

    def test_to_business_data_schema_rejects_underscore_input_keys(self):
        """A PM-authored ``_underscore`` key in ``inputs`` must surface as a
        compile-time error rather than silently leaking into the child
        BusinessData namespace.

        ContextBridge passes the input dict verbatim into ``SchemaObject``;
        Pydantic ``create_model`` refuses model fields whose names start
        with ``_`` and raises :class:`NameError` from inside
        ``SchemaEngine.get_pydantic_model``. We assert that raise here so a
        future change that swallows the error (e.g. by stripping the
        prefix) is caught by this regression test.
        """
        from graph_agent.core.schema_engine import SchemaEngine

        bridge = ContextBridge(
            inputs={"normal_field": "parent.x", "_sneaky_meta": "parent.y"},
        )
        with pytest.raises(NameError, match="leading underscores"):
            bridge.to_business_data_schema(SchemaEngine())

    def test_typo_in_phase_field_name(self):
        """``max_iteration`` without trailing ``s`` used to silently drop."""
        data = _base_graph_dict()
        data["phases"] = [{
            "mode": "llm",
            "name": "p",
            "prompt": "p",
            "max_iteration": 3,  # missing "s"
        }]
        with pytest.raises(ValidationError) as exc:
            _SKILL_ADAPTER.validate_python(data)
        assert "max_iteration" in str(exc.value)


# =============================================================================
# io: field validation
# =============================================================================


class TestIoFieldValidation:
    def test_target_artifact_accepted(self):
        m = _SKILL_ADAPTER.validate_python({
            **_base_graph_dict(),
            "io": {
                "inputs": [{"name": "x", "source": "runtime"}],
                "outputs": [{"name": "y", "target": "artifact"}],
            },
        })
        assert m.io.outputs[0].target == "artifact"

    def test_target_file_accepted(self):
        m = _SKILL_ADAPTER.validate_python({
            **_base_graph_dict(),
            "io": {
                "inputs": [{"name": "x", "source": "runtime"}],
                "outputs": [{"name": "y", "target": "file", "path": "out.md"}],
            },
        })
        assert m.io.outputs[0].target == "file"

    def test_target_unknown_rejected(self):
        data = _base_graph_dict()
        data["io"]["outputs"] = [{"name": "y", "target": "s3_bucket"}]
        with pytest.raises(ValidationError):
            _SKILL_ADAPTER.validate_python(data)


# =============================================================================
# LLMPhase.steps prompt structure
# =============================================================================


class TestLLMPhaseSteps:
    def test_llm_phase_accepts_steps_as_str_list(self):
        """LLMPhase.steps accepts list[str], aligned with AgentProfile.steps."""
        manifest = _SKILL_ADAPTER.validate_python({
            **_base_graph_dict(),
            "phases": [{
                "mode": "llm",
                "name": "planning_phase",
                "prompt": "p",
                "steps": ["read context", "call tools", "return answer"],
            }],
        })

        phase = manifest.phases[0]
        assert isinstance(phase, LLMPhase)
        assert phase.steps == ["read context", "call tools", "return answer"]

    def test_llm_phase_steps_default_empty_list(self):
        """Omitting steps defaults to [], preserving existing manifests."""
        phase = LLMPhase.model_validate({
            "mode": "llm",
            "name": "p",
            "prompt": "p",
        })

        assert phase.steps == []

    def test_llm_phase_steps_rejects_dict_object(self):
        """Old Step-object shaped entries are rejected; schema is list[str]."""
        with pytest.raises(ValidationError) as exc:
            _SKILL_ADAPTER.validate_python({
                **_base_graph_dict(),
                "phases": [{
                    "mode": "llm",
                    "name": "planning_phase",
                    "prompt": "p",
                    "steps": [{"name": "maybe_run", "tools": ["t1"]}],
                }],
            })

        assert "steps" in str(exc.value)

    def test_step_class_no_longer_importable(self):
        """Step class is removed; import should fail."""
        with pytest.raises(ImportError):
            from graph_agent.core.manifest import Step  # noqa: F401


class TestLLMPhaseExtendedFields:
    def test_domain_protocols_default_empty(self):
        phase = LLMPhase.model_validate({"mode": "llm", "name": "p"})
        assert phase.domain_protocols == []

    def test_references_default_empty(self):
        phase = LLMPhase.model_validate({"mode": "llm", "name": "p"})
        assert phase.references == []

    def test_few_shot_examples_default_empty(self):
        phase = LLMPhase.model_validate({"mode": "llm", "name": "p"})
        assert phase.few_shot_examples == []

    def test_context_access_default_empty(self):
        phase = LLMPhase.model_validate({"mode": "llm", "name": "p"})
        assert phase.context_access == []

    def test_context_access_only_accepts_literal_values(self):
        phase = LLMPhase.model_validate({
            "mode": "llm",
            "name": "p",
            "context_access": ["artifact", "working_memory"],
        })
        assert phase.context_access == ["artifact", "working_memory"]

        with pytest.raises(ValidationError):
            LLMPhase.model_validate({
                "mode": "llm",
                "name": "p",
                "context_access": ["database"],
            })

    def test_llm_role_optional_string(self):
        phase = LLMPhase.model_validate({
            "mode": "llm",
            "name": "p",
            "llm_role": "architect",
        })
        assert phase.llm_role == "architect"


class TestAgentProfileExtendedFields:
    def test_domain_protocols_default_empty(self):
        profile = AgentProfile(role="r", goal="g")
        assert profile.domain_protocols == []

    def test_references_default_empty(self):
        profile = AgentProfile(role="r", goal="g")
        assert profile.references == []

    def test_few_shot_examples_default_empty(self):
        profile = AgentProfile(role="r", goal="g")
        assert profile.few_shot_examples == []

    def test_context_access_default_empty(self):
        profile = AgentProfile(role="r", goal="g")
        assert profile.context_access == []

    def test_context_access_only_accepts_literal_values(self):
        profile = AgentProfile.model_validate({
            "role": "r",
            "goal": "g",
            "context_access": ["artifact", "working_memory"],
        })
        assert profile.context_access == ["artifact", "working_memory"]

        with pytest.raises(ValidationError):
            AgentProfile.model_validate({
                "role": "r",
                "goal": "g",
                "context_access": ["database"],
            })

    def test_llm_role_optional_string(self):
        profile = AgentProfile(role="r", goal="g", llm_role="architect")
        assert profile.llm_role == "architect"


class TestTierRemoval:
    def test_llm_phase_rejects_tier_field(self):
        """Q3 decision 2026-04-27: schema tier was removed."""
        with pytest.raises(ValidationError, match="tier"):
            LLMPhase(
                name="test",
                mode="llm",
                tier="balanced",
            )

    def test_llm_role_alone_works_normally(self):
        phase = LLMPhase.model_validate({
            "mode": "llm",
            "name": "p",
            "llm_role": "architect",
        })
        assert phase.llm_role == "architect"

    def test_logic_phase_rejects_tier_field(self):
        """LogicPhase also rejects tier through inherited extra='forbid'."""
        with pytest.raises(ValidationError, match="tier"):
            LogicPhase(
                name="test",
                mode="logic",
                execute_steps=["mod.func"],
                tier="balanced",
            )

    def test_agent_skill_def_rejects_tier_field(self):
        """Top-level AgentSkillDef no longer accepts tier."""
        with pytest.raises(ValidationError, match="tier"):
            AgentSkillDef(
                type="agent",
                name="test",
                description="t",
                agent_profile=AgentProfile(role="r", goal="g"),
                tier="balanced",
            )

    def test_agent_profile_llm_role_alone_works_normally(self):
        data = _base_agent_dict()
        data["agent_profile"]["llm_role"] = "architect"
        manifest = _SKILL_ADAPTER.validate_python(data)
        assert isinstance(manifest, AgentSkillDef)
        assert manifest.agent_profile.llm_role == "architect"


# =============================================================================
# Public surface
# =============================================================================


# =============================================================================
# Cohesion plan 方针 1.6 / 1.7 / 1.8 (2026-04-26): cross-field validators
# =============================================================================


class TestLogicPhaseRetryFields:
    """LogicPhase schema rejects retry fields — Q1 decision (2026-04-27)."""

    def test_logic_phase_rejects_retry_target(self):
        with pytest.raises(ValidationError, match="retry_target"):
            LogicPhase(
                name="test",
                mode="logic",
                execute_steps=["module.func"],
                retry_target="other_phase",
            )

    def test_logic_phase_rejects_max_retries(self):
        with pytest.raises(ValidationError, match="max_retries"):
            LogicPhase(
                name="test",
                mode="logic",
                execute_steps=["module.func"],
                max_retries=3,
            )


class TestRetryTargetReferenceValidation:
    """``retry_target`` on an LLMPhase must point to another phase in the
    same GraphSkillDef. A typo / dangling reference must fail at parse
    time, not surprise the runtime when RetryRouter tries to look it up.
    """

    def test_dangling_retry_target_rejected(self):
        data = _base_graph_dict()
        data["phases"] = [
            {
                "mode": "llm",
                "name": "draft",
                "llm_role": "balanced",
                "prompt": "draft something",
                "retry_target": "nonexistent_phase",
            },
            {
                "mode": "llm",
                "name": "review",
                "llm_role": "balanced",
                "prompt": "review",
            },
        ]
        with pytest.raises(ValidationError) as exc:
            _SKILL_ADAPTER.validate_python(data)
        msg = str(exc.value)
        assert "retry_target" in msg, (
            "retry_target validator must mention the field by name; got "
            f"{msg!r}"
        )
        assert "nonexistent_phase" in msg, (
            "Error message must include the offending value so the author "
            f"can locate the typo; got {msg!r}"
        )

    def test_valid_retry_target_accepted(self):
        data = _base_graph_dict()
        data["phases"] = [
            {
                "mode": "llm",
                "name": "draft",
                "llm_role": "balanced",
                "prompt": "draft something",
                "retry_target": "draft",  # self-loop is valid
            }
        ]
        m = _SKILL_ADAPTER.validate_python(data)
        assert isinstance(m, GraphSkillDef)


class TestPhaseNameUniqueness:
    """LangGraph nodes are keyed off ``f'{phase.name}_execute'``; duplicate
    phase names silently overwrite each other's routing. Reject at parse
    time."""

    def test_duplicate_phase_names_rejected(self):
        data = _base_graph_dict()
        data["phases"] = [
            {
                "mode": "llm",
                "name": "duplicated",
                "llm_role": "balanced",
                "prompt": "first",
            },
            {
                "mode": "llm",
                "name": "duplicated",
                "llm_role": "balanced",
                "prompt": "second",
            },
        ]
        with pytest.raises(ValidationError) as exc:
            _SKILL_ADAPTER.validate_python(data)
        msg = str(exc.value)
        assert "duplicated" in msg or "unique" in msg.lower() or "duplicate" in msg.lower(), (
            "Phase-name uniqueness validator must mention either the "
            "duplicated name or the word duplicate/unique so the author "
            f"can fix the SKILL.md; got {msg!r}"
        )


class TestCountFieldsLowerBound:
    """``max_iterations``, ``max_retries``, ``max_nudges`` must be >= 0
    or >= 1 — zero and negative inputs were silently accepted before."""

    def test_negative_max_iterations_rejected(self):
        with pytest.raises(ValidationError):
            LLMPhase.model_validate(
                {
                    "mode": "llm",
                    "name": "p",
                    "max_iterations": -1,
                }
            )

    def test_zero_max_iterations_rejected(self):
        """``max_iterations=0`` means the agent loop never runs — that is
        almost certainly a typo, not an intent. Reject it."""
        with pytest.raises(ValidationError):
            LLMPhase.model_validate(
                {
                    "mode": "llm",
                    "name": "p",
                    "max_iterations": 0,
                }
            )

    def test_negative_max_retries_rejected(self):
        with pytest.raises(ValidationError):
            LLMPhase.model_validate(
                {
                    "mode": "llm",
                    "name": "p",
                    "max_retries": -1,
                }
            )

    def test_zero_max_retries_accepted(self):
        """``max_retries=0`` is meaningful: the phase runs exactly once
        with no retries. Distinct from None (which means default)."""
        phase = LLMPhase.model_validate(
            {"mode": "llm", "name": "p", "max_retries": 0}
        )
        assert phase.max_retries == 0

    def test_negative_max_nudges_rejected(self):
        with pytest.raises(ValidationError):
            LLMPhase.model_validate(
                {
                    "mode": "llm",
                    "name": "p",
                    "max_nudges": -3,
                }
            )


class TestSubmodelExports:
    def test_all_expected_symbols_exportable(self):
        from graph_agent.core import manifest as m

        for sym in (
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
        ):
            assert hasattr(m, sym), f"manifest.py missing public export: {sym}"
