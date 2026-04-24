"""Schema validation tests for ``SkillManifest`` (Studio Phase 0 Task 0.1).

The manifest is the single source of truth for SKILL.md shape. These
tests lock in:

* canonical dict shapes for ``graph`` and ``simple`` skills validate
* the discriminator picks the right subclass off ``type``
* ``extra="forbid"`` rejects typos at every level
* the three real ``phase_config`` shapes (code-only / subgraph / LLM)
  survive validation
* a real production SKILL.md's frontmatter round-trips through the
  schema (smoke test — full body parsing arrives in Task 0.3 when
  ``core/parser.py`` is refactored to emit manifest-shaped dicts)
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import TypeAdapter, ValidationError

from graph_agent.core.manifest import (
    ContextBridge,
    GraphSkillManifest,
    IoDeclaration,
    IoInput,
    IoOutput,
    PhaseConfig,
    SimpleSkillManifest,
    SkillManifest,
    Step,
    SubSkillSpec,
)


_SKILL_ADAPTER = TypeAdapter(SkillManifest)


def _base_graph_dict() -> dict:
    """Minimal well-formed ``graph`` manifest."""
    return {
        "name": "sample-graph",
        "description": "A fixture graph skill for manifest validation tests.",
        "type": "graph",
        "io": {
            "inputs": [{"name": "input_a", "source": "runtime", "type": "str"}],
            "outputs": [{"name": "out_a", "target": "file", "path": "out.json"}],
        },
        "phases": [{"name": "phase_one", "tier": "balanced"}],
    }


def _base_simple_dict() -> dict:
    """Minimal well-formed ``simple`` manifest."""
    return {
        "name": "sample-simple",
        "description": "A fixture simple skill for manifest validation tests.",
        "type": "simple",
        "phases": [{"name": "only_phase", "tier": "fast"}],
        "context_mapping": {"chapter_text": "{input.chapter_text}"},
    }


class TestGraphManifestShape:
    """Canonical shape + field-level semantics for graph skills."""

    def test_minimal_graph_validates(self):
        m = _SKILL_ADAPTER.validate_python(_base_graph_dict())
        assert isinstance(m, GraphSkillManifest)
        assert m.type == "graph"
        assert m.schema_version == "1.0"
        assert m.io.inputs[0].name == "input_a"
        assert m.io.outputs[0].target == "file"

    def test_schema_version_defaults_to_1_0(self):
        # Real SKILL.md files never declare schema_version today;
        # it must default so existing skills validate unchanged.
        data = _base_graph_dict()
        assert "schema_version" not in data
        m = _SKILL_ADAPTER.validate_python(data)
        assert m.schema_version == "1.0"

    def test_graph_io_is_required(self):
        data = _base_graph_dict()
        del data["io"]
        with pytest.raises(ValidationError) as exc:
            _SKILL_ADAPTER.validate_python(data)
        assert "io" in str(exc.value).lower()


class TestSimpleManifestShape:
    """Canonical shape + field-level semantics for simple skills."""

    def test_minimal_simple_validates(self):
        m = _SKILL_ADAPTER.validate_python(_base_simple_dict())
        assert isinstance(m, SimpleSkillManifest)
        assert m.type == "simple"
        assert m.context_mapping == {"chapter_text": "{input.chapter_text}"}
        # Simple skills may omit `io`.
        assert m.io is None


class TestTypeDiscriminator:
    """The ``type`` field drives the concrete class choice."""

    def test_type_graph_yields_graph_class(self):
        m = _SKILL_ADAPTER.validate_python(_base_graph_dict())
        assert isinstance(m, GraphSkillManifest)

    def test_type_simple_yields_simple_class(self):
        m = _SKILL_ADAPTER.validate_python(_base_simple_dict())
        assert isinstance(m, SimpleSkillManifest)

    def test_unknown_type_is_rejected(self):
        data = _base_graph_dict()
        data["type"] = "script"  # neither graph nor simple
        with pytest.raises(ValidationError) as exc:
            _SKILL_ADAPTER.validate_python(data)
        assert "type" in str(exc.value).lower()


class TestExtraForbid:
    """Unknown keys fail loudly at every level, catching silent typos."""

    def test_unknown_top_level_key_rejected(self):
        data = _base_graph_dict()
        data["descriptionx"] = "typo'd description"
        with pytest.raises(ValidationError) as exc:
            _SKILL_ADAPTER.validate_python(data)
        assert "descriptionx" in str(exc.value)

    def test_unknown_phase_key_rejected(self):
        data = _base_graph_dict()
        data["phases"] = [{"name": "p", "max_iteration": 3}]  # typo: missing "s"
        with pytest.raises(ValidationError) as exc:
            _SKILL_ADAPTER.validate_python(data)
        assert "max_iteration" in str(exc.value)

    def test_unknown_io_input_key_rejected(self):
        data = _base_graph_dict()
        data["io"]["inputs"] = [
            {"name": "x", "source": "runtime", "kind": "str"}  # should be "type"
        ]
        with pytest.raises(ValidationError):
            _SKILL_ADAPTER.validate_python(data)

    def test_unknown_context_bridge_key_rejected(self):
        # Phase-level nested model also forbids extras.
        data = _base_graph_dict()
        data["phases"] = [{
            "name": "p",
            "subgraph": "child/SKILL.md",
            "context_bridge": {"inputs": {}, "outputs": {}, "extras": {}},
        }]
        with pytest.raises(ValidationError) as exc:
            _SKILL_ADAPTER.validate_python(data)
        assert "extras" in str(exc.value)


class TestRealPhaseShapes:
    """The three phase_config shapes actually found in production skills."""

    def test_code_only_phase(self):
        """E.g. ``text-segmentation``'s ``setup`` phase."""
        m = _SKILL_ADAPTER.validate_python({
            **_base_graph_dict(),
            "phases": [{
                "name": "setup",
                "tools": ["script.segmenter.prepare_chapter"],
            }],
        })
        phase = m.phases[0]
        assert phase.tier is None
        assert phase.tools == ["script.segmenter.prepare_chapter"]

    def test_llm_phase_with_validator_and_loop_caps(self):
        """E.g. ``text-segmentation``'s ``segment`` phase."""
        m = _SKILL_ADAPTER.validate_python({
            **_base_graph_dict(),
            "phases": [{
                "name": "segment",
                "tier": "balanced",
                "tools": [
                    "script.segmenter.parse_segmentation_output",
                    "script.segmenter.store_segments",
                ],
                "validator": "script.validators.validate_segmentation_structure",
                "max_iterations": 10,
                "max_nudges": 2,
            }],
        })
        phase = m.phases[0]
        assert phase.max_iterations == 10
        assert phase.max_nudges == 2
        assert phase.validator == "script.validators.validate_segmentation_structure"

    def test_subgraph_phase_with_context_bridge(self):
        """E.g. ``examples/subgraph-sample``'s delegating phases."""
        m = _SKILL_ADAPTER.validate_python({
            **_base_graph_dict(),
            "phases": [{
                "name": "delegate_segmentation",
                "subgraph": "../../../text-segmentation/SKILL.md",
                "context_bridge": {
                    "inputs": {"chapters": "{context.chapters}"},
                    "outputs": {"segmented_chapters": "{subgraph.segmentation_result}"},
                },
            }],
        })
        phase = m.phases[0]
        assert phase.subgraph == "../../../text-segmentation/SKILL.md"
        assert isinstance(phase.context_bridge, ContextBridge)
        assert phase.context_bridge.inputs == {"chapters": "{context.chapters}"}


