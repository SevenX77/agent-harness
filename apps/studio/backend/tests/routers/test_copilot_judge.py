from __future__ import annotations

import ast
import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from app.models.copilot import CopilotEventDone
from app.routers import copilot as copilot_router
from app.services import copilot as copilot_service
from fastapi.testclient import TestClient
from graph_agent.core.result_contracts import NodeRunResult, RunResultSnapshot, RunResultsRef


def test_copilot_judge_requires_run_and_baseline_refs_without_streaming(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def stream_query(**kwargs: object) -> AsyncIterator[object]:
        calls.append(kwargs)
        return _events(CopilotEventDone())

    monkeypatch.setattr(copilot_router, "stream_query", stream_query)

    response = client.post(
        "/api/skills/text-segmentation/copilot/judge",
        json={"run_results_ref": "text-segmentation/runs/run-1/result.json"},
    )

    assert response.status_code == 422
    assert response.json()["error_code"] == "copilot.judge_ref_missing"
    assert calls == []


def test_copilot_judge_uses_golden_owned_compare_ref_and_only_writes_judge_context(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    skills_dir, _workspaces_dir = studio_roots
    monkeypatch.chdir(tmp_path)
    skill_id = "text-segmentation"
    run_id = "current-run"
    golden_id = "golden-run"
    skill_dir = skills_dir / skill_id
    run_results_ref = _write_run_snapshot(
        skill_dir,
        skill_id,
        run_id,
        {"draft": {"answer": "hello studio"}},
    )
    baseline_ref = _write_golden_baseline(
        skill_dir,
        skill_id,
        golden_id,
        {"draft": {"answer": "hello world"}},
    )

    response = client.post(
        "/api/skills/text-segmentation/copilot/judge",
        json={
            "run_results_ref": run_results_ref,
            "baseline_ref": baseline_ref,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["compare_result_ref"] == f"{skill_id}/golden/{golden_id}/compare/{run_id}/compare_result.json"
    assert body["judge_context_ref"] == f"{skill_id}/runs/{run_id}/copilot_judge/{golden_id}/judge_context.json"
    golden_compare_dir = skill_dir / ".workspace" / "golden" / golden_id / "compare" / run_id
    judge_dir = skill_dir / ".workspace" / "runs" / run_id / "copilot_judge" / golden_id
    cwd_dir = tmp_path / skill_id / "runs" / run_id / "copilot_judge" / golden_id
    assert (golden_compare_dir / "compare_result.json").is_file()
    assert not (judge_dir / "compare_result.json").exists()
    assert (judge_dir / "judge_context.json").is_file()
    assert not (cwd_dir / "compare_result.json").exists()


def test_copilot_judge_returns_golden_owned_refs_baseline_and_diff_summary(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _workspaces_dir = studio_roots
    skill_id = "text-segmentation"
    run_id = "judge-run"
    golden_id = "judge-golden"
    skill_dir = skills_dir / skill_id
    run_results_ref = _write_run_snapshot(
        skill_dir,
        skill_id,
        run_id,
        {"draft": {"answer": "hello studio"}},
    )
    baseline_ref = _write_golden_baseline(
        skill_dir,
        skill_id,
        golden_id,
        {"draft": {"answer": "hello world"}},
    )

    response = client.post(
        f"/api/skills/{skill_id}/copilot/judge",
        json={
            "run_results_ref": run_results_ref,
            "baseline_ref": baseline_ref,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["baseline_ref"] == baseline_ref
    assert body["diff_summary"] == {
        "baseline_id": golden_id,
        "run_results_ref": run_results_ref,
        "total_score": body["diff_summary"]["total_score"],
        "node_group_count": 1,
        "failed_node_count": 1,
    }
    assert body["compare_result_ref"] == f"{skill_id}/golden/{golden_id}/compare/{run_id}/compare_result.json"
    assert body["judge_context_ref"] == f"{skill_id}/runs/{run_id}/copilot_judge/{golden_id}/judge_context.json"


def test_copilot_router_does_not_own_judge_fact_file_writes() -> None:
    router_path = Path(copilot_router.__file__)
    tree = ast.parse(router_path.read_text(encoding="utf-8"))

    forbidden_names = {"resolve_skill_dir"}
    forbidden_attributes = {"write_text", "mkdir"}
    forbidden_imports = {"json"}
    findings: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            findings.extend(alias.name for alias in node.names if alias.name in forbidden_imports)
        elif isinstance(node, ast.ImportFrom) and node.module in forbidden_imports:
            findings.append(node.module)
        elif isinstance(node, ast.Name) and node.id in forbidden_names:
            findings.append(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in forbidden_attributes:
            findings.append(node.attr)

    assert findings == []


def test_copilot_chat_service_does_not_read_run_or_golden_fact_files() -> None:
    service_source = Path(copilot_service.__file__).read_text(encoding="utf-8")

    forbidden_patterns = (
        "run_dir_for",
        "golden_dir_for",
        "json.load(",
        "open(",
    )

    assert [pattern for pattern in forbidden_patterns if pattern in service_source] == []


def test_copilot_router_and_service_do_not_directly_read_run_or_golden_facts() -> None:
    forbidden_function_names = {"open", "run_dir_for", "golden_dir_for"}
    findings: list[str] = []

    for module in (copilot_router, copilot_service):
        module_path = Path(module.__file__)
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "app.services.skills":
                findings.extend(
                    f"{module_path.name}:{alias.name}"
                    for alias in node.names
                    if alias.name in {"run_dir_for", "golden_dir_for"}
                )
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in forbidden_function_names:
                    findings.append(f"{module_path.name}:{node.func.id}")
                elif (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "load"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "json"
                ):
                    findings.append(f"{module_path.name}:json.load")

    assert findings == []


def test_copilot_judge_rejects_cross_skill_run_results_ref(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _workspaces_dir = studio_roots
    run_results_ref = _write_run_snapshot(
        skills_dir / "event-extraction",
        "event-extraction",
        "foreign-run",
        {"setup": {"answer": "foreign run"}},
    )
    baseline_ref = _write_golden_baseline(
        skills_dir / "text-segmentation",
        "text-segmentation",
        "golden-run",
        {"setup": {"answer": "route baseline"}},
    )

    response = client.post(
        "/api/skills/text-segmentation/copilot/judge",
        json={
            "run_results_ref": run_results_ref,
            "baseline_ref": baseline_ref,
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "copilot.judge_ref_invalid"
    assert body["details"] == {
        "ref_kind": "run_results_ref",
        "ref": "event-extraction/runs/foreign-run/result.json",
        "expected_skill_id": "text-segmentation",
    }


def test_copilot_judge_rejects_cross_skill_baseline_ref(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _workspaces_dir = studio_roots
    run_results_ref = _write_run_snapshot(
        skills_dir / "text-segmentation",
        "text-segmentation",
        "current-run",
        {"setup": {"answer": "route run"}},
    )
    baseline_ref = _write_golden_baseline(
        skills_dir / "event-extraction",
        "event-extraction",
        "foreign-golden",
        {"setup": {"answer": "foreign baseline"}},
    )

    response = client.post(
        "/api/skills/text-segmentation/copilot/judge",
        json={
            "run_results_ref": run_results_ref,
            "baseline_ref": baseline_ref,
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "copilot.judge_ref_invalid"
    assert body["details"] == {
        "ref_kind": "baseline_ref",
        "ref": "event-extraction/golden/foreign-golden/baseline.json",
        "expected_skill_id": "text-segmentation",
    }


@pytest.mark.parametrize(
    ("payload", "ref_kind", "ref"),
    [
        (
            {
                "run_results_ref": "text-segmentation/runs/current-run/result.json/extra",
                "baseline_ref": "text-segmentation/golden/golden-run/baseline.json",
            },
            "run_results_ref",
            "text-segmentation/runs/current-run/result.json/extra",
        ),
        (
            {
                "run_results_ref": "text-segmentation/runs/current-run/result.json",
                "baseline_ref": "text-segmentation/golden/golden-run/report.json",
            },
            "baseline_ref",
            "text-segmentation/golden/golden-run/report.json",
        ),
    ],
)
def test_copilot_judge_rejects_refs_that_do_not_match_exact_shapes(
    client: TestClient,
    payload: dict[str, str],
    ref_kind: str,
    ref: str,
) -> None:
    response = client.post(
        "/api/skills/text-segmentation/copilot/judge",
        json=payload,
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "copilot.judge_ref_invalid"
    assert body["details"] == {
        "ref_kind": ref_kind,
        "ref": ref,
        "expected_skill_id": "text-segmentation",
    }


def test_copilot_judge_accepts_workspace_golden_baseline_ref(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    skills_dir, _workspaces_dir = studio_roots
    monkeypatch.chdir(tmp_path)
    skill_id = "text-segmentation"
    run_id = "current-run"
    golden_id = "workspace-golden"
    skill_dir = skills_dir / skill_id
    run_results_ref = _write_run_snapshot(
        skill_dir,
        skill_id,
        run_id,
        {"setup": {"answer": "hello studio"}},
    )
    _write_golden_baseline(
        skill_dir,
        skill_id,
        golden_id,
        {"setup": {"answer": "hello world"}},
    )

    response = client.post(
        "/api/skills/text-segmentation/copilot/judge",
        json={
            "run_results_ref": run_results_ref,
            "baseline_ref": f".workspace/golden/{golden_id}/baseline.json",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["compare_result_ref"] == f"{skill_id}/golden/{golden_id}/compare/{run_id}/compare_result.json"
    assert body["judge_context_ref"] == f"{skill_id}/runs/{run_id}/copilot_judge/{golden_id}/judge_context.json"


def test_copilot_judge_accepts_against_baseline_id_as_golden_owned_fact_ref(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _workspaces_dir = studio_roots
    skill_id = "text-segmentation"
    run_id = "against-run"
    golden_id = "against-golden"
    skill_dir = skills_dir / skill_id
    run_results_ref = _write_run_snapshot(
        skill_dir,
        skill_id,
        run_id,
        {"setup": {"answer": "hello studio"}},
    )
    _write_golden_baseline(
        skill_dir,
        skill_id,
        golden_id,
        {"setup": {"answer": "hello world"}},
    )

    response = client.post(
        "/api/skills/text-segmentation/copilot/judge",
        json={
            "run_results_ref": run_results_ref,
            "against": golden_id,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["baseline_ref"] == f"{skill_id}/golden/{golden_id}/baseline.json"
    assert body["compare_result_ref"] == f"{skill_id}/golden/{golden_id}/compare/{run_id}/compare_result.json"
    assert body["judge_context_ref"] == f"{skill_id}/runs/{run_id}/copilot_judge/{golden_id}/judge_context.json"


async def _events(*events: object) -> AsyncIterator[object]:
    for event in events:
        yield event


def _write_run_snapshot(
    skill_dir: Path,
    skill_id: str,
    run_id: str,
    node_outputs: dict[str, dict[str, object]],
) -> str:
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore

    store = LocalRunArtifactStore(root=skill_dir / ".workspace")
    objects = {
        f"nodes/{node_id}/outputs.json": json.dumps(output).encode("utf-8")
        for node_id, output in node_outputs.items()
    }
    objects["result.json"] = RunResultSnapshot(
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
                trace_refs=[f"{skill_id}/runs/{run_id}/trace.jsonl"],
            )
            for node_id in node_outputs
        ],
        status="success",
        outputs_ref=f"{skill_id}/runs/{run_id}/final_state.json",
        trace_refs=[f"{skill_id}/runs/{run_id}/trace.jsonl"],
    ).model_dump_json().encode("utf-8")
    store.begin_run(run_id, metadata={"artifact_id": skill_id})
    store.put_batch(run_id, objects)
    store.seal_run(run_id)
    return f"{skill_id}/runs/{run_id}/result.json"


def _write_golden_baseline(
    skill_dir: Path,
    skill_id: str,
    golden_id: str,
    node_outputs: dict[str, dict[str, object]],
) -> str:
    golden_dir = skill_dir / ".workspace" / "golden" / golden_id
    cases_dir = golden_dir / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)
    cases: list[dict[str, str]] = []
    for node_id, output in node_outputs.items():
        case_ref = f"cases/{node_id}.json"
        cases.append(
            {
                "case_id": node_id,
                "node_id": node_id,
                "phase_id": node_id,
                "expected_output_ref": case_ref,
            }
        )
        (cases_dir / f"{node_id}.json").write_text(
            json.dumps(
                {
                    "case_id": node_id,
                    "node_id": node_id,
                    "phase_id": node_id,
                    "expected_output": output,
                }
            ),
            encoding="utf-8",
        )
    (golden_dir / "baseline.json").write_text(
        json.dumps(
            {
                "baseline_id": golden_id,
                "source_run_id": "source-run",
                "source_run_results_ref": f"{skill_id}/runs/source-run/result.json",
                "cases": cases,
            }
        ),
        encoding="utf-8",
    )
    return f"{skill_id}/golden/{golden_id}/baseline.json"
