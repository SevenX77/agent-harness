from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest
from graph_agent.core.result_contracts import GoldenInputRef, NodeRunResult, RunResultSnapshot, RunResultsRef


def test_publish_request_contract_requires_artifact_ref_release_idempotency_and_atomic_stage() -> None:
    PublishArtifactRequest = _load_symbol(
        "app.services.publish_pipeline",
        "PublishArtifactRequest",
    )

    request = PublishArtifactRequest(
        artifact_ref={
            "artifact_id": "artifact-123",
            "content_hash": "sha256:abc123",
            "store": "ephemeral",
            "manifest_ref": "manifests/artifact-123.json",
        },
        release_version="1.2.3",
        idempotency_key="publish-idem-123",
        atomic_stage="stage_invisible",
    )

    assert _field(request, "artifact_ref")["artifact_id"] == "artifact-123"
    assert _field(request, "release_version") == "1.2.3"
    assert _field(request, "idempotency_key") == "publish-idem-123"
    assert _field(request, "atomic_stage") == "stage_invisible"

    required_fields = ("artifact_ref", "release_version", "idempotency_key", "atomic_stage")
    for missing_field in required_fields:
        payload = {
            "artifact_ref": {
                "artifact_id": "artifact-123",
                "content_hash": "sha256:abc123",
                "store": "ephemeral",
                "manifest_ref": "manifests/artifact-123.json",
            },
            "release_version": "1.2.3",
            "idempotency_key": "publish-idem-123",
            "atomic_stage": "stage_invisible",
        }
        payload.pop(missing_field)
        with pytest.raises((TypeError, ValueError)):
            PublishArtifactRequest(**payload)


def test_golden_headless_request_reexports_engine_golden_input_ref_contract() -> None:
    GoldenHeadlessRequest = _load_symbol(
        "app.services.golden_headless",
        "GoldenHeadlessRequest",
    )

    assert GoldenHeadlessRequest is GoldenInputRef

    request = GoldenHeadlessRequest(
        run_results_ref=RunResultsRef(
            run_id="run-123",
            uri="demo.skill/runs/run-123/result.json",
            content_hash="sha256:abc123",
        ),
        baseline_ref="golden/baseline-123/baseline.json",
    )

    assert _field(request, "run_results_ref").uri == "demo.skill/runs/run-123/result.json"
    assert _field(request, "baseline_ref") == "golden/baseline-123/baseline.json"
    assert "final_state" not in _field_names(request)
    assert "skill_id" not in _field_names(request)

    legacy_payload = GoldenHeadlessRequest(
        run_results_ref=RunResultsRef(
            run_id="run-123",
            uri="demo.skill/runs/run-123/result.json",
            content_hash="sha256:abc123",
        ),
        baseline_ref="golden/baseline-123/baseline.json",
        final_state={"legacy": "whole-run-diff"},
    )
    assert "final_state" not in _field_names(legacy_payload)

    with pytest.raises((TypeError, ValueError)):
        GoldenHeadlessRequest(
            final_state={"legacy": "whole-run-diff"},
            baseline_ref="golden/baseline-123/baseline.json",
        )


def test_golden_baseline_contract_exposes_stable_refs_instead_of_metadata_as_core_fact() -> None:
    GoldenBaseline = _load_symbol("app.models.golden", "GoldenBaseline")
    GoldenBaselineFile = _load_symbol("app.models.golden", "GoldenBaselineFile")
    GoldenBaselinePlan = _load_symbol("app.models.golden", "GoldenBaselinePlan")

    baseline = GoldenBaseline(
        id="run-123",
        source_run_id="run-123",
        source_run_results_ref="demo.skill/runs/run-123/result.json",
        baseline_ref=".workspace/golden/run-123/baseline.json",
        linked_input_id="run-123",
        created_at="2026-06-17T00:00:00Z",
        locked=False,
        content_path="/workspace/.workspace/golden/run-123/baseline.json",
    )
    plan = GoldenBaselinePlan(
        baseline=baseline,
        files=[
            GoldenBaselineFile(
                path=".workspace/golden/run-123/baseline.json",
                content='{"baseline_id":"run-123"}',
            ),
            GoldenBaselineFile(
                path=".workspace/golden/run-123/report.json",
                content='{"case_count":1}',
            ),
            GoldenBaselineFile(
                path=".workspace/golden/run-123/cases/draft.json",
                content='{"expected_output":{"ok":true}}',
            ),
        ],
    )

    assert _field(baseline, "source_run_id") == "run-123"
    assert _field(baseline, "source_run_results_ref") == "demo.skill/runs/run-123/result.json"
    assert _field(baseline, "baseline_ref") == ".workspace/golden/run-123/baseline.json"
    assert [item.path for item in plan.files] == [
        ".workspace/golden/run-123/baseline.json",
        ".workspace/golden/run-123/report.json",
        ".workspace/golden/run-123/cases/draft.json",
    ]
    assert "result_path" not in _field_names(plan)
    assert "result_content" not in _field_names(plan)
    assert "metadata_path" not in _field_names(plan)
    assert "metadata_content" not in _field_names(plan)