class TestStudioNewFields:
    """Fields the plan introduced but no legacy skill uses yet."""

    def test_step_with_conditional_expressions(self):
        m = _SKILL_ADAPTER.validate_python({
            **_base_graph_dict(),
            "phases": [{
                "name": "conditional_phase",
                "steps": [
                    {
                        "name": "maybe_run",
                        "goal": "Run when upstream succeeded",
                        "when": "context.prev_ok == True",
                        "skip_if": "context.force_skip",
                        "tools": ["t1", "t2"],
                    },
                ],
            }],
        })
        step = m.phases[0].steps[0]
        assert isinstance(step, Step)
        assert step.when == "context.prev_ok == True"
        assert step.skip_if == "context.force_skip"

    def test_phase_model_override(self):
        m = _SKILL_ADAPTER.validate_python({
            **_base_graph_dict(),
            "phases": [{
                "name": "override_phase",
                "model_override": "CL46T",  # llm_roles.yaml model code
            }],
        })
        assert m.phases[0].model_override == "CL46T"

    def test_phase_sub_skills_dynamic_dispatch(self):
        m = _SKILL_ADAPTER.validate_python({
            **_base_graph_dict(),
            "phases": [{
                "name": "dispatcher",
                "sub_skills": [
                    {"name": "render", "path": "../subskills/render/SKILL.md"},
                ],
            }],
        })
        sub_skill = m.phases[0].sub_skills[0]
        assert isinstance(sub_skill, SubSkillSpec)
        assert sub_skill.path == "../subskills/render/SKILL.md"


