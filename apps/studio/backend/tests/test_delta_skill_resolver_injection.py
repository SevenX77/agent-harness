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


def test_delta4_predictor_dispatch_passes_skill_resolver(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_run_skill(skill_dir: Path, **kwargs: Any) -> dict[str, Any]:
        calls.append({"skill_dir": skill_dir, **kwargs})
        return {"context": {"predict_trace": []}, "metrics": {}}

    monkeypatch.setattr(predictor_module, "ensure_workspace_skill_dir", lambda _: tmp_path)
    monkeypatch.setattr(
        predictor_module,
        "build_gateway_model_resolver",
        lambda: object(),
    )
    service = PredictorService(run_skill_fn=fake_run_skill)

    service.dispatch_predict_job("demo.skill")

    assert calls
    assert "skill_resolver" in calls[0]
    assert calls[0]["skill_resolver"] is not None


def test_delta4_predictor_fallback_compile_passes_skill_resolver(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    calls: list[dict[str, Any]] = []

    class FakeLoader:
        def compile_skill(self, skill_dir: Path, **kwargs: Any) -> Any:
            calls.append({"skill_dir": skill_dir, **kwargs})
            return SimpleNamespace(nodes=[], manifest=SimpleNamespace(phases=[]))

    monkeypatch.setattr(predictor_module, "SkillLoader", FakeLoader)

    predictor_module._fallback_trace_from_skill(tmp_path, {})

    assert calls
    assert "skill_resolver" in calls[0]
    assert calls[0]["skill_resolver"] is not None


def test_delta4_run_worker_passes_skill_resolver(tmp_path: Path, monkeypatch: Any) -> None:
    calls: list[dict[str, Any]] = []

    def fake_run_skill(skill_dir: Path, **kwargs: Any) -> dict[str, Any]:
        calls.append({"skill_dir": skill_dir, **kwargs})
        return {"context": {}, "metrics": {}}

    monkeypatch.setattr(run_manager_module, "run_skill", fake_run_skill)
    monkeypatch.setattr(
        run_manager_module,
        "build_gateway_model_resolver",
        lambda: object(),
    )
    queue = _Queue()

    run_manager_module._run_worker_main(
        "demo.skill",
        str(tmp_path / "skill"),
        str(tmp_path / "run"),
        {},
        queue,
    )

    assert calls
    assert "skill_resolver" in calls[0]
    assert calls[0]["skill_resolver"] is not None


def test_delta4_lint_skill_path_passes_skill_resolver(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_compile_skill(skill_path: Path, **kwargs: Any) -> Any:
        calls.append({"skill_path": skill_path, **kwargs})
        return SimpleNamespace(manifest=SimpleNamespace(phases=[]), nodes=[])

    monkeypatch.setattr(skills_module, "compile_skill", fake_compile_skill)

    skills_module.lint_skill_path(tmp_path)

    assert calls
    assert "skill_resolver" in calls[0]
    assert calls[0]["skill_resolver"] is not None
