"""Service-layer tests for authored golden case content (write_golden_case_content).

Design basis: docs/studio/mvp1/02_capabilities/golden-eval/mvp1-alignment.md F6 —
golden 本身随时可写(手填/copilot 设计), run 输出只是默认种子;
decision doc: .kiro/specs/studio-moirai-agent-system/
decision-2026-08-07-golden-case-authoring.md (D-1).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from app.services.golden_diff import (
    read_golden_baseline_content,
    set_golden_baseline_for_run,
    write_golden_case_content,
)
from app.services.skills import resolve_skill_dir
from fastapi import HTTPException
from graph_agent.core.result_contracts import NodeRunResult, RunResultSnapshot, RunResultsRef

SKILL = "text-segmentation"


def _seal_run_snapshot(skill_id: str, run_id: str, node_outputs: dict[str, dict[str, Any]]) -> None:
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore

    run_dir = resolve_skill_dir(skill_id) / ".workspace" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    store = LocalRunArtifactStore(root=run_dir.parent.parent)
    object_payloads = {
        f"nodes/{node_id}/outputs.json": json.dumps(outputs).encode("utf-8")
        for node_id, outputs in node_outputs.items()
    }
    snapshot = RunResultSnapshot(
        run_results_ref=RunResultsRef(
            run_id=run_id,
            uri=f"{skill_id}/runs/{run_id}/result.json",
            content_hash="sha256:" + ("0" * 64),
        ),
        node_results=[
            NodeRunResult(
                agent_node_id=node_id,
                status="success",
                outputs_ref=f"{skill_id}/runs/{run_id}/nodes/{node_id}/outputs.json",
                trace_refs=[f"{skill_id}/runs/{run_id}/trace/{node_id}.jsonl"],
            )
            for node_id in node_outputs
        ],
        status="success",
        outputs_ref=f"{skill_id}/runs/{run_id}/outputs.json",
        trace_refs=[f"{skill_id}/runs/{run_id}/trace.jsonl"],
    )
    object_payloads["result.json"] = snapshot.model_dump_json().encode("utf-8")
    store.begin_run(run_id, metadata={"artifact_id": skill_id})
    store.put_batch(run_id, object_payloads)
    store.seal_run(run_id)


def _seed_baseline(run_id: str, *, lock: bool = False) -> None:
    _seal_run_snapshot(
        SKILL,
        run_id,
        {"setup": {"answer": "alpha"}, "review": {"score": 7}},
    )
    set_golden_baseline_for_run(SKILL, run_id, lock=lock)


def _case_file(run_id: str, node_id: str) -> dict[str, Any]:
    path = resolve_skill_dir(SKILL) / ".workspace" / "golden" / run_id / "cases" / f"{node_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_write_replaces_expected_output_and_marks_authored(
    studio_roots: tuple[Path, Path],
) -> None:
    """The authored content becomes the golden truth and carries its provenance."""
    del studio_roots
    _seed_baseline("author-run")
    authored = {"score": 9, "verdict": "hand-corrected"}

    case = write_golden_case_content(SKILL, "author-run", "review", authored)

    assert case.node_id == "review"
    assert case.expected_output == authored
    content = read_golden_baseline_content(SKILL, "author-run", node_id="review")
    assert content.cases[0].expected_output == authored
    on_disk = _case_file("author-run", "review")
    assert on_disk["origin"] == "authored"
    assert isinstance(on_disk["authored_at"], str) and on_disk["authored_at"]


def test_write_does_not_touch_sibling_case_files(
    studio_roots: tuple[Path, Path],
) -> None:
    """Editing one node's golden leaves the sibling's run-promoted case byte-identical."""
    del studio_roots
    _seed_baseline("sibling-run")
    sibling_before = _case_file("sibling-run", "setup")

    write_golden_case_content(SKILL, "sibling-run", "review", {"score": 1})

    assert _case_file("sibling-run", "setup") == sibling_before
    assert "origin" not in sibling_before


def test_write_missing_baseline_is_404(studio_roots: tuple[Path, Path]) -> None:
    del studio_roots

    with pytest.raises(HTTPException) as exc_info:
        write_golden_case_content(SKILL, "ghost-baseline", "review", {"score": 1})

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error_code"] == "golden.baseline_not_found"


def test_write_locked_baseline_is_409(studio_roots: tuple[Path, Path]) -> None:
    """A locked baseline is the first write path where the lock actually bites."""
    del studio_roots
    _seed_baseline("locked-run", lock=True)

    with pytest.raises(HTTPException) as exc_info:
        write_golden_case_content(SKILL, "locked-run", "review", {"score": 1})

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error_code"] == "golden.baseline_locked"


def test_write_node_without_case_is_422(studio_roots: tuple[Path, Path]) -> None:
    """Edit semantics: only nodes that already hold a case in this baseline are writable."""
    del studio_roots
    _seed_baseline("no-case-run")

    with pytest.raises(HTTPException) as exc_info:
        write_golden_case_content(SKILL, "no-case-run", "ghost-node", {"score": 1})

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error_code"] == "golden.case_not_found"


def test_write_empty_expected_output_is_422(studio_roots: tuple[Path, Path]) -> None:
    """An empty object would silently gut the eval — reject at the write boundary."""
    del studio_roots
    _seed_baseline("empty-run")

    with pytest.raises(HTTPException) as exc_info:
        write_golden_case_content(SKILL, "empty-run", "review", {})

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error_code"] == "golden.invalid_expected_output"