class TestIoFieldValidation:
    """Output ``target`` enum + input ``source`` enum match real vocabulary."""

    def test_target_artifact_accepted(self):
        # Real skill: story-deconstruction uses target: artifact.
        m = _SKILL_ADAPTER.validate_python({
            **_base_graph_dict(),
            "io": {
                "inputs": [{"name": "x", "source": "runtime"}],
                "outputs": [{"name": "y", "target": "artifact"}],
            },
        })
        assert m.io.outputs[0].target == "artifact"

    def test_target_unknown_rejected(self):
        data = _base_graph_dict()
        data["io"]["outputs"] = [{"name": "y", "target": "s3_bucket"}]
        with pytest.raises(ValidationError):
            _SKILL_ADAPTER.validate_python(data)


class TestRealFrontmatterSmoke:
    """Integration smoke: real SKILL.md frontmatters validate once a
    minimal ``phases`` list is spliced in (full body parsing lands in
    Task 0.3 when ``core/parser.py`` emits manifest-shaped dicts).
    """

    @pytest.mark.parametrize(
        "skill_relpath,expected_type,expected_name",
        [
            ("skills/text-segmentation/SKILL.md", "graph", "text-segmentation"),
            ("skills/story-deconstruction/SKILL.md", "graph", "story-deconstruction"),
            ("skills/batch-analysis/SKILL.md", "graph", "batch-analysis"),
            ("skills/adaptation_v1/SKILL.md", "simple", "plan-scenes"),
            ("skills/adaptation_v1/subskills/beat_extractor/SKILL.md",
             "simple", "beat-extractor"),
        ],
    )
    def test_real_skill_frontmatter_validates(
        self, skill_relpath: str, expected_type: str, expected_name: str,
    ):
        root = Path(__file__).resolve().parents[3]
        skill_path = root / skill_relpath
        text = skill_path.read_text(encoding="utf-8")
        frontmatter_block = text.split("---", 2)[1]
        frontmatter = yaml.safe_load(frontmatter_block)

        # Splice in a minimal phases list so the manifest is well-formed
        # without needing the full phase_config body parser.
        manifest_dict = {**frontmatter, "phases": [{"name": "dummy"}]}
        m = _SKILL_ADAPTER.validate_python(manifest_dict)

        assert m.type == expected_type
        assert m.name == expected_name


class TestSubmodelExports:
    """Sanity check on the public surface — all submodels are importable."""

    def test_all_expected_symbols_exportable(self):
        # If any of these imports silently drop, a caller trying to
        # construct dicts in code would hit an AttributeError at the
        # call site; catching it here is cheaper.
        from graph_agent.core import manifest as m

        for sym in (
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
        ):
            assert hasattr(m, sym), f"manifest.py missing public export: {sym}"
