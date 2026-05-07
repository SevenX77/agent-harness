from __future__ import annotations

from types import SimpleNamespace

from graph_agent.core import runner as runner_module
from graph_agent.core._predict_internal.strategy import HeuristicStubStrategy


class RecordingHarness:
    def __init__(self) -> None:
        self._resolver = SimpleNamespace()
        self.bindings_seen: list[bool] = []
        self.callbacks = []
        self.phases = [object()]

    def run(self, **kwargs: object) -> dict[str, object]:
        del kwargs
        self.bindings_seen.append(hasattr(self._resolver, "_graph_agent_predict_mock_strategy"))
        return {
            "data": _Data(),
            "flow": _Flow(),
        }


class _Data:
    def model_dump(self) -> dict[str, object]:
        return {"ok": True}


class _Flow:
    metrics: dict[str, object] = {}
    trace_path = None


def test_run_skill_dict_omitted_mock_llm_does_not_bind_predictor(
    monkeypatch,
    tmp_path,
) -> None:
    skill = tmp_path / "SKILL.md"
    skill.write_text("---\nname: test\n---\n", encoding="utf-8")
    harness = RecordingHarness()
    monkeypatch.setattr(runner_module, "load_workflow_from_md", lambda *_args, **_kwargs: harness)
    runner_module.clear_cache()

    runner_module._run_skill_dict(skill, callbacks=[], cleanup_checkpoints_on_finish=False)

    assert harness.bindings_seen == [False]
    assert not hasattr(harness._resolver, "_graph_agent_predict_mock_strategy")


def test_run_skill_dict_explicit_mock_none_binds_only_during_current_run(
    monkeypatch,
    tmp_path,
) -> None:
    skill = tmp_path / "SKILL.md"
    skill.write_text("---\nname: test\n---\n", encoding="utf-8")
    harness = RecordingHarness()
    monkeypatch.setattr(runner_module, "load_workflow_from_md", lambda *_args, **_kwargs: harness)
    runner_module.clear_cache()

    runner_module._run_skill_dict(
        skill,
        callbacks=[],
        cleanup_checkpoints_on_finish=False,
        mock_llm=None,
    )

    assert harness.bindings_seen == [True]
    assert not hasattr(harness._resolver, "_graph_agent_predict_mock_strategy")


def test_run_skill_dict_restores_existing_predict_binding(monkeypatch, tmp_path) -> None:
    skill = tmp_path / "SKILL.md"
    skill.write_text("---\nname: test\n---\n", encoding="utf-8")
    harness = RecordingHarness()
    existing = HeuristicStubStrategy()
    harness._resolver._graph_agent_predict_mock_strategy = existing
    monkeypatch.setattr(runner_module, "load_workflow_from_md", lambda *_args, **_kwargs: harness)
    runner_module.clear_cache()

    runner_module._run_skill_dict(
        skill,
        callbacks=[],
        cleanup_checkpoints_on_finish=False,
        mock_llm={"draft": {"text": "manual"}},
    )

    assert harness.bindings_seen == [True]
    assert harness._resolver._graph_agent_predict_mock_strategy is existing
