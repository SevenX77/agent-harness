"""Service-layer tests for per-node golden write + cases projection + merge.

Design basis: docs/studio/mvp1/02_capabilities/golden-eval/mvp1-alignment.md
- GOLDEN_EVAL-1: golden = one agent node's expected output, not a whole-run snapshot.
- F6: per-node write must not clobber sibling nodes; predict fake data stays 409;
  a valid golden is not auto-overwritten by writing a different node.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from app.services.golden_diff import (
    list_golden_baselines_for_skill,
    plan_golden_baseline_for_run,
    set_golden_baseline_for_run,
)
from app.services.skills import resolve_skill_dir
from fastapi import HTTPException
from graph_agent.core.result_contracts import NodeRunResult, RunResultSnapshot, RunResultsRef


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


def _read_baseline(skill_id: str, golden_id: str) -> dict[str, Any]:
    path = resolve_skill_dir(skill_id) / ".workspace" / "golden" / golden_id / "baseline.json"
    return json.loads(path.read_text(encoding="utf-8"))


SKILL = "text-segmentation"


def test_plan_with_node_id_emits_only_that_nodes_case(
    studio_roots: tuple[Path, Path],
) -> None:
    """A node-scoped plan emits exactly one case + one case file for the named node."""
    del studio_roots
    _seal_run_snapshot(
        SKILL,
        "node-plan-run",
        {"setup": {"answer": "alpha"}, "review": {"score": 7}},
    )

    plan = plan_golden_baseline_for_run(SKILL, "node-plan-run", lock=False, node_id="review")

    case_node_ids = [case.node_id for case in plan.baseline.cases]
    assert case_node_ids == ["review"]
    case_file_paths = [f.path for f in plan.files if f.path.endswith(".json") and "/cases/" in f.path]
    assert case_file_paths == [".workspace/golden/node-plan-run/cases/review.json"]


def test_set_with_node_id_then_other_node_merges_not_clobbers(
    studio_roots: tuple[Path, Path],
) -> None:
    """Writing node B after node A keeps A's golden case on disk (F6: per-node merge)."""
    del studio_roots
    _seal_run_snapshot(
        SKILL,
        "merge-run",
        {"setup": {"answer": "alpha"}, "review": {"score": 7}},
    )

    set_golden_baseline_for_run(SKILL, "merge-run", lock=False, node_id="setup")
    set_golden_baseline_for_run(SKILL, "merge-run", lock=False, node_id="review")

    golden_dir = resolve_skill_dir(SKILL) / ".workspace" / "golden" / "merge-run"
    assert (golden_dir / "cases" / "setup.json").exists()
    assert (golden_dir / "cases" / "review.json").exists()
    baseline = _read_baseline(SKILL, "merge-run")
    case_node_ids = sorted(case["node_id"] for case in baseline["cases"])
    assert case_node_ids == ["review", "setup"]


def test_set_single_node_does_not_write_sibling_cases(
    studio_roots: tuple[Path, Path],
) -> None:
    """A first node-scoped write must not eagerly materialize sibling node cases."""
    del studio_roots
    _seal_run_snapshot(
        SKILL,
        "single-run",
        {"setup": {"answer": "alpha"}, "review": {"score": 7}},
    )

    set_golden_baseline_for_run(SKILL, "single-run", lock=False, node_id="setup")

    golden_dir = resolve_skill_dir(SKILL) / ".workspace" / "golden" / "single-run"
    assert (golden_dir / "cases" / "setup.json").exists()
    assert not (golden_dir / "cases" / "review.json").exists()
    baseline = _read_baseline(SKILL, "single-run")
    assert [case["node_id"] for case in baseline["cases"]] == ["setup"]


def test_set_without_node_id_keeps_whole_run_behavior(
    studio_roots: tuple[Path, Path],
) -> None:
    """Omitting node_id promotes every node (run-as-seed default), unchanged contract."""
    del studio_roots
    _seal_run_snapshot(
        SKILL,
        "whole-run",
        {"setup": {"answer": "alpha"}, "review": {"score": 7}},
    )

    set_golden_baseline_for_run(SKILL, "whole-run", lock=False)

    baseline = _read_baseline(SKILL, "whole-run")
    assert sorted(case["node_id"] for case in baseline["cases"]) == ["review", "setup"]


def test_list_baselines_projects_cases(
    studio_roots: tuple[Path, Path],
) -> None:
    """GET-source listing projects per-node cases for the three-state badge."""
    del studio_roots
    _seal_run_snapshot(
        SKILL,
        "list-run",
        {"setup": {"answer": "alpha"}, "review": {"score": 7}},
    )
    set_golden_baseline_for_run(SKILL, "list-run", lock=False)

    baselines = list_golden_baselines_for_skill(SKILL)

    assert len(baselines) == 1
    case_node_ids = sorted(case.node_id for case in baselines[0].cases)
    assert case_node_ids == ["review", "setup"]


def test_plan_with_unknown_node_id_is_rejected(
    studio_roots: tuple[Path, Path],
) -> None:
    """A node_id absent from the sealed run cannot be promoted to golden."""
    del studio_roots
    _seal_run_snapshot(SKILL, "unknown-node-run", {"setup": {"answer": "alpha"}})

    with pytest.raises(HTTPException) as exc_info:
        plan_golden_baseline_for_run(SKILL, "unknown-node-run", lock=False, node_id="ghost")

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error_code"] == "golden.node_not_in_run"
