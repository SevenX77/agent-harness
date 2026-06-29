from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from app.services import predictor as predictor_module
from app.services import run_manager as run_manager_module
from app.services import skills as skills_module
from app.services.predictor import PredictorService


class _Queue:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def put(self, item: dict[str, Any]) -> None:
        self.items.append(item)


def test_delta4_predictor_dispatch_uses_engine_artifact_adapter(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    from app.core import config

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")

    sha_val = "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "GRAPH.md").write_text("# Skill\n", encoding="utf-8")

    import app.core.adapters.engine as engine_adapter_module

    mock_art_ref = {
        "artifact_id": "demo.skill",
        "content_hash": f"sha256:{sha_val}",
        "store": "ephemeral",
        "manifest_ref": "some_manifest_ref",
    }
    monkeypatch.setattr(
        engine_adapter_module.EngineAdapter,
        "compile",
        lambda *a, **k: mock_art_ref,
    )

    calls: list[dict[str, Any]] = []

    def fake_predict_artifact(_adapter: object, payload: dict[str, Any]) -> dict[str, Any]:
        calls.append(payload)
        from app.core.adapters.engine import RunResult

        result = RunResult(
            run_id="run-123", success=True, skill_id="demo.skill", context={"predict_trace": []}, metrics={}
        )
        return result.model_dump(mode="json")

    monkeypatch.setattr(engine_adapter_module.EngineAdapter, "predict_artifact", fake_predict_artifact)
    monkeypatch.setattr(predictor_module, "ensure_workspace_skill_dir", lambda _: skill_dir)

    service = PredictorService()
    service.dispatch_predict_job("demo.skill")

    assert calls
    assert calls[0]["artifact_ref"] == mock_art_ref


def test_delta4_predictor_fallback_compile_passes_skill_resolver(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    calls: list[dict[str, Any]] = []

    class FakeLoader:
        def compile_skill(self, skill_dir: Path, **kwargs: Any) -> Any:
            calls.append({"skill_dir": skill_dir, **kwargs})
            return SimpleNamespace(nodes=[], manifest=SimpleNamespace(phases=[]))

    import app.core.adapters.engine as engine_adapter_module

    monkeypatch.setattr(engine_adapter_module, "SkillLoader", FakeLoader)

    predictor_module._fallback_trace_from_skill(tmp_path, {})

    assert calls
    assert "skill_resolver" in calls[0]
    assert calls[0]["skill_resolver"] is not None


def test_delta4_run_worker_passes_skill_resolver(tmp_path: Path, monkeypatch: Any) -> None:
    from app.core import config

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")

    storage_root = tmp_path / "workspaces" / "default"
    sha_val = "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
    ephemeral_dir = storage_root / "ephemeral_run_skills" / sha_val
    ephemeral_dir.mkdir(parents=True, exist_ok=True)
    (ephemeral_dir / "GRAPH.md").write_text("# Skill\n", encoding="utf-8")

    import app.core.adapters.engine as engine_adapter_module

    calls: list[dict[str, Any]] = []

    def fake_run_artifact(_adapter: object, payload: dict[str, Any]) -> dict[str, Any]:
        calls.append(payload)
        return {"context": {}, "metrics": {}}

    monkeypatch.setattr(engine_adapter_module.EngineAdapter, "run_artifact", fake_run_artifact)

    art_ref = {
        "artifact_id": "demo.skill",
        "content_hash": f"sha256:{sha_val}",
        "store": "ephemeral",
        "manifest_ref": "some_manifest_ref",
    }
    queue = _Queue()

    run_manager_module._run_worker_main(
        "demo.skill",
        str(tmp_path / "run"),
        {},
        queue,
        art_ref,
    )

    assert calls
    assert calls[0]["artifact_ref"] == art_ref
    assert calls[0]["inputs"] == {}


def test_run_worker_reports_failed_when_result_unsuccessful(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """P0#3 (handshake audit §5.3): the run worker must NOT report fake success.

    When EngineAdapter.run_artifact returns a RunResult with success=False
    (engine-level failure that does not raise, e.g. [F-v3-graph-root-missing]),
    the worker must surface status=failed, not the hardcoded 'success'.
    """
    import json

    from app.core import config

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")

    sha_val = "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
    storage_root = tmp_path / "workspaces" / "default"
    ephemeral_dir = storage_root / "ephemeral_run_skills" / sha_val
    ephemeral_dir.mkdir(parents=True, exist_ok=True)
    (ephemeral_dir / "GRAPH.md").write_text("# Skill\n", encoding="utf-8")

    import app.core.adapters.engine as engine_adapter_module

    def fake_run_artifact(_adapter: object, _payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "context": {},
            "metrics": {},
            "success": False,
            "error": "[F-v3-graph-root-missing] boom",
        }

    monkeypatch.setattr(engine_adapter_module.EngineAdapter, "run_artifact", fake_run_artifact)

    art_ref = {
        "artifact_id": "demo.skill",
        "content_hash": f"sha256:{sha_val}",
        "store": "ephemeral",
        "manifest_ref": "some_manifest_ref",
    }
    run_dir = storage_root / "runs" / "run"
    queue = _Queue()

    run_manager_module._run_worker_main(
        "demo.skill",
        str(run_dir),
        {},
        queue,
        art_ref,
    )

    status_events = [e for e in queue.items if e.get("type") == "status"]
    assert status_events, "worker should emit a status event"
    assert status_events[-1]["status"] == "failed"
    assert "graph-root-missing" in str(status_events[-1].get("error"))

    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore

    metrics = json.loads(
        LocalRunArtifactStore(root=storage_root)
        .get_run_object("run", "metrics.json")
        .decode("utf-8")
    )
    assert metrics["status"] == "failed"


def test_run_worker_passes_workspace_root_not_runs_dir(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """P0#2 (handshake audit §5.2): worker passes workspace_dir = the .workspace ROOT.

    Engine writes <workspace_dir>/runs/<thread_id>. Passing run_dir.parent (=.workspace/runs)
    made it land in .workspace/runs/runs/<id> while Studio reads .workspace/runs/<id> (empty).
    Mirrors the predict-path contract (test_workspace_dir_contract_red §predict).
    """
    from app.core import config

    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")

    sha_val = "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
    storage_root = tmp_path / "workspaces" / "default"
    ephemeral_dir = storage_root / "ephemeral_run_skills" / sha_val
    ephemeral_dir.mkdir(parents=True, exist_ok=True)
    (ephemeral_dir / "GRAPH.md").write_text("# Skill\n", encoding="utf-8")

    import app.core.adapters.engine as engine_adapter_module

    calls: list[dict[str, Any]] = []

    def fake_run_artifact(_adapter: object, payload: dict[str, Any]) -> dict[str, Any]:
        calls.append(payload)
        return {"context": {}, "metrics": {}, "success": True}

    monkeypatch.setattr(engine_adapter_module.EngineAdapter, "run_artifact", fake_run_artifact)

    art_ref = {
        "artifact_id": "demo.skill",
        "content_hash": f"sha256:{sha_val}",
        "store": "ephemeral",
        "manifest_ref": "some_manifest_ref",
    }
    workspace_root = tmp_path / "skill" / ".workspace"
    run_dir = workspace_root / "runs" / "run-123"
    queue = _Queue()

    run_manager_module._run_worker_main(
        "demo.skill",
        str(run_dir),
        {},
        queue,
        art_ref,
    )

    assert calls
    assert calls[0]["workspace_dir"] == str(workspace_root)
    assert calls[0]["thread_id"] == "run-123"


def test_delta4_lint_skill_path_passes_skill_resolver(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_compile_skill(skill_path: Path, **kwargs: Any) -> Any:
        calls.append({"skill_path": skill_path, **kwargs})
        return SimpleNamespace(manifest=SimpleNamespace(phases=[]), nodes=[], raw={"graph": {"frontmatter": {}}})

    monkeypatch.setattr(skills_module, "compile_skill", fake_compile_skill)

    skills_module.lint_skill_path(tmp_path)

    assert calls
    assert "skill_resolver" in calls[0]
    assert calls[0]["skill_resolver"] is not None
