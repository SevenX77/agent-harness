from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from graph_agent.core.result_contracts import GoldenInputRef, NodeRunResult, RunResultSnapshot, RunResultsRef

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


def test_golden_headless_request_is_engine_golden_input_ref_contract() -> None:
    from app.services.golden_headless import GoldenHeadlessRequest

    assert GoldenHeadlessRequest is GoldenInputRef

    request = GoldenHeadlessRequest(
        run_results_ref=RunResultsRef(
            run_id="run-123",
            uri="demo.skill/runs/run-123/result.json",
            content_hash="sha256:" + ("0" * 64),
        ),
        baseline_ref="demo.skill/golden/golden-123/baseline.json",
    )

    assert request.run_results_ref.uri == "demo.skill/runs/run-123/result.json"
    assert request.baseline_ref == "demo.skill/golden/golden-123/baseline.json"


def test_golden_headless_reads_run_result_snapshot_refs_and_returns_node_groups(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.golden_headless import evaluate_golden_headless

    current_ref = _write_sealed_snapshot(
        tmp_path,
        monkeypatch,
        run_id="current-snapshot",
        node_outputs={
            "draft": {"answer": "hello studio", "ok": True},
            "review": {"score": 10},
        },
    )
    baseline_ref = _write_baseline_contract(
        tmp_path,
        baseline_id="golden-snapshot",
        source_run_id="golden-run",
        source_run_results_ref="demo.skill/runs/golden-run/result.json",
        cases={
            "draft": {"answer": "hello world", "ok": True},
            "review": {"score": 10},
        },
    )

    result = evaluate_golden_headless(
        _headless_request(current_ref, baseline_ref)
    )

    assert result.baseline_id == "golden-snapshot"
    assert result.source_run_id == "golden-run"
    assert result.source_run_results_ref == "demo.skill/runs/golden-run/result.json"
    assert result.run_results_ref == current_ref
    assert result.baseline_ref == baseline_ref
    assert [group.node_id for group in result.node_groups] == ["draft", "review"]
    assert [group.phase_id for group in result.node_groups] == ["draft", "review"]
    assert result.node_groups[0].status == "fail"
    assert result.node_groups[0].field_differences[0].field_path == "nodes.draft.answer"
    assert result.node_groups[0].baseline_ref == baseline_ref
    assert result.node_groups[0].run_results_ref == current_ref
    assert result.node_groups[1].status == "pass"
    assert result.node_groups[1].field_differences == []
    assert not hasattr(result, "node_results")


def test_golden_headless_rejects_baseline_payload_id_that_drifts_from_baseline_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.golden_headless import evaluate_golden_headless

    current_ref = _write_sealed_snapshot(
        tmp_path,
        monkeypatch,
        run_id="current-run",
        node_outputs={"draft": {"answer": "hello studio"}},
    )
    baseline_ref = _write_baseline_contract(
        tmp_path,
        baseline_id="golden-path-id",
        source_run_id="golden-source",
        source_run_results_ref="demo.skill/runs/golden-source/result.json",
        cases={"draft": {"answer": "hello world"}},
    )
    baseline_path = Path(baseline_ref)
    baseline_payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline_payload["baseline_id"] = "golden-payload-id"
    baseline_path.write_text(json.dumps(baseline_payload), encoding="utf-8")

    with pytest.raises(HTTPException) as exc_info:
        evaluate_golden_headless(_headless_request(current_ref, baseline_ref))

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error_code"] == "golden.baseline_invalid"
    assert exc_info.value.detail["details"] == {
        "ref": baseline_ref,
        "field": "baseline_id",
        "expected_baseline_id": "golden-path-id",
        "embedded_baseline_id": "golden-payload-id",
    }


def test_golden_headless_request_from_ref_rejects_embedded_cross_skill_run_results_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.golden_headless import golden_headless_request_from_ref

    current_ref = _write_sealed_snapshot_with_refs(
        tmp_path,
        monkeypatch,
        run_id="current-run",
        embedded_run_results_ref="foreign.skill/runs/foreign-run/result.json",
        node_output_refs={"draft": "demo.skill/runs/current-run/nodes/draft/outputs.json"},
        node_outputs={"draft": {"answer": "current output"}},
    )

    with pytest.raises(HTTPException) as exc_info:
        golden_headless_request_from_ref(
            current_ref,
            "demo.skill/golden/golden-run/baseline.json",
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error_code"] == "golden.run_result_invalid"
    assert exc_info.value.detail["details"]["ref"] == current_ref
    assert exc_info.value.detail["details"]["embedded_ref"] == "foreign.skill/runs/foreign-run/result.json"


def test_golden_headless_rejects_embedded_cross_skill_outputs_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore
    from app.services.golden_headless import evaluate_golden_headless

    current_ref = _write_sealed_snapshot_with_refs(
        tmp_path,
        monkeypatch,
        run_id="current-run",
        embedded_run_results_ref="demo.skill/runs/current-run/result.json",
        node_output_refs={"draft": "foreign.skill/runs/foreign-run/nodes/draft/outputs.json"},
        node_outputs={"draft": {"answer": "current output"}},
    )
    skill_dir = _prepare_demo_skill_dir(tmp_path, monkeypatch)
    store = LocalRunArtifactStore(root=skill_dir / ".workspace")
    store.begin_run("foreign-run", metadata={"artifact_id": "foreign.skill"})
    store.put_batch(
        "foreign-run",
        {"nodes/draft/outputs.json": json.dumps({"answer": "foreign output"}).encode("utf-8")},
    )
    store.seal_run("foreign-run")
    baseline_ref = _write_baseline_contract(
        tmp_path,
        baseline_id="golden-current",
        source_run_id="source-run",
        source_run_results_ref="demo.skill/runs/source-run/result.json",
        cases={"draft": {"answer": "current output"}},
    )

    with pytest.raises(HTTPException) as exc_info:
        evaluate_golden_headless(
            _headless_request(current_ref, baseline_ref)
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error_code"] == "golden.run_result_invalid"
    assert exc_info.value.detail["details"]["ref"] == current_ref
    assert exc_info.value.detail["details"]["embedded_ref"] == "foreign.skill/runs/foreign-run/nodes/draft/outputs.json"


def test_golden_headless_rejects_embedded_same_skill_different_run_outputs_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.golden_headless import evaluate_golden_headless

    current_ref = _write_sealed_snapshot_with_refs(
        tmp_path,
        monkeypatch,
        run_id="current-run",
        embedded_run_results_ref="demo.skill/runs/current-run/result.json",
        node_output_refs={"draft": "demo.skill/runs/other-run/nodes/draft/outputs.json"},
        node_outputs={"draft": {"answer": "current output"}},
    )
    baseline_ref = _write_baseline_contract(
        tmp_path,
        baseline_id="golden-current",
        source_run_id="source-run",
        source_run_results_ref="demo.skill/runs/source-run/result.json",
        cases={"draft": {"answer": "current output"}},
    )

    with pytest.raises(HTTPException) as exc_info:
        evaluate_golden_headless(
            _headless_request(current_ref, baseline_ref)
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error_code"] == "golden.run_result_invalid"
    assert exc_info.value.detail["details"]["ref"] == current_ref
    assert exc_info.value.detail["details"]["embedded_ref"] == "demo.skill/runs/other-run/nodes/draft/outputs.json"
    assert exc_info.value.detail["details"]["field"] == "node_results.outputs_ref"
    assert exc_info.value.detail["details"]["expected_skill_id"] == "demo.skill"
    assert exc_info.value.detail["details"]["expected_run_id"] == "current-run"
    assert exc_info.value.detail["details"]["embedded_skill_id"] == "demo.skill"
    assert exc_info.value.detail["details"]["embedded_run_id"] == "other-run"


def test_golden_headless_rejects_embedded_absolute_outputs_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.golden_headless import evaluate_golden_headless

    absolute_ref = str(tmp_path / "outside" / "outputs.json")
    current_ref = _write_sealed_snapshot_with_refs(
        tmp_path,
        monkeypatch,
        run_id="current-run",
        embedded_run_results_ref="demo.skill/runs/current-run/result.json",
        node_output_refs={"draft": absolute_ref},
        node_outputs={"draft": {"answer": "current output"}},
    )
    baseline_ref = _write_baseline_contract(
        tmp_path,
        baseline_id="golden-current",
        source_run_id="source-run",
        source_run_results_ref="demo.skill/runs/source-run/result.json",
        cases={"draft": {"answer": "current output"}},
    )

    with pytest.raises(HTTPException) as exc_info:
        evaluate_golden_headless(
            _headless_request(current_ref, baseline_ref)
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error_code"] == "golden.run_result_invalid"
    assert exc_info.value.detail["details"]["ref"] == current_ref
    assert exc_info.value.detail["details"]["embedded_ref"] == absolute_ref
    assert exc_info.value.detail["details"]["field"] == "node_results.outputs_ref"


def test_golden_headless_accepts_embedded_safe_relative_outputs_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.golden_headless import evaluate_golden_headless

    current_ref = _write_sealed_snapshot_with_refs(
        tmp_path,
        monkeypatch,
        run_id="current-run",
        embedded_run_results_ref="demo.skill/runs/current-run/result.json",
        node_output_refs={"draft": "nodes/draft/outputs.json"},
        node_outputs={"draft": {"answer": "current output"}},
    )
    baseline_ref = _write_baseline_contract(
        tmp_path,
        baseline_id="golden-current",
        source_run_id="source-run",
        source_run_results_ref="demo.skill/runs/source-run/result.json",
        cases={"draft": {"answer": "current output"}},
    )

    result = evaluate_golden_headless(
        _headless_request(current_ref, baseline_ref)
    )

    assert result.total_score == 100
    assert result.node_groups[0].node_id == "draft"
    assert result.node_groups[0].status == "pass"
    assert result.node_groups[0].field_differences == []


def test_golden_headless_rejects_whole_run_payload_without_snapshot_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.golden_headless import evaluate_golden_headless

    current_ref = _write_sealed_current_result(
        tmp_path,
        monkeypatch,
        run_id="current-whole-run",
        payload={"phase_outputs": {"draft": {"answer": "legacy whole-run shape"}}},
    )
    baseline_ref = _write_baseline_contract(
        tmp_path,
        baseline_id="golden-whole-run",
        source_run_id="golden-run",
        source_run_results_ref="demo.skill/runs/golden-run/result.json",
        cases={"draft": {"answer": "legacy whole-run shape"}},
    )

    with pytest.raises(HTTPException) as exc_info:
        evaluate_golden_headless(
            _headless_request(current_ref, baseline_ref)
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error_code"] == "golden.run_result_invalid"
    assert exc_info.value.detail["details"]["ref"] == current_ref


def test_golden_headless_missing_baseline_returns_golden_baseline_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.golden_headless import evaluate_golden_headless

    current_ref = _write_sealed_snapshot(
        tmp_path,
        monkeypatch,
        run_id="current-missing-baseline",
        node_outputs={"draft": {"answer": "hello"}},
    )
    missing_baseline = str(tmp_path / "golden" / "missing" / "baseline.json")

    with pytest.raises(HTTPException) as exc_info:
        evaluate_golden_headless(
            _headless_request(current_ref, missing_baseline)
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error_code"] == "golden.baseline_not_found"
    assert exc_info.value.detail["details"]["ref"] == missing_baseline


@pytest.mark.parametrize(
    "case_ref_kind",
    ["absolute", "parent", "sibling"],
)
def test_golden_headless_rejects_case_refs_outside_baseline_cases_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case_ref_kind: str,
) -> None:
    from app.services.golden_headless import evaluate_golden_headless

    current_ref = _write_sealed_snapshot(
        tmp_path,
        monkeypatch,
        run_id=f"current-baseline-escape-{case_ref_kind}",
        node_outputs={"draft": {"answer": "must not read escaped case"}},
    )
    baseline_dir = tmp_path / "golden" / f"escape-{case_ref_kind}"
    baseline_dir.mkdir(parents=True)
    if case_ref_kind == "absolute":
        case_ref = str(tmp_path / "outside-absolute.json")
        case_path = Path(case_ref)
    elif case_ref_kind == "parent":
        case_ref = "../outside-parent.json"
        case_path = baseline_dir.parent / "outside-parent.json"
    else:
        case_ref = "draft.json"
        case_path = baseline_dir / "draft.json"
    case_path.write_text(
        json.dumps(
            {
                "case_id": "draft",
                "node_id": "draft",
                "phase_id": "draft",
                "expected_output": {"answer": "must not read escaped case"},
            }
        ),
        encoding="utf-8",
    )
    baseline_path = baseline_dir / "baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "baseline_id": f"escape-{case_ref_kind}",
                "source_run_id": "source-run",
                "source_run_results_ref": "demo.skill/runs/source-run/result.json",
                "cases": [
                    {
                        "case_id": "draft",
                        "node_id": "draft",
                        "phase_id": "draft",
                        "expected_output_ref": case_ref,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(HTTPException) as exc_info:
        evaluate_golden_headless(
            _headless_request(current_ref, str(baseline_path))
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error_code"] == "golden.baseline_invalid"
    assert exc_info.value.detail["details"]["case_ref"] == case_ref


def test_golden_headless_returns_per_node_verdicts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.golden_headless import evaluate_golden_headless

    current_ref = _write_sealed_snapshot(
        tmp_path,
        monkeypatch,
        run_id="current-run",
        node_outputs={
            "setup": {"answer": "hello studio", "ok": True},
            "review": {"score": 10},
        },
    )
    baseline_ref = _write_baseline_contract(
        tmp_path,
        baseline_id="golden-run",
        source_run_id="golden-run",
        source_run_results_ref="demo.skill/runs/golden-run/result.json",
        cases={
            "setup": {"answer": "hello world", "ok": True},
            "review": {"score": 10},
        },
    )

    result = evaluate_golden_headless(
        _headless_request(current_ref, baseline_ref)
    )

    assert [node.node_id for node in result.node_groups] == ["setup", "review"]
    setup = result.node_groups[0]
    review = result.node_groups[1]
    assert setup.status == "fail"
    assert setup.score < 1
    assert setup.field_differences[0].field_path == "nodes.setup.answer"
    assert review.status == "pass"
    assert review.score == 1
    assert review.field_differences == []


def test_golden_headless_returns_per_node_verdicts_for_real_run_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real engine run/golden result is BusinessData {inputs, phase_outputs, scratch}.

    Per-node golden must derive nodes from the `phase_outputs` dict, not only from
    the synthetic top-level `phases` list. Without this, real runs silently degrade
    to a single run-level `output` verdict.
    """
    from app.services.golden_headless import evaluate_golden_headless

    current_ref = _write_sealed_snapshot(
        tmp_path,
        monkeypatch,
        run_id="current-real-shape",
        node_outputs={
            "draft": {"answer": "hello studio", "ok": True},
            "review": {"score": 10},
        },
    )
    baseline_ref = _write_baseline_contract(
        tmp_path,
        baseline_id="golden-real-shape",
        source_run_id="golden-real-shape",
        source_run_results_ref="demo.skill/runs/golden-real-shape/result.json",
        cases={
            "draft": {"answer": "hello world", "ok": True},
            "review": {"score": 10},
        },
    )

    result = evaluate_golden_headless(
        _headless_request(current_ref, baseline_ref)
    )

    # Must produce per-node verdicts, NOT degrade to a single run-level node.
    assert [node.node_id for node in result.node_groups] == ["draft", "review"]
    assert [node.node_id for node in result.node_groups] != ["output"]
    draft = result.node_groups[0]
    review = result.node_groups[1]
    assert draft.status == "fail"
    assert draft.score < 1
    assert draft.field_differences[0].field_path == "nodes.draft.answer"
    assert review.status == "pass"
    assert review.score == 1
    assert review.field_differences == []


def test_golden_headless_missing_result_ref_does_not_fallback_to_legacy_final_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore
    from app.services.golden_headless import evaluate_golden_headless

    skill_dir = _prepare_demo_skill_dir(tmp_path, monkeypatch)
    store = LocalRunArtifactStore(root=skill_dir / ".workspace")
    store.begin_run("current-final-state-only", metadata={"artifact_id": "demo.skill"})
    store.put_batch(
        "current-final-state-only",
        {
            "final_state.json": json.dumps(
                {"answer": "legacy fallback must not be live"}
            ).encode("utf-8")
        },
    )
    store.seal_run("current-final-state-only")

    golden_dir = tmp_path / "golden"
    golden_dir.mkdir()
    (golden_dir / "result.json").write_text(json.dumps({"answer": "golden"}), encoding="utf-8")
    current_ref = "demo.skill/runs/current-final-state-only/result.json"

    with pytest.raises(HTTPException) as exc_info:
        evaluate_golden_headless(
            _headless_request(current_ref, str(golden_dir / "result.json"))
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error_code"] == "golden.run_results_not_found"
    assert exc_info.value.detail["details"]["ref"] == current_ref


def test_golden_headless_rejects_current_run_result_from_mutable_run_dir_path(
    tmp_path: Path,
) -> None:
    from app.services.golden_headless import evaluate_golden_headless

    run_path = tmp_path / "demo.skill" / ".workspace" / "runs" / "run-mutable" / "result.json"
    golden_path = tmp_path / "demo.skill" / ".workspace" / "golden" / "golden-run" / "result.json"
    run_path.parent.mkdir(parents=True)
    golden_path.parent.mkdir(parents=True)
    run_path.write_text(
        json.dumps({"phase_outputs": {"draft": {"answer": "mutable run file"}}}),
        encoding="utf-8",
    )
    golden_path.write_text(
        json.dumps({"phase_outputs": {"draft": {"answer": "mutable run file"}}}),
        encoding="utf-8",
    )

    with pytest.raises(HTTPException) as exc_info:
        evaluate_golden_headless(
            _headless_request(str(run_path), str(golden_path))
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error_code"] == "golden.run_results_mutable_ref"
    assert exc_info.value.detail["details"]["ref"] == str(run_path)


def test_golden_headless_rejects_current_run_result_from_plain_file_path(
    tmp_path: Path,
) -> None:
    from app.services.golden_headless import evaluate_golden_headless

    current_path = tmp_path / "current" / "result.json"
    golden_path = tmp_path / "golden" / "result.json"
    current_path.parent.mkdir()
    golden_path.parent.mkdir()
    current_path.write_text(
        json.dumps({"phase_outputs": {"draft": {"answer": "plain file current"}}}),
        encoding="utf-8",
    )
    golden_path.write_text(
        json.dumps({"phase_outputs": {"draft": {"answer": "plain file current"}}}),
        encoding="utf-8",
    )

    with pytest.raises(HTTPException) as exc_info:
        evaluate_golden_headless(
            _headless_request(str(current_path), str(golden_path))
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error_code"] == "golden.run_result_invalid"
    assert exc_info.value.detail["details"]["ref"] == str(current_path)


def test_golden_headless_reads_run_result_from_sealed_run_artifact_store_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config
    from app.services import skills as skills_service
    from app.services.golden_headless import evaluate_golden_headless

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    skill_dir = tmp_path / "workspaces" / "default" / "skills" / "demo.skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")
    monkeypatch.setattr(skills_service, "resolve_skill_dir", lambda _skill_id: skill_dir)

    current_ref = _write_sealed_snapshot(
        tmp_path,
        monkeypatch,
        run_id="run-store-golden",
        node_outputs={"draft": {"answer": "sealed store"}},
    )
    baseline_ref = _write_baseline_contract(
        tmp_path,
        baseline_id="golden-store",
        source_run_id="golden-store",
        source_run_results_ref="demo.skill/runs/golden-store/result.json",
        cases={"draft": {"answer": "sealed store"}},
    )

    result = evaluate_golden_headless(
        _headless_request(current_ref, baseline_ref)
    )

    assert result.total_score == 100
    assert result.node_groups[0].status == "pass"
    assert result.node_groups[0].field_differences == []


def test_golden_headless_exposes_run_artifact_hash_mismatch_without_legacy_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore
    from app.services import skills as skills_service
    from app.services.golden_headless import evaluate_golden_headless

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    skill_dir = tmp_path / "workspaces" / "default" / "skills" / "demo.skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")
    monkeypatch.setattr(skills_service, "resolve_skill_dir", lambda _skill_id: skill_dir)

    run_dir = skill_dir / ".workspace" / "runs" / "run-corrupt-golden"
    run_dir.mkdir(parents=True)
    (run_dir / "result.json").write_text(
        json.dumps({"phase_outputs": {"draft": {"answer": "legacy fallback"}}}),
        encoding="utf-8",
    )
    store = LocalRunArtifactStore(root=skill_dir / ".workspace")
    refs = store.put_batch(
        "run-corrupt-golden",
        {
            "result.json": json.dumps(
                {"phase_outputs": {"draft": {"answer": "sealed store"}}}
            ).encode("utf-8")
        },
    )
    ref = refs["result.json"] if isinstance(refs, dict) else refs[0]
    store.seal_run("run-corrupt-golden")
    sha_val = ref.content_hash.split(":", 1)[1]
    (skill_dir / ".workspace" / "blobs" / sha_val).write_bytes(b"corrupted")

    golden_path = tmp_path / "golden" / "result.json"
    golden_path.parent.mkdir()
    golden_path.write_text(
        json.dumps({"phase_outputs": {"draft": {"answer": "sealed store"}}}),
        encoding="utf-8",
    )

    with pytest.raises(HTTPException) as exc_info:
        evaluate_golden_headless(
            _headless_request("demo.skill/runs/run-corrupt-golden/result.json", str(golden_path))
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error_code"] == "golden.hash_mismatch"
    assert exc_info.value.detail["details"]["run_id"] == "run-corrupt-golden"


def test_golden_headless_invalid_result_ref_returns_stable_error_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.golden_headless import evaluate_golden_headless

    golden_path = tmp_path / "golden" / "result.json"
    golden_path.parent.mkdir()
    current_ref = _write_sealed_current_object(
        tmp_path,
        monkeypatch,
        run_id="current-invalid-json",
        path="result.json",
        content=b"{not-json",
    )
    golden_path.write_text(json.dumps({"answer": "golden"}), encoding="utf-8")

    with pytest.raises(HTTPException) as exc_info:
        evaluate_golden_headless(
            _headless_request(current_ref, str(golden_path))
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error_code"] == "golden.run_result_invalid"
    assert exc_info.value.detail["details"]["ref"] == current_ref


def test_golden_headless_marks_schema_drift_stale_and_missing_nodes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.golden_headless import evaluate_golden_headless

    current_ref = _write_sealed_snapshot(
        tmp_path,
        monkeypatch,
        run_id="current-schema-drift",
        node_outputs={
            "draft": {"answer": {"text": "hello"}},
            "stale_only": {"value": "extra node"},
        },
    )
    baseline_ref = _write_baseline_contract(
        tmp_path,
        baseline_id="golden-schema-drift",
        source_run_id="golden-schema-drift",
        source_run_results_ref="demo.skill/runs/golden-schema-drift/result.json",
        cases={
            "draft": {"answer": "hello"},
            "missing_only": {"value": "required node"},
        },
    )

    result = evaluate_golden_headless(
        _headless_request(current_ref, baseline_ref)
    )

    nodes = {node.node_id: node for node in result.node_groups}
    assert set(nodes) == {"draft", "stale_only", "missing_only"}
    assert nodes["draft"].status == "fail"
    assert nodes["draft"].field_differences[0].field_path == "nodes.draft.answer"
    assert nodes["stale_only"].status == "fail"
    assert nodes["stale_only"].schema_status == "stale"
    assert nodes["stale_only"].field_differences[0].field_path.startswith("nodes.stale_only")
    assert nodes["missing_only"].status == "fail"
    assert nodes["missing_only"].schema_status == "missing"
    assert nodes["missing_only"].field_differences[0].field_path.startswith("nodes.missing_only")


def _headless_request(run_results_ref: str, baseline_ref: str) -> GoldenInputRef:
    from app.services.golden_headless import GoldenHeadlessRequest

    return GoldenHeadlessRequest(
        run_results_ref=RunResultsRef(
            run_id=_run_id_from_ref(run_results_ref),
            uri=run_results_ref,
            content_hash="sha256:" + ("0" * 64),
        ),
        baseline_ref=baseline_ref,
    )


def _run_id_from_ref(ref: str) -> str:
    parts = Path(ref).parts
    if "runs" in parts:
        index = parts.index("runs")
        if index + 1 < len(parts):
            return parts[index + 1]
    return Path(ref).parent.name or "unknown-run"


def _write_sealed_current_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    run_id: str,
    payload: object,
) -> str:
    return _write_sealed_current_object(
        tmp_path,
        monkeypatch,
        run_id=run_id,
        path="result.json",
    content=json.dumps(payload).encode("utf-8"),
    )


def _write_sealed_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    run_id: str,
    node_outputs: dict[str, object],
) -> str:
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore

    skill_dir = _prepare_demo_skill_dir(tmp_path, monkeypatch)
    store = LocalRunArtifactStore(root=skill_dir / ".workspace")
    run_results_ref = f"demo.skill/runs/{run_id}/result.json"
    object_payloads: dict[str, bytes] = {}
    node_results: list[NodeRunResult] = []
    for node_id, outputs in node_outputs.items():
        outputs_path = f"nodes/{node_id}/outputs.json"
        object_payloads[outputs_path] = json.dumps(outputs).encode("utf-8")
        node_results.append(
            NodeRunResult(
                agent_node_id=node_id,
                status="success",
                outputs_ref=f"demo.skill/runs/{run_id}/{outputs_path}",
                trace_refs=[f"demo.skill/runs/{run_id}/trace/{node_id}.jsonl"],
            )
        )
    snapshot = RunResultSnapshot(
        run_results_ref=RunResultsRef(
            run_id=run_id,
            uri=run_results_ref,
            content_hash="sha256:" + ("0" * 64),
        ),
        node_results=node_results,
        status="success",
        outputs_ref=f"demo.skill/runs/{run_id}/outputs.json",
        trace_refs=[f"demo.skill/runs/{run_id}/trace.jsonl"],
    )
    object_payloads["result.json"] = snapshot.model_dump_json().encode("utf-8")
    store.begin_run(run_id, metadata={"artifact_id": "demo.skill"})
    store.put_batch(run_id, object_payloads)
    store.seal_run(run_id)
    return run_results_ref


def _write_sealed_snapshot_with_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    run_id: str,
    embedded_run_results_ref: str,
    node_output_refs: dict[str, str],
    node_outputs: dict[str, object],
) -> str:
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore

    skill_dir = _prepare_demo_skill_dir(tmp_path, monkeypatch)
    store = LocalRunArtifactStore(root=skill_dir / ".workspace")
    run_results_ref = f"demo.skill/runs/{run_id}/result.json"
    object_payloads: dict[str, bytes] = {}
    node_results: list[NodeRunResult] = []
    for node_id, outputs in node_outputs.items():
        outputs_path = f"nodes/{node_id}/outputs.json"
        object_payloads[outputs_path] = json.dumps(outputs).encode("utf-8")
        node_results.append(
            NodeRunResult(
                agent_node_id=node_id,
                status="success",
                outputs_ref=node_output_refs[node_id],
                trace_refs=[f"demo.skill/runs/{run_id}/trace/{node_id}.jsonl"],
            )
        )
    snapshot = RunResultSnapshot(
        run_results_ref=RunResultsRef(
            run_id=_run_id_from_ref(embedded_run_results_ref),
            uri=embedded_run_results_ref,
            content_hash="sha256:" + ("0" * 64),
        ),
        node_results=node_results,
        status="success",
        outputs_ref=f"demo.skill/runs/{run_id}/outputs.json",
        trace_refs=[f"demo.skill/runs/{run_id}/trace.jsonl"],
    )
    object_payloads["result.json"] = snapshot.model_dump_json().encode("utf-8")
    store.begin_run(run_id, metadata={"artifact_id": "demo.skill"})
    store.put_batch(run_id, object_payloads)
    store.seal_run(run_id)
    return run_results_ref


def _write_baseline_contract(
    tmp_path: Path,
    *,
    baseline_id: str,
    source_run_id: str,
    source_run_results_ref: str,
    cases: dict[str, object],
) -> str:
    baseline_dir = tmp_path / "golden" / baseline_id
    cases_dir = baseline_dir / "cases"
    cases_dir.mkdir(parents=True)
    case_records = []
    for node_id, expected_output in cases.items():
        case_id = node_id
        case_path = cases_dir / f"{case_id}.json"
        case_path.write_text(
            json.dumps(
                {
                    "case_id": case_id,
                    "node_id": node_id,
                    "phase_id": node_id,
                    "expected_output": expected_output,
                }
            ),
            encoding="utf-8",
        )
        case_records.append(
            {
                "case_id": case_id,
                "node_id": node_id,
                "phase_id": node_id,
                "expected_output_ref": f"cases/{case_id}.json",
            }
        )
    baseline_path = baseline_dir / "baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "baseline_id": baseline_id,
                "source_run_id": source_run_id,
                "source_run_results_ref": source_run_results_ref,
                "cases": case_records,
            }
        ),
        encoding="utf-8",
    )
    (baseline_dir / "report.json").write_text(
        json.dumps({"baseline_id": baseline_id, "case_count": len(case_records)}),
        encoding="utf-8",
    )
    return str(baseline_path)


def _write_sealed_current_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    run_id: str,
    path: str,
    content: bytes,
) -> str:
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore

    skill_dir = _prepare_demo_skill_dir(tmp_path, monkeypatch)
    store = LocalRunArtifactStore(root=skill_dir / ".workspace")
    store.begin_run(run_id, metadata={"artifact_id": "demo.skill"})
    store.put_batch(run_id, {path: content})
    store.seal_run(run_id)
    return f"demo.skill/runs/{run_id}/{path}"


def _prepare_demo_skill_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from app.services import skills as skills_service

    skill_dir = tmp_path / "workspaces" / "default" / "skills" / "demo.skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")
    monkeypatch.setattr(skills_service, "resolve_skill_dir", lambda _skill_id: skill_dir)
    return skill_dir


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
