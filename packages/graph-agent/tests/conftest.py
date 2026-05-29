"""Shared fixtures + import-time invariants for the graph_agent suite.

The middleware-chain topological order regression test lives in
``tests/graph_agent/middleware/test_chain_topology.py`` so pytest
collects it as part of the full suite (``conftest.py`` is treated as
a fixtures file and tests inside it do not run during a full
``pytest tests/graph_agent/`` invocation). The import below acts as
an import-time sanity check — if the middleware package fails to
import (e.g., a missing module after a refactor), every test in the
suite errors out at collection rather than producing a confusing
runtime failure deep in a single test case.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from graph_agent.core.skill_resolver_protocol import SkillResolutionError, validate_skill_id

# Import-time sanity: ensure the MVP-3 middleware package is importable
# before any test runs. The actual ordering assertions live in the
# adjacent ``middleware/test_chain_topology.py`` test file.
from graph_agent.middleware import DEFAULT_MIDDLEWARE_ORDER  # noqa: F401


class MockSkillResolver:
    """Deterministic resolver used by tests that are not exercising lookup behavior."""

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root
        self.fixtures = Path(__file__).resolve().parent / "fixtures"

    def resolve_skill(self, skill_id: str) -> Path:
        validate_skill_id(skill_id)
        fixtures = self.fixtures
        registry = fixtures / "v030_skill_registry"
        known = {
            "fixture.echo_expert": registry / "echo_expert",
            "demo.echo_agent": fixtures / "v030_agent_demo" / "registry" / "echo_agent",
            "e2e.echo": fixtures / "v030_e2e_pipeline" / "registry" / "echo",
            "e2e.expander": fixtures / "v030_e2e_pipeline" / "registry" / "expander",
        }
        if skill_id in known:
            return known[skill_id]
        relative = Path(*skill_id.split("."))
        candidates = (
            self.workspace_root / skill_id,
            self.workspace_root / relative,
            self.workspace_root / "registry" / skill_id,
            self.workspace_root / "registry" / relative,
            registry / skill_id,
            registry / relative,
        )
        for candidate in candidates:
            if (candidate / "GRAPH.md").is_file():
                return candidate
        phases_root = self.workspace_root / "phases"
        if phases_root.is_dir():
            for phase_dir in sorted(path for path in phases_root.iterdir() if path.is_dir()):
                candidate = phase_dir / skill_id
                if (candidate / "GRAPH.md").is_file():
                    return candidate
        raise SkillResolutionError(skill_id, "not registered in deterministic test resolver")


@pytest.fixture
def mock_skill_resolver(tmp_path: Path) -> MockSkillResolver:
    return MockSkillResolver(tmp_path)


collect_ignore_glob: list[str] = []

_V21_CORPUS_DEFERRED_TESTS = {
    "tests/integration/skills/event_extraction/test_cognitive_flow_smoke.py::test_event_extraction_compiles_from_legacy_v21_root",
    "tests/integration/skills/event_extraction/test_cognitive_flow_smoke.py::test_event_extraction_final_phase_documents_json_output_contract",
    "tests/integration/skills/event_extraction/test_cognitive_flow_smoke.py::test_event_extraction_setup_action_is_discovered",
    "tests/integration/skills/event_extraction/test_validators_runtime.py::TestEventExtractionOutputSchema::test_accepts_well_formed_timeline",
    "tests/integration/skills/event_extraction/test_validators_runtime.py::TestEventExtractionOutputSchema::test_rejects_missing_event_id",
    "tests/integration/skills/event_extraction/test_validators_runtime.py::TestEventExtractionOutputSchema::test_rejects_missing_event_timeline",
    "tests/integration/skills/event_extraction/test_validators_runtime.py::TestEventExtractionOutputSchema::test_rejects_non_integer_paragraph_index",
    "tests/integration/skills/text_segmentation/test_cognitive_flow_smoke.py::test_text_segmentation_compiles_from_legacy_v21_root",
    "tests/integration/skills/text_segmentation/test_cognitive_flow_smoke.py::test_text_segmentation_review_documents_json_output_contract",
    "tests/integration/skills/text_segmentation/test_cognitive_flow_smoke.py::test_text_segmentation_setup_action_is_discovered",
    "tests/integration/skills/text_segmentation/test_validators_runtime.py::TestTextSegmentationOutputSchema::test_accepts_well_formed_segmentation_result",
    "tests/integration/skills/text_segmentation/test_validators_runtime.py::TestTextSegmentationOutputSchema::test_rejects_invalid_segment_type",
    "tests/integration/skills/text_segmentation/test_validators_runtime.py::TestTextSegmentationOutputSchema::test_rejects_missing_line_field",
    "tests/integration/skills/text_segmentation/test_validators_runtime.py::TestTextSegmentationOutputSchema::test_rejects_missing_required_root",
}

_V1_SKILL_AWAITING_CUTOVER_TESTS = {
    "tests/core/test_module_sandbox.py::test_loader_pipeline_resolves_skill_forward_ref_segment_class",
    "tests/integration/test_mvp1_smoke.py::TestCompileLayer::test_v3_skill_compiles_to_graph_agent_harness",
    "tests/integration/test_mvp1_smoke.py::TestCompileLayer::test_v3_skill_io_outputs_declared",
    "tests/integration/test_mvp1_smoke.py::TestRealLLMSmoke::test_v3_run_one_chapter_honors_invariants",
    "tests/tools/test_dual_run_shadow.py::test_dual_run_shadow_hello_world_idempotency",
}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    v1_xfail_marker = pytest.mark.xfail(
        reason="by-design: V1 layout skill awaiting user V2.1 cutover (Phase 1 baseline)",
        strict=False,
    )
    v21_corpus_xfail_marker = pytest.mark.xfail(
        reason=(
            "by-design: root skills/ corpus is still V2.1 format; compiling it with the "
            "V0.3.0 engine is deferred to PR G §10 corpus migration and is outside the "
            "engine cleanup scope"
        ),
        strict=False,
    )
    tests_root = config.rootpath
    if not (tests_root / "tests").exists() and (tests_root / "packages/graph-agent/tests").exists():
        tests_root = tests_root / "packages/graph-agent"
    for item in items:
        nodeid = str(item.path.relative_to(tests_root))
        candidate_nodeids = {item.nodeid, f"{nodeid}::{item.name}"}
        if item.cls is not None:
            candidate_nodeids.add(f"{nodeid}::{item.cls.__name__}::{item.name}")
        if candidate_nodeids & _V21_CORPUS_DEFERRED_TESTS:
            item.add_marker(v21_corpus_xfail_marker)
        elif candidate_nodeids & _V1_SKILL_AWAITING_CUTOVER_TESTS:
            item.add_marker(v1_xfail_marker)
