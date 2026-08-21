"""Seeding fills the goldens a skill does not usably have, and touches nothing else.

Design basis: docs/studio/mvp1/02_capabilities/golden-eval/mvp1-alignment.md F6 —
"agent 节点**无 golden / 空模板 / 坏文件(schema 完全不符)**时,默认用该节点 Run 输出填充、
在其上编辑;**已有有效 golden 不被 Run 自动覆盖**".

The three unusable shapes are one question with one answer: a case is usable when it
resolves to a dict ``expected_output``. Absent record, missing file and non-dict payload
are the same verdict, so the seeder and the diff read them through the same resolver.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.golden_diff import (
    list_golden_baselines_for_skill,
    plan_golden_seed_for_run,
    seed_golden_baseline_for_run,
    set_golden_baseline_for_run,
)
from app.services.skills import resolve_skill_dir
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


def _golden_dir(skill_id: str, golden_id: str) -> Path:
    return resolve_skill_dir(skill_id) / ".workspace" / "golden" / golden_id


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def test_seed_writes_a_case_for_every_node_that_never_had_one(
    studio_roots: tuple[Path, Path],
) -> None:
    """A skill with no golden at all gets one case per node of the finished run."""
    del studio_roots
    _seal_run_snapshot(SKILL, "seed-first", {"setup": {"answer": "alpha"}, "review": {"score": 7}})

    result = seed_golden_baseline_for_run(SKILL, "seed-first")

    assert sorted(target.node_id for target in result.seeded) == ["review", "setup"]
    assert all(target.reason == "absent" for target in result.seeded)
    cases = _golden_dir(SKILL, "seed-first") / "cases"
    assert _read_json(cases / "setup.json")["expected_output"] == {"answer": "alpha"}
    assert _read_json(cases / "review.json")["expected_output"] == {"score": 7}


def test_seed_leaves_a_usable_case_byte_for_byte_alone(
    studio_roots: tuple[Path, Path],
) -> None:
    """A valid golden is not auto-overwritten, however different this run's output is."""
    del studio_roots
    _seal_run_snapshot(SKILL, "seed-base", {"setup": {"answer": "alpha"}, "review": {"score": 7}})
    set_golden_baseline_for_run(SKILL, "seed-base", lock=False, node_id="setup")
    kept = (_golden_dir(SKILL, "seed-base") / "cases" / "setup.json").read_bytes()

    _seal_run_snapshot(SKILL, "seed-later", {"setup": {"answer": "DIFFERENT"}, "review": {"score": 1}})
    result = seed_golden_baseline_for_run(SKILL, "seed-later")

    assert [target.node_id for target in result.seeded] == ["review"]
    assert (_golden_dir(SKILL, "seed-base") / "cases" / "setup.json").read_bytes() == kept


def test_seed_refills_a_case_whose_file_went_missing(
    studio_roots: tuple[Path, Path],
) -> None:
    """A record pointing at a file that is not there is not a golden — refill it."""
    del studio_roots
    _seal_run_snapshot(SKILL, "seed-missing", {"setup": {"answer": "alpha"}})
    set_golden_baseline_for_run(SKILL, "seed-missing", lock=False)
    (_golden_dir(SKILL, "seed-missing") / "cases" / "setup.json").unlink()

    _seal_run_snapshot(SKILL, "seed-missing-2", {"setup": {"answer": "refilled"}})
    result = seed_golden_baseline_for_run(SKILL, "seed-missing-2")

    assert [(t.node_id, t.reason) for t in result.seeded] == [("setup", "case_file_missing")]
    case = _golden_dir(SKILL, "seed-missing") / "cases" / "setup.json"
    assert _read_json(case)["expected_output"] == {"answer": "refilled"}


def test_seed_refills_a_case_whose_expected_output_is_not_an_object(
    studio_roots: tuple[Path, Path],
) -> None:
    """An empty template / schema-mismatched file is refilled rather than skipped."""
    del studio_roots
    _seal_run_snapshot(SKILL, "seed-empty", {"setup": {"answer": "alpha"}})
    set_golden_baseline_for_run(SKILL, "seed-empty", lock=False)
    case = _golden_dir(SKILL, "seed-empty") / "cases" / "setup.json"
    case.write_text(json.dumps({"case_id": "setup", "node_id": "setup"}), encoding="utf-8")

    _seal_run_snapshot(SKILL, "seed-empty-2", {"setup": {"answer": "refilled"}})
    result = seed_golden_baseline_for_run(SKILL, "seed-empty-2")

    assert [(t.node_id, t.reason) for t in result.seeded] == [("setup", "expected_output_invalid")]
    assert _read_json(case)["expected_output"] == {"answer": "refilled"}


def test_seed_fills_the_baseline_the_skill_already_has(
    studio_roots: tuple[Path, Path],
) -> None:
    """Seeding adds cases to the live baseline instead of starting a rival one."""
    del studio_roots
    _seal_run_snapshot(SKILL, "seed-into", {"setup": {"answer": "alpha"}, "review": {"score": 7}})
    set_golden_baseline_for_run(SKILL, "seed-into", lock=False, node_id="setup")

    _seal_run_snapshot(SKILL, "seed-into-2", {"setup": {"answer": "x"}, "review": {"score": 9}})
    seed_golden_baseline_for_run(SKILL, "seed-into-2")

    baselines = list_golden_baselines_for_skill(SKILL)
    assert [baseline.id for baseline in baselines] == ["seed-into"]
    assert sorted(case.node_id for case in baselines[0].cases) == ["review", "setup"]
    assert not _golden_dir(SKILL, "seed-into-2").exists()