def test_list_golden_baselines_reads_stable_result_layout_without_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = importlib.import_module("app.services.golden_diff")
    skill_dir = tmp_path / "skill-a"
    golden_dir = skill_dir / ".workspace" / "golden" / "run-123"
    golden_dir.mkdir(parents=True)
    (golden_dir / "baseline.json").write_text(
        json.dumps(
            {
                "baseline_id": "run-123",
                "source_run_id": "source-run",
                "source_run_results_ref": "skill-a/runs/source-run/result.json",
                "locked": True,
                "cases": [],
            }
        ),
        encoding="utf-8",
    )
    (golden_dir / "report.json").write_text(json.dumps({"case_count": 0}), encoding="utf-8")

    monkeypatch.setattr(service, "resolve_skill_dir", lambda _skill_id: skill_dir)

    baselines = service.list_golden_baselines_for_skill("skill-a")

    assert [baseline.id for baseline in baselines] == ["run-123"]
    assert baselines[0].source_run_id == "source-run"
    assert baselines[0].source_run_results_ref == "skill-a/runs/source-run/result.json"
    assert baselines[0].baseline_ref == ".workspace/golden/run-123/baseline.json"
    assert baselines[0].locked is True


def test_plan_golden_baseline_reads_sealed_run_artifact_store_not_legacy_run_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config
    from app.services import golden_diff
    from app.services import skills as skills_service

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    skill_dir = tmp_path / "workspaces" / "default" / "skills" / "demo.skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")
    monkeypatch.setattr(skills_service, "resolve_skill_dir", lambda _skill_id: skill_dir)
    monkeypatch.setattr(golden_diff, "resolve_skill_dir", lambda _skill_id: skill_dir)

    _write_snapshot_store(
        skill_dir,
        skill_id="demo.skill",
        run_id="run-promote-store",
        node_outputs={"draft": {"answer": "sealed store"}},
    )

    plan = golden_diff.plan_golden_baseline_for_run(
        "demo.skill",
        "run-promote-store",
        lock=False,
    )

    files = {item.path: json.loads(item.content) for item in plan.files}
    assert files[".workspace/golden/run-promote-store/baseline.json"] == {
        "baseline_id": "run-promote-store",
        "source_run_id": "run-promote-store",
        "source_run_results_ref": "demo.skill/runs/run-promote-store/result.json",
        "locked": False,
        "cases": [
            {
                "case_id": "draft",
                "node_id": "draft",
                "phase_id": "draft",
                "expected_output_ref": "cases/draft.json",
            }
        ],
    }
    assert files[".workspace/golden/run-promote-store/cases/draft.json"]["expected_output"] == {
        "answer": "sealed store"
    }
    assert files[".workspace/golden/run-promote-store/report.json"]["case_count"] == 1
    assert plan.baseline.source_run_id == "run-promote-store"
    assert plan.baseline.source_run_results_ref == "demo.skill/runs/run-promote-store/result.json"
    assert plan.baseline.baseline_ref == ".workspace/golden/run-promote-store/baseline.json"


