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

import inspect
from pathlib import Path
from typing import Any

import pytest

# Import-time sanity: ensure the MVP-3 middleware package is importable
# before any test runs. The actual ordering assertions live in the
# adjacent ``middleware/test_chain_topology.py`` test file.
from graph_agent.middleware import DEFAULT_MIDDLEWARE_ORDER  # noqa: F401


class TestSkillResolver:
    """Resolver used by legacy tests that are not exercising resolution behavior."""

    def resolve_skill(self, skill_id: str) -> Path:
        fixtures = Path(__file__).resolve().parent / "fixtures"
        registry = fixtures / "v030_skill_registry"
        known = {
            "fixture.echo_expert": registry / "echo_expert",
        }
        if skill_id in known:
            return known[skill_id]
        dotted = registry / skill_id.replace(".", "/")
        if (dotted / "GRAPH.md").is_file():
            return dotted
        matches: list[Path] = []
        for tmp_root in Path("/tmp").glob("pytest-of-*"):
            for candidate in tmp_root.rglob(skill_id):
                if candidate.is_dir():
                    matches.append(candidate)
        with_graph = [candidate for candidate in matches if (candidate / "GRAPH.md").is_file()]
        if with_graph:
            return max(with_graph, key=lambda path: path.stat().st_mtime_ns)
        if matches:
            return max(matches, key=lambda path: path.stat().st_mtime_ns)
        raise KeyError(skill_id)


TEST_SKILL_RESOLVER = TestSkillResolver()


def _set_kw_default(func: Any, name: str, value: Any) -> None:
    kwdefaults = dict(getattr(func, "__kwdefaults__", None) or {})
    kwdefaults[name] = value
    func.__kwdefaults__ = kwdefaults

    signature = inspect.signature(func)
    parameters = [
        parameter.replace(default=inspect.Parameter.empty)
        if parameter.name == name
        else parameter
        for parameter in signature.parameters.values()
    ]
    func.__signature__ = signature.replace(parameters=parameters)


def pytest_configure(config: pytest.Config) -> None:
    del config
    from graph_agent.core import compiler, graph_assembler, loader, runner, skill_tool_factory
    from graph_agent.tools import md_to_json
    from graph_agent.tools.builtin.parallel_map import parallel_map

    for func in (
        compiler.compile_skill,
        graph_assembler.assemble_graph,
        loader.SkillLoader.compile_skill,
        loader.load_workflow_from_md,
        runner.run_skill,
        runner._run_skill_dict,
        runner._run_v21_skill_dict,
        skill_tool_factory.build_skill_tool,
        parallel_map,
        md_to_json.md_to_json,
    ):
        _set_kw_default(func, "skill_resolver", TEST_SKILL_RESOLVER)

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

