from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from graph_agent.core import runner as runner_module
from graph_agent.io.run_layout import runs_root


class RecordingGraph:
    def invoke(self, state: dict[str, object], *args: Any, **kwargs: Any) -> dict[str, object]:
        del state
        class MockData:
            def model_dump(self) -> dict[str, object]:
                return {"ok": True}
        return {"data": MockData()}


class RecordingAssembler:
    def __init__(self) -> None:
        self.graph = RecordingGraph()


def _write_v030_root(root: Path) -> Path:
    (root / "GRAPH.md").write_text(
        """---
schema_version: "v0.3.0"
name: test
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
phases: []
---
""",
        encoding="utf-8",
    )
    return root


def test_run_skill_dict_omitted_mock_llm_passes_no_chat_model(
    monkeypatch,
    tmp_path,
    mock_skill_resolver,
) -> None:
    skill_root = _write_v030_root(tmp_path)
    chat_models: list[object] = []
    model_resolvers: list[object] = []

    monkeypatch.setattr(
        "graph_agent.core.compiler.compile_skill",
        lambda *_args, **_kwargs: object(),
    )

    def fake_assemble_graph(*_args, chat_model=None, model_resolver=None, **_kwargs):
        chat_models.append(chat_model)
        model_resolvers.append(model_resolver)
        return RecordingAssembler()

    monkeypatch.setattr("graph_agent.core.graph_assembler.assemble_graph", fake_assemble_graph)

    runner_module._run_skill_dict(
        skill_root,
        workspace_dir=tmp_path / "workspace",
        run_root=runs_root(tmp_path / "workspace"),
        callbacks=[],
        cleanup_checkpoints_on_finish=False,
        skill_resolver=mock_skill_resolver,
    )

    assert chat_models == [None]
    assert model_resolvers == [None]


def test_run_skill_dict_explicit_mock_none_is_passed_as_chat_model(
    monkeypatch,
    tmp_path,
    mock_skill_resolver,
) -> None:
    skill_root = _write_v030_root(tmp_path)
    resolved_model = object()
    model_resolver = SimpleNamespace(resolve=lambda **_kwargs: resolved_model)
    chat_models: list[object] = []
    model_resolvers: list[object] = []

    monkeypatch.setattr(
        "graph_agent.core.compiler.compile_skill",
        lambda *_args, **_kwargs: object(),
    )

    def fake_assemble_graph(*_args, chat_model=None, model_resolver=None, **_kwargs):
        chat_models.append(chat_model)
        model_resolvers.append(model_resolver)
        return RecordingAssembler()

    monkeypatch.setattr("graph_agent.core.graph_assembler.assemble_graph", fake_assemble_graph)

    runner_module._run_skill_dict(
        skill_root,
        workspace_dir=tmp_path / "workspace",
        run_root=runs_root(tmp_path / "workspace"),
        callbacks=[],
        cleanup_checkpoints_on_finish=False,
        skill_resolver=mock_skill_resolver,
        model_resolver=model_resolver,
        mock_llm=None,
    )

    assert chat_models == [None]
    assert model_resolvers == [None]


def test_run_skill_dict_uses_model_resolver_when_mock_llm_omitted(
    monkeypatch, tmp_path, mock_skill_resolver
) -> None:
    skill_root = _write_v030_root(tmp_path)
    model_resolver = SimpleNamespace(resolve=lambda **_kwargs: object())
    chat_models: list[object] = []
    model_resolvers: list[object] = []

    monkeypatch.setattr(
        "graph_agent.core.compiler.compile_skill",
        lambda *_args, **_kwargs: object(),
    )

    def fake_assemble_graph(*_args, chat_model=None, model_resolver=None, **_kwargs):
        chat_models.append(chat_model)
        model_resolvers.append(model_resolver)
        return RecordingAssembler()

    monkeypatch.setattr("graph_agent.core.graph_assembler.assemble_graph", fake_assemble_graph)

    runner_module._run_skill_dict(
        skill_root,
        workspace_dir=tmp_path / "workspace",
        run_root=runs_root(tmp_path / "workspace"),
        callbacks=[],
        cleanup_checkpoints_on_finish=False,
        skill_resolver=mock_skill_resolver,
        model_resolver=model_resolver,
    )

    assert chat_models == [None]
    assert model_resolvers == [model_resolver]
