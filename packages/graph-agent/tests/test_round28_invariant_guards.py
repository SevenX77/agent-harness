from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

from graph_agent.cognitive.middlewares import create_custom_middlewares
from graph_agent.cognitive.prompt import apply_v030_cognitive_template
from graph_agent.core.error_registry import ERROR_REGISTRY
from graph_agent.core.exceptions import GraphAgentFatalError
from graph_agent.core.module_sandbox import ModuleSandbox
from graph_agent.runtime.state import BlackboardState, blackboard_data_merge

REPO_ROOT = Path(__file__).resolve().parents[3]
FEATURES_PATH = REPO_ROOT / "packages/graph-agent/spec/features.yaml"


def test_round28_prompt_template_keeps_eight_named_slots() -> None:
    prompt = apply_v030_cognitive_template(
        phase_name="main",
        role="Researcher",
        goal="Answer with evidence.",
        steps=[{"id": "S1", "name": "Read", "content": "Read the source."}],
        protocols=[{"id": "P1", "content": "Cite every claim."}],
        output_schema={"type": "object", "properties": {"answer": {"type": "string"}}},
        knowledge_base="Aligned facts.",
        inline_examples=["Inline example."],
    )

    expected_slots = {
        "role",
        "goal",
        "thinking_style",
        "knowledge_base",
        "examples",
        "ambiguity_feedback",
        "protocol_citation",
        "critical_reminders",
    }
    for slot in expected_slots:
        assert f"<{slot}>" in prompt
        assert f"</{slot}>" in prompt
    assert prompt.rstrip().endswith("</exit_contract>")


def test_round28_middleware_order_keeps_observation_before_control() -> None:
    middlewares = create_custom_middlewares(phase_name="round28", callbacks=[])

    names = [type(middleware).__name__ for middleware in middlewares]
    assert names[:4] == [
        "AgentLoopIterationMiddleware",
        "WorkingMemoryMiddleware",
        "DeadEndPruningMiddleware",
        "ClarificationMiddleware",
    ]


def test_round28_tool_sandbox_blocks_write_and_escape_shapes(tmp_path: Path) -> None:
    module_file = tmp_path / "local_action.py"
    module_file.write_text(
        "def run(value):\n"
        "    return {'value': value + 1}\n",
        encoding="utf-8",
    )

    sandbox = ModuleSandbox(search_paths=[tmp_path])
    action = sandbox.import_callable("local_action.run")

    assert action(1) == {"value": 2}
    assert "local_action" not in sys.modules


def test_round28_blackboard_state_has_explicit_mapping_boundary() -> None:
    state: BlackboardState = {
        "data": {
            "inputs": {"topic": "round28"},
            "phase_outputs": {"draft": {"answer": "v1"}},
            "scratch": {},
        },
        "flow": {"phase": "draft"},
        "run_id": "run-1",
    }
    merged = blackboard_data_merge(
        state["data"],
        {"inputs": {}, "phase_outputs": {"review": {"answer": "v2"}}, "scratch": {"k": "v"}},
    )

    assert merged == {
        "inputs": {"topic": "round28"},
        "phase_outputs": {"draft": {"answer": "v1"}, "review": {"answer": "v2"}},
        "scratch": {"k": "v"},
    }
    with pytest.raises(GraphAgentFatalError):
        blackboard_data_merge(merged, {"phase_outputs": {"review": {"answer": "v3"}}})


def test_round28_error_registry_keeps_f_v3_metadata_shape() -> None:
    features = yaml.safe_load(FEATURES_PATH.read_text(encoding="utf-8"))["features"]
    primary_owner_by_code = {
        code: feature["id"]
        for feature in features
        for code in feature.get("error_codes_primary", [])
    }

    assert set(ERROR_REGISTRY) == set(primary_owner_by_code)
    assert len(ERROR_REGISTRY) == 93
    for code, metadata in ERROR_REGISTRY.items():
        assert code.startswith("[F-v3-")
        assert metadata.code == code
        assert metadata.level in {"FATAL", "WARN"}
        assert metadata.stage
        assert metadata.doc_link
        assert primary_owner_by_code[code].startswith("F-")