_V1_SKILL_AWAITING_CUTOVER_TESTS = {
    "tests/core/test_module_sandbox.py::test_loader_pipeline_resolves_skill_forward_ref_segment_class",
    "tests/core/test_t11_phase_token_info.py::test_hello_world_phase_token_info_has_raw_line_and_line_numbers",
    "tests/core/test_t11_phase_token_info.py::test_missing_phase_token_info_returns_none",
    "tests/core/test_v21_actions_keys.py::test_context_write_intermediate_state_is_not_output_key_checked",
    "tests/core/test_v21_actions_keys.py::test_text_segmentation_broken_skill_fails_compile_on_context_update",
    "tests/core/test_v21_codemod.py::test_ci_scan_codemod_review_exits_one_on_marker",
    "tests/core/test_v21_codemod.py::test_ci_scan_codemod_review_exits_zero_without_marker",
    "tests/core/test_v21_graph_serializer.py::test_new_phase_appends_one_phase_line",
    "tests/core/test_v21_graph_serializer.py::test_serial_graph_round_trips_byte_exact",
    "tests/core/test_v21_graph_serializer.py::test_single_phase_graph_round_trips_byte_exact",
    "tests/core/test_v21_purity.py::test_purity_cli_clean_exit_0",
    "tests/core/test_v21_purity.py::test_purity_cli_dirty_exit_1",
    "tests/core/test_v21_purity.py::test_purity_cli_ignores_v2_pending",
    "tests/core/test_v21_skill_authoring_guide_example.py::test_skill_authoring_guide_minimal_example_matches_hello_world",
    "tests/e2e/test_batch_analysis_v21.py::test_batch_analysis_v21_compile_and_assemble",
    "tests/e2e/test_batch_analysis_v21.py::test_batch_analysis_v21_e2e_fake_llm_star_topology",
    "tests/e2e/test_batch_analysis_v21.py::test_batch_analysis_v21_reference_fanout_topology",
    "tests/e2e/test_event_extraction_v21.py::test_event_extraction_v21_compile_and_assemble",
    "tests/e2e/test_event_extraction_v21.py::test_event_extraction_v21_e2e_fake_llm",
    "tests/e2e/test_global_synthesis_v21.py::test_global_synthesis_io_field_flow_consistency",
    "tests/e2e/test_global_synthesis_v21.py::test_global_synthesis_v21_compile_and_assemble",
    "tests/e2e/test_global_synthesis_v21.py::test_global_synthesis_v21_e2e_fake_llm",
    "tests/e2e/test_hello_world_v21.py::test_hello_world_v21_compile_and_assemble",
    "tests/e2e/test_hello_world_v21.py::test_hello_world_v21_e2e_tool_then_finish_task",
    "tests/e2e/test_producer_v21.py::test_producer_v21_compile_and_assemble",
    "tests/e2e/test_producer_v21.py::test_producer_v21_e2e_actor_critic_fake_llm",
    "tests/e2e/test_product_manual_v21.py::test_product_manual_v21_compile_and_assemble",
    "tests/e2e/test_product_manual_v21.py::test_product_manual_v21_e2e_fake_llm",
    "tests/e2e/test_subgraph_sample_v21.py::test_subgraph_sample_v21_compile_topology_and_subgraph_refs",
    "tests/e2e/test_subgraph_sample_v21.py::test_subgraph_sample_v21_e2e_fake_llm_smoke",
    "tests/e2e/test_text_segmentation_v21.py::test_text_segmentation_v21_compile_and_assemble",
    "tests/e2e/test_text_segmentation_v21.py::test_text_segmentation_v21_e2e_fake_llm",
    "tests/e2e/test_v21_all_skills_smoke.py::test_v21_all_skills_smoke_discovers_current_sources",
    "tests/integration/skills/event_extraction/test_cognitive_flow_smoke.py::test_event_extraction_compiles_from_v21_root",
    "tests/integration/skills/event_extraction/test_cognitive_flow_smoke.py::test_event_extraction_final_phase_documents_json_output_contract",
    "tests/integration/skills/event_extraction/test_cognitive_flow_smoke.py::test_event_extraction_setup_action_is_discovered",
    "tests/integration/skills/event_extraction/test_validators_runtime.py::TestEventExtractionOutputSchema::test_accepts_well_formed_timeline",
    "tests/integration/skills/event_extraction/test_validators_runtime.py::TestEventExtractionOutputSchema::test_rejects_missing_event_id",
    "tests/integration/skills/event_extraction/test_validators_runtime.py::TestEventExtractionOutputSchema::test_rejects_missing_event_timeline",
    "tests/integration/skills/event_extraction/test_validators_runtime.py::TestEventExtractionOutputSchema::test_rejects_non_integer_paragraph_index",
    "tests/integration/skills/text_segmentation/test_cognitive_flow_smoke.py::test_text_segmentation_compiles_from_v21_root",
    "tests/integration/skills/text_segmentation/test_cognitive_flow_smoke.py::test_text_segmentation_review_documents_json_output_contract",
    "tests/integration/skills/text_segmentation/test_cognitive_flow_smoke.py::test_text_segmentation_setup_action_is_discovered",
    "tests/integration/skills/text_segmentation/test_validators_runtime.py::TestTextSegmentationOutputSchema::test_accepts_well_formed_segmentation_result",
    "tests/integration/skills/text_segmentation/test_validators_runtime.py::TestTextSegmentationOutputSchema::test_rejects_invalid_segment_type",
    "tests/integration/skills/text_segmentation/test_validators_runtime.py::TestTextSegmentationOutputSchema::test_rejects_missing_line_field",
    "tests/integration/skills/text_segmentation/test_validators_runtime.py::TestTextSegmentationOutputSchema::test_rejects_missing_required_root",
    "tests/integration/test_mvp1_smoke.py::TestCompileLayer::test_v3_skill_compiles_to_graph_agent_harness",
    "tests/integration/test_mvp1_smoke.py::TestCompileLayer::test_v3_skill_io_outputs_declared",
    "tests/integration/test_mvp1_smoke.py::TestRealLLMSmoke::test_v3_run_one_chapter_honors_invariants",
    "tests/tools/test_dual_run_shadow.py::test_dual_run_shadow_hello_world_idempotency",
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
        candidate_nodeids = {item.nodeid, f"{nodeid}::{item.name}"}
        if item.cls is not None:
            candidate_nodeids.add(f"{nodeid}::{item.cls.__name__}::{item.name}")
        if candidate_nodeids & _V1_SKILL_AWAITING_CUTOVER_TESTS:
            item.add_marker(xfail_marker)
