from __future__ import annotations

import ast
import json
from pathlib import Path

BACKEND_ROOT = next(
    parent for parent in Path(__file__).resolve().parents if (parent / "app").is_dir() and (parent / "tests").is_dir()
)


def test_golden_diff_uses_headless_adapter_contract_instead_of_final_state_file_diff() -> None:
    source = (BACKEND_ROOT / "app" / "services" / "golden_diff.py").read_text(encoding="utf-8")

    assert "GoldenHeadlessRequest" in source
    assert "GoldenHeadlessResult" in source
    assert "final_state.json" not in source
    assert not _contains_computed_string(source, "final_state.json")
    assert "_diff_value" not in source


def test_golden_headless_does_not_fallback_to_sample_skill_id() -> None:
    source = (BACKEND_ROOT / "app" / "services" / "golden_headless.py").read_text(encoding="utf-8")

    assert "text-segmentation" not in source
    assert "evaluate_golden_baseline" not in source


def test_golden_headless_returns_per_node_verdicts(tmp_path: Path) -> None:
    from app.services.golden_headless import GoldenHeadlessRequest, evaluate_golden_headless

    current_path = tmp_path / "current" / "result.json"
    golden_path = tmp_path / "golden" / "result.json"
    current_path.parent.mkdir()
    golden_path.parent.mkdir()
    current_path.write_text(
        json.dumps(
            {
                "run_id": "current-run",
                "success": True,
                "phases": [
                    {"phase_name": "setup", "outputs": {"answer": "hello studio", "ok": True}},
                    {"phase_name": "review", "outputs": {"score": 10}},
                ],
            }
        ),
        encoding="utf-8",
    )
    golden_path.write_text(
        json.dumps(
            {
                "run_id": "golden-run",
                "success": True,
                "phases": [
                    {"phase_name": "setup", "outputs": {"answer": "hello world", "ok": True}},
                    {"phase_name": "review", "outputs": {"score": 10}},
                ],
            }
        ),
        encoding="utf-8",
    )

    result = evaluate_golden_headless(
        GoldenHeadlessRequest(
            run_results_ref=str(current_path),
            baseline_ref=str(golden_path),
        )
    )

    assert [node.node_id for node in result.node_results] == ["setup", "review"]
    setup = result.node_results[0]
    review = result.node_results[1]
    assert setup.verdict == "fail"
    assert setup.score < 1
    assert setup.differences[0].field_path == "nodes.setup.answer"
    assert review.verdict == "pass"
    assert review.score == 1
    assert review.differences == []


def test_golden_headless_returns_per_node_verdicts_for_real_run_shape(tmp_path: Path) -> None:
    """Real engine run/golden result is BusinessData {inputs, phase_outputs, scratch}.

    Per-node golden must derive nodes from the `phase_outputs` dict, not only from
    the synthetic top-level `phases` list. Without this, real runs silently degrade
    to a single run-level `output` verdict.
    """
    from app.services.golden_headless import GoldenHeadlessRequest, evaluate_golden_headless

    current_path = tmp_path / "current" / "result.json"
    golden_path = tmp_path / "golden" / "result.json"
    current_path.parent.mkdir()
    golden_path.parent.mkdir()
    current_path.write_text(
        json.dumps(
            {
                "inputs": {"topic": "x"},
                "phase_outputs": {
                    "draft": {"answer": "hello studio", "ok": True},
                    "review": {"score": 10},
                },
                "scratch": {},
            }
        ),
        encoding="utf-8",
    )
    golden_path.write_text(
        json.dumps(
            {
                "inputs": {"topic": "x"},
                "phase_outputs": {
                    "draft": {"answer": "hello world", "ok": True},
                    "review": {"score": 10},
                },
                "scratch": {},
            }
        ),
        encoding="utf-8",
    )

    result = evaluate_golden_headless(
        GoldenHeadlessRequest(
            run_results_ref=str(current_path),
            baseline_ref=str(golden_path),
        )
    )

    # Must produce per-node verdicts, NOT degrade to a single run-level node.
    assert [node.node_id for node in result.node_results] == ["draft", "review"]
    assert [node.node_id for node in result.node_results] != ["output"]
    draft = result.node_results[0]
    review = result.node_results[1]
    assert draft.verdict == "fail"
    assert draft.score < 1
    assert draft.differences[0].field_path == "nodes.draft.answer"
    assert review.verdict == "pass"
    assert review.score == 1
    assert review.differences == []


def _contains_computed_string(source: str, expected: str) -> bool:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        value = _static_string_value(node)
        if value == expected:
            return True
    return False


def _static_string_value(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _static_string_value(node.left)
        right = _static_string_value(node.right)
        if left is not None and right is not None:
            return left + right
    return None