def test_plan_golden_baseline_exposes_missing_result_blob_without_candidate_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore
    from app.services import golden_diff
    from app.services import skills as skills_service
    from fastapi import HTTPException

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    skill_dir = tmp_path / "workspaces" / "default" / "skills" / "demo.skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")
    monkeypatch.setattr(skills_service, "resolve_skill_dir", lambda _skill_id: skill_dir)
    monkeypatch.setattr(golden_diff, "resolve_skill_dir", lambda _skill_id: skill_dir)

    store = LocalRunArtifactStore(root=skill_dir / ".workspace")
    store.begin_run("run-missing-result-blob", metadata={"artifact_id": "demo.skill"})
    refs = store.put_batch(
        "run-missing-result-blob",
        {
            "result.json": _snapshot_json(
                skill_id="demo.skill",
                run_id="run-missing-result-blob",
                node_ids=["draft"],
            ).encode("utf-8"),
            "nodes/draft/outputs.json": json.dumps({"answer": "sealed result"}).encode("utf-8"),
        },
    )
    result_ref = refs["result.json"] if isinstance(refs, dict) else refs[0]
    store.seal_run("run-missing-result-blob")
    (skill_dir / ".workspace" / "blobs" / result_ref.content_hash.split(":", 1)[1]).unlink()

    with pytest.raises(HTTPException) as exc_info:
        golden_diff.plan_golden_baseline_for_run(
            "demo.skill",
            "run-missing-result-blob",
            lock=False,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error_code"] == "golden.run_results_not_found"
    assert exc_info.value.detail["details"]["path"] == "result.json"
    assert "hash" in exc_info.value.detail["details"]


def test_compare_run_to_golden_requires_sealed_run_result_snapshot_without_result_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore
    from app.services import golden_diff
    from app.services import skills as skills_service

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    skill_dir = tmp_path / "workspaces" / "default" / "skills" / "demo.skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")
    monkeypatch.setattr(skills_service, "resolve_skill_dir", lambda _skill_id: skill_dir)
    monkeypatch.setattr(golden_diff, "resolve_skill_dir", lambda _skill_id: skill_dir)

    store = LocalRunArtifactStore(root=skill_dir / ".workspace")
    store.begin_run("run-output-only", metadata={"artifact_id": "demo.skill"})
    store.put_batch("run-output-only", {"outputs.json": json.dumps({"draft": {"answer": "sealed"}}).encode("utf-8")})
    store.seal_run("run-output-only")

    golden_dir = skill_dir / ".workspace" / "golden" / "golden-final-state"
    golden_dir.mkdir(parents=True)
    (golden_dir / "baseline.json").write_text(
        json.dumps(
            {
                "baseline_id": "golden-final-state",
                "source_run_id": "source-run",
                "source_run_results_ref": "demo.skill/runs/source-run/result.json",
                "cases": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(Exception) as exc_info:
        golden_diff.compare_run_to_golden(
            "demo.skill",
            "run-output-only",
            against="golden-final-state",
        )

    assert getattr(exc_info.value, "status_code", None) == 404
    assert exc_info.value.detail["error_code"] == "golden.run_results_not_found"


def _write_snapshot_store(
    skill_dir: Path,
    *,
    skill_id: str,
    run_id: str,
    node_outputs: dict[str, object],
) -> str:
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore

    store = LocalRunArtifactStore(root=skill_dir / ".workspace")
    object_payloads = {
        f"nodes/{node_id}/outputs.json": json.dumps(outputs).encode("utf-8")
        for node_id, outputs in node_outputs.items()
    }
    object_payloads["result.json"] = _snapshot_json(
        skill_id=skill_id,
        run_id=run_id,
        node_ids=list(node_outputs),
    ).encode("utf-8")
    store.begin_run(run_id, metadata={"artifact_id": skill_id})
    store.put_batch(run_id, object_payloads)
    store.seal_run(run_id)
    return f"{skill_id}/runs/{run_id}/result.json"


def _snapshot_json(*, skill_id: str, run_id: str, node_ids: list[str]) -> str:
    return RunResultSnapshot(
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
            for node_id in node_ids
        ],
        status="success",
        outputs_ref=f"{skill_id}/runs/{run_id}/outputs.json",
        trace_refs=[f"{skill_id}/runs/{run_id}/trace.jsonl"],
    ).model_dump_json()


def _load_symbol(module_name: str, symbol_name: str) -> Any:
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        pytest.fail(f"{module_name} is missing for the Studio MVP1 publish/golden contract: {exc}")
    try:
        return getattr(module, symbol_name)
    except AttributeError:
        pytest.fail(f"{module_name}.{symbol_name} is missing from the Studio MVP1 publish/golden contract")


def _field(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value[key]
    return getattr(value, key)


def _field_names(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value)
    model_fields = getattr(value, "model_fields", None)
    if isinstance(model_fields, dict):
        return set(model_fields)
    dataclass_fields = getattr(value, "__dataclass_fields__", None)
    if isinstance(dataclass_fields, dict):
        return set(dataclass_fields)
    return set(vars(value))
