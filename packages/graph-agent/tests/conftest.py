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

import pytest

# Import-time sanity: ensure the MVP-3 middleware package is importable
# before any test runs. The actual ordering assertions live in the
# adjacent ``middleware/test_chain_topology.py`` test file.
from graph_agent.middleware import DEFAULT_MIDDLEWARE_ORDER  # noqa: F401

# V1 cutover legacy test quarantine: these files import old class names removed
# by the V2 refactor. Keep them as reference corpus pending a V1->V2 migration
# spec deciding whether to delete, migrate, or rewrite them.
collect_ignore_glob = [
    "cognitive/test_finish_v2.py",
    "core/test_build_graph_nodes.py",
    "core/test_compile_skill_hostile_inputs.py",
    "core/test_loader_pipeline.py",
    "core/test_loader_xml_rendering.py",
    "core/test_manifest_phase_builders.py",
    "core/test_manifest.py",
    "core/test_parse_skill_md.py",
    "core/test_personas.py",
    "core/test_validate_manifest.py",
    "core/validators/test_persona_resolution.py",
    "core/validators/test_template_variables.py",
    "core/validators/test_tool_paths.py",
    "integration/test_mvp2_schema_io.py",
]

# Test paths that depend on the live repo skills using the V2.1 layout
# (GRAPH.md / phases/). Phase 1 baseline intentionally imported V1 layout
# skills, awaiting user-guided V2.1 cutover.
_V1_SKILL_AWAITING_CUTOVER = [
    "tests/core/test_t11_phase_token_info.py",
    "tests/core/test_v21_actions_keys.py",
    "tests/core/test_v21_codemod.py",
    "tests/core/test_v21_graph_serializer.py",
    "tests/core/test_v21_purity.py",
    "tests/core/test_v21_skill_authoring_guide_example.py",
    "tests/e2e/test_batch_analysis_v21.py",
    "tests/e2e/test_event_extraction_v21.py",
    "tests/e2e/test_global_synthesis_v21.py",
    "tests/e2e/test_hello_world_v21.py",
    "tests/e2e/test_producer_v21.py",
    "tests/e2e/test_text_segmentation_v21.py",
    "tests/e2e/test_product_manual_v21.py",
    "tests/e2e/test_subgraph_sample_v21.py",
    "tests/e2e/test_v21_all_skills_smoke.py",
    "tests/integration/skills/",
    "tests/integration/test_mvp1_smoke.py",
    "tests/tools/test_dual_run_shadow.py",
]

_V1_SKILL_AWAITING_CUTOVER_TESTS = {
    "tests/core/test_module_sandbox.py::test_loader_pipeline_resolves_skill_forward_ref_segment_class",
}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    xfail_marker = pytest.mark.xfail(
        reason="by-design: V1 layout skill awaiting user V2.1 cutover (Phase 1 baseline)",
        strict=False,
    )
    tests_root = config.rootpath
    if not (tests_root / "tests").exists() and (tests_root / "packages/graph-agent/tests").exists():
        tests_root = tests_root / "packages/graph-agent"
    for item in items:
        nodeid = str(item.path.relative_to(tests_root))
        full_nodeid = f"{nodeid}::{item.name}"
        if full_nodeid in _V1_SKILL_AWAITING_CUTOVER_TESTS:
            item.add_marker(xfail_marker)
            continue
        if any(nodeid.startswith(pattern) for pattern in _V1_SKILL_AWAITING_CUTOVER):
            item.add_marker(xfail_marker)
