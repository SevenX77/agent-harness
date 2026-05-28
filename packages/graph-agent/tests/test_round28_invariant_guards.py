from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "packages/graph-agent/src/graph_agent"


def _read(relative_path: str) -> str:
    return (SRC_ROOT / relative_path).read_text(encoding="utf-8")


def test_round28_prompt_template_keeps_eight_named_slots() -> None:
    text = _read("cognitive/prompt.py")
    expected_slots = {
        "role",
        "goal",
        "thinking_style",
        "examples",
        "knowledge_base",
        "ambiguity_feedback",
        "critical_reminders",
        "exit_contract",
    }
    rendered_slots = set(re.findall(r"<(/?)([a-z_]+)>", text))
    slot_names = {slot for _slash, slot in rendered_slots}
    assert expected_slots <= slot_names


def test_round28_middleware_order_keeps_observation_before_control() -> None:
    text = _read("cognitive/middlewares.py")
    factory = text[text.index("def create_custom_middlewares") :]
    loop_index = factory.index("middlewares.append(\n            AgentLoopIterationMiddleware")
    memory_index = factory.index("middlewares.append(\n            WorkingMemoryMiddleware")
    pruning_index = factory.index("middlewares.append(\n            DeadEndPruningMiddleware")
    clarification_index = factory.index("middlewares.append(ClarificationMiddleware())")
    assert loop_index < memory_index < pruning_index < clarification_index


def test_round28_tool_sandbox_blocks_write_and_escape_shapes() -> None:
    sandbox_text = _read("core/module_sandbox.py")
    purity_text = _read("core/purity.py")
    assert "escape" in sandbox_text.lower()
    assert "open" in purity_text and "write" in purity_text
    assert "ImportError" in sandbox_text or "PermissionError" in sandbox_text


def test_round28_blackboard_state_has_explicit_mapping_boundary() -> None:
    mapper_text = _read("runtime/state_mapper.py")
    state_text = _read("runtime/state.py")
    assert "blackboard" in mapper_text
    assert "inputs" in mapper_text and "phase_outputs" in mapper_text and "scratch" in mapper_text
    assert "BlackboardState" in state_text


def test_round28_error_registry_keeps_f_v3_metadata_shape() -> None:
    text = _read("core/error_registry.py")
    assert "[F-v3-" in text
    assert "level" in text
    assert "stage" in text
    assert "doc_link" in text