def test_a_seeded_case_records_the_run_it_came_from(
    studio_roots: tuple[Path, Path],
) -> None:
    """The baseline names one source run, so each case has to name its own."""
    del studio_roots
    _seal_run_snapshot(SKILL, "seed-origin", {"setup": {"answer": "alpha"}, "review": {"score": 7}})
    set_golden_baseline_for_run(SKILL, "seed-origin", lock=False, node_id="setup")

    _seal_run_snapshot(SKILL, "seed-origin-2", {"setup": {"answer": "x"}, "review": {"score": 9}})
    seed_golden_baseline_for_run(SKILL, "seed-origin-2")

    cases = _golden_dir(SKILL, "seed-origin") / "cases"
    assert _read_json(cases / "setup.json")["source_run_id"] == "seed-origin"
    assert _read_json(cases / "review.json")["source_run_id"] == "seed-origin-2"


def test_seed_plan_writes_nothing_and_targets_the_live_baseline(
    studio_roots: tuple[Path, Path],
) -> None:
    """The native-fs writer gets the same decision as a plan, without side effects."""
    del studio_roots
    _seal_run_snapshot(SKILL, "seed-plan", {"setup": {"answer": "alpha"}, "review": {"score": 7}})
    set_golden_baseline_for_run(SKILL, "seed-plan", lock=False, node_id="setup")

    _seal_run_snapshot(SKILL, "seed-plan-2", {"setup": {"answer": "x"}, "review": {"score": 9}})
    plan = plan_golden_seed_for_run(SKILL, "seed-plan-2")

    assert [target.node_id for target in plan.seeded] == ["review"]
    case_paths = [file.path for file in plan.files if "/cases/" in file.path]
    assert case_paths == [".workspace/golden/seed-plan/cases/review.json"]
    assert not (_golden_dir(SKILL, "seed-plan") / "cases" / "review.json").exists()


def test_seed_with_nothing_to_fill_writes_no_files(
    studio_roots: tuple[Path, Path],
) -> None:
    """Every node already usable means the run changes nothing on disk."""
    del studio_roots
    _seal_run_snapshot(SKILL, "seed-full", {"setup": {"answer": "alpha"}})
    set_golden_baseline_for_run(SKILL, "seed-full", lock=False)
    before = (_golden_dir(SKILL, "seed-full") / "cases" / "setup.json").read_bytes()

    _seal_run_snapshot(SKILL, "seed-full-2", {"setup": {"answer": "x"}})
    result = seed_golden_baseline_for_run(SKILL, "seed-full-2")

    assert result.seeded == []
    assert result.files == []
    assert (_golden_dir(SKILL, "seed-full") / "cases" / "setup.json").read_bytes() == before


def test_a_plan_file_carries_the_hash_it_was_computed_from(
    studio_roots: tuple[Path, Path],
) -> None:
    """A plan file says what it expects to find, so the writer can refuse a surprise.

    The desktop writer is the Rust native-fs layer, and "create only if absent" was the
    only mode it was ever asked for — which silently made refilling a broken case
    impossible, because that file exists (ledger K1). A plan file that already has
    content on disk must therefore carry that content's hash; one that has none carries
    null, which is the writer's create-if-absent case.
    """
    del studio_roots
    _seal_run_snapshot(SKILL, "seed-hash-base", {"setup": {"answer": "alpha"}, "review": {"score": 7}})
    set_golden_baseline_for_run(SKILL, "seed-hash-base", lock=False, node_id="setup")
    broken = _golden_dir(SKILL, "seed-hash-base") / "cases" / "setup.json"
    broken.write_text(json.dumps({"case_id": "setup", "expected_output": "not an object"}), encoding="utf-8")

    _seal_run_snapshot(SKILL, "seed-hash-later", {"setup": {"answer": "beta"}, "review": {"score": 9}})
    plan = plan_golden_seed_for_run(SKILL, "seed-hash-later")

    by_path = {file.path: file for file in plan.files}
    setup_case = by_path[".workspace/golden/seed-hash-base/cases/setup.json"]
    review_case = by_path[".workspace/golden/seed-hash-base/cases/review.json"]
    baseline_file = by_path[".workspace/golden/seed-hash-base/baseline.json"]

    # setup.json is on disk (broken) → the plan reports the hash it read.
    assert setup_case.expected_hash == _workspace_text_hash(broken.read_text(encoding="utf-8"))
    # review.json has never existed → nothing to expect.
    assert review_case.expected_hash is None
    # baseline.json always exists once a baseline does — the case the old mode could
    # never write.
    baseline_path = _golden_dir(SKILL, "seed-hash-base") / "baseline.json"
    assert baseline_file.expected_hash == _workspace_text_hash(baseline_path.read_text(encoding="utf-8"))


def _workspace_text_hash(text: str) -> str:
    """The hash the Rust writer computes: sha256 over LF-normalized text."""
    import hashlib

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
