from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from graph_agent.core.adapter_contracts import (
    PredictArtifactRequest,
    RunArtifactRequest,
    RunSession,
)
from graph_agent.core.artifacts import ArtifactRef, compile_artifact


class HashingFakeRunArtifactStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.put_calls = 0
        self.sealed: list[str] = []

    def begin_run(self, run_id: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"run_id": run_id, "metadata": metadata or {}}

    def put_batch(self, run_id: str, objects: dict[str, bytes]) -> dict[str, Any]:
        from graph_agent.core.storage_contracts import ObjectRef

        self.put_calls += 1
        refs: dict[str, ObjectRef] = {}
        for path, content in objects.items():
            sha_val = hashlib.sha256(content).hexdigest()
            content_hash = f"sha256:{sha_val}"
            self.objects[content_hash] = content
            refs[path] = ObjectRef(
                bytes_ref=f"bytes://{content_hash}",
                content_hash=content_hash,
                size_bytes=len(content),
                path=path,
            )
        return refs

    def seal_run(self, run_id: str) -> object:
        self.sealed.append(run_id)
        return {"run_id": run_id, "sealed": True}

    def get_object(self, *, hash: str) -> bytes:
        return self.objects[hash]


class EmptyRefsRunArtifactStore(HashingFakeRunArtifactStore):
    def put_batch(self, run_id: str, objects: dict[str, bytes]) -> dict[str, Any]:
        self.put_calls += 1
        return {}


class WrongPathRefsRunArtifactStore(HashingFakeRunArtifactStore):
    def put_batch(self, run_id: str, objects: dict[str, bytes]) -> dict[str, Any]:
        from graph_agent.core.storage_contracts import ObjectRef

        self.put_calls += 1
        return {
            "other.json": ObjectRef(
                bytes_ref="bytes://sha256:other",
                content_hash="sha256:other",
                size_bytes=5,
                path="other.json",
            )
        }


class CountingArtifactExecutor:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, request: RunArtifactRequest) -> dict[str, Any]:
        self.calls += 1
        return {"artifact_id": request.artifact_ref.artifact_id, "calls": self.calls}


def _artifact_ref() -> ArtifactRef:
    return ArtifactRef(
        artifact_id="artifact-runtime-demo",
        content_hash="sha256:runtime-demo",
        store="ephemeral",
        manifest_ref="object://manifest.json",
        source_map_ref="object://source-map.json",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_two_phase_logic_skill(root: Path) -> None:
    _write_text(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: artifact-runtime-real-graph
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
  outputs:
    type: object
    properties:
      prepared:
        type: string
      answer:
        type: string
phases:
  - prepare
  - draft
---
<phase depends_on="input">prepare</phase>
<phase depends_on="prepare" output>draft</phase>
""",
    )
    _write_text(
        root / "phases" / "prepare" / "LOGIC.md",
        """---
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
  outputs:
    type: object
    properties:
      prepared:
        type: string
---
<action>prepare</action>
""",
    )
    _write_text(
        root / "phases" / "prepare" / "actions" / "prepare.py",
        "def prepare(context):\n"
        "    return {'prepared': 'prepared:' + str(context.get('topic', 'missing'))}\n",
    )
    _write_text(
        root / "phases" / "draft" / "LOGIC.md",
        """---
io:
  inputs:
    type: object
    properties:
      prepared:
        type: string
  outputs:
    type: object
    properties:
      answer:
        type: string
---
<action>draft</action>
""",
    )
    _write_text(
        root / "phases" / "draft" / "actions" / "draft.py",
        "def draft(context):\n"
        "    return {'answer': 'answer:' + str(context.get('prepared', 'missing'))}\n",
    )


def _write_single_agent_skill(root: Path) -> None:
    _write_text(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: artifact-runtime-predict-agent
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
  outputs:
    type: object
    properties:
      answer:
        type: string
phases:
  - draft
---
<phase depends_on="input" output>draft</phase>
""",
    )
    _write_text(
        root / "phases" / "draft" / "SKILL.md",
        """---
llm_role: analyst
phase_config:
  io:
    inputs:
      type: object
      properties:
        topic:
          type: string
    outputs:
      type: object
      required: [answer]
      properties:
        answer:
          type: string
  tools:
    - finish_task
  max_iterations: 2
---
<role>
You draft a short answer.
</role>

<goal>
Call @tool:finish_task with the answer.
</goal>
""",
    )


class FailIfInvokedProvider:
    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, request: Any) -> Any:
        del request
        self.calls += 1
        raise AssertionError("Predict must not invoke a live LLM provider")


def test_run_artifact_accepts_artifact_ref_and_returns_run_session() -> None:
    runner = importlib.import_module("graph_agent.core.runner")
    request = RunArtifactRequest(
        artifact_ref=_artifact_ref(),
        inputs={"topic": "red"},
        execution_context={"workspace_id": "local"},
        idempotency_key="idem-run-artifact-1",
    )

    session = runner.run_artifact(request, artifact_executor=CountingArtifactExecutor())

    assert session.run_id
    assert session.event_stream_ref


def test_core_run_artifact_rejects_raw_skill_path() -> None:
    runner = importlib.import_module("graph_agent.core.runner")

    assert hasattr(runner, "run_artifact"), "Engine must expose run_artifact before it can reject raw skill_path"

    with pytest.raises(Exception) as exc_info:
        runner.run_artifact(
            skill_path="/tmp/legacy/SKILL.md",
            inputs={"topic": "red"},
            idempotency_key="idem-raw-path",
        )

    assert getattr(exc_info.value, "error_code", None) == "runtime.raw_skill_path"


def test_run_artifact_idempotency_key_executes_once() -> None:
    runner = importlib.import_module("graph_agent.core.runner")
    executor = CountingArtifactExecutor()
    request = RunArtifactRequest(
        artifact_ref=_artifact_ref(),
        inputs={"topic": "red"},
        execution_context={"workspace_id": "local"},
        idempotency_key="idem-repeat",
    )

    first = runner.run_artifact(request, artifact_executor=executor)
    second = runner.run_artifact(request, artifact_executor=executor)

    assert first.run_id == second.run_id
    assert executor.calls == 1


def test_run_artifact_without_executor_executes_compiled_graph(
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    runner = importlib.import_module("graph_agent.core.runner")
    skill_root = tmp_path / "artifact-runtime-real-graph"
    _write_two_phase_logic_skill(skill_root)
    manifest = compile_artifact(source_root=skill_root, skill_resolver=mock_skill_resolver)
    workspace_dir = tmp_path / "workspace"

    request = RunArtifactRequest(
        artifact_ref=manifest.artifact_ref,
        inputs={"topic": "mars"},
        execution_context={
            "artifact_root": str(skill_root),
            "workspace_dir": str(workspace_dir),
            "thread_id": "artifact-real-run",
        },
        idempotency_key="idem-real-graph-run",
    )

    session = runner.run_artifact(request, skill_resolver=mock_skill_resolver)

    assert isinstance(session, RunSession)
    result_path = workspace_dir / "runs" / session.run_id / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["success"] is True
    assert result["context"]["prepared"] == "prepared:mars"
    assert result["context"]["answer"] == "answer:prepared:mars"


def test_run_artifact_replays_cached_file_result_through_run_artifact_store(
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    runner = importlib.import_module("graph_agent.core.runner")
    idempotency_key = "idem-real-graph-run-store-after-file-cache"
    getattr(runner, "_RUN_CACHE", {}).pop(idempotency_key, None)
    skill_root = tmp_path / "artifact-runtime-real-graph"
    _write_two_phase_logic_skill(skill_root)
    manifest = compile_artifact(source_root=skill_root, skill_resolver=mock_skill_resolver)
    workspace_dir = tmp_path / "workspace"
    request = RunArtifactRequest(
        artifact_ref=manifest.artifact_ref,
        inputs={"topic": "saturn"},
        execution_context={
            "artifact_root": str(skill_root),
            "workspace_dir": str(workspace_dir),
            "thread_id": "artifact-real-run-cache-store",
        },
        idempotency_key=idempotency_key,
    )

    first = runner.run_artifact(request, skill_resolver=mock_skill_resolver)
    assert isinstance(first, RunSession)
    assert first.result_ref is not None
    assert first.result_ref.startswith("file://")

    store = HashingFakeRunArtifactStore()
    second = runner.run_artifact(
        request,
        run_artifact_store=store,
        skill_resolver=mock_skill_resolver,
    )

    assert isinstance(second, RunSession)
    assert second.result_ref is not None
    assert second.result_ref.startswith("bytes://")
    assert store.put_calls == 1
    stored = store.get_object(hash=second.result_ref.removeprefix("bytes://"))
    result = json.loads(stored.decode("utf-8"))
    assert result["success"] is True
    assert result["context"]["prepared"] == "prepared:saturn"


def test_predict_artifact_without_executor_executes_predict_graph_with_mock(
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    runner = importlib.import_module("graph_agent.core.runner")
    skill_root = tmp_path / "artifact-runtime-real-graph"
    _write_two_phase_logic_skill(skill_root)
    manifest = compile_artifact(source_root=skill_root, skill_resolver=mock_skill_resolver)
    workspace_dir = tmp_path / "workspace"

    request = PredictArtifactRequest(
        artifact_ref=manifest.artifact_ref,
        inputs={"topic": "venus"},
        execution_context={
            "artifact_root": str(skill_root),
            "workspace_dir": str(workspace_dir),
            "thread_id": "artifact-real-predict",
            "mock_llm": {"draft": {"answer": "mocked-answer"}},
        },
        idempotency_key="idem-real-graph-predict",
    )

    session = runner.predict_artifact(request, skill_resolver=mock_skill_resolver)

    assert isinstance(session, RunSession)
    result_path = workspace_dir / "runs" / session.run_id / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["source"] == "predict"
    assert result["context"]["prepared"] == "prepared:venus"
    assert result["context"]["answer"] == "answer:prepared:venus"
    assert [phase["phase_name"] for phase in result["phases"]] == ["prepare", "draft"]


def test_predict_artifact_agent_phase_never_invokes_live_llm_provider(
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    runner = importlib.import_module("graph_agent.core.runner")
    skill_root = tmp_path / "artifact-runtime-predict-agent"
    _write_single_agent_skill(skill_root)
    manifest = compile_artifact(source_root=skill_root, skill_resolver=mock_skill_resolver)
    workspace_dir = tmp_path / "workspace"
    provider = FailIfInvokedProvider()

    request = PredictArtifactRequest(
        artifact_ref=manifest.artifact_ref,
        inputs={"topic": "ceres"},
        execution_context={
            "artifact_root": str(skill_root),
            "workspace_dir": str(workspace_dir),
            "thread_id": "artifact-agent-predict",
            "mock_llm": {"draft": {"answer": "mocked-agent-answer"}},
        },
        idempotency_key="idem-agent-predict-provider-trap",
    )

    session = runner.predict_artifact(
        request,
        skill_resolver=mock_skill_resolver,
        llm_provider=provider,
    )

    assert isinstance(session, RunSession)
    assert provider.calls == 0
    result_path = workspace_dir / "runs" / session.run_id / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["source"] == "predict"
    assert result["success"] is True
    assert result["context"]["answer"] == "mocked-agent-answer"


def test_predict_graph_resolves_engine_predict_model_before_live_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    from graph_agent.core import graph_assembler
    from graph_agent.core._predict_internal.interception import PredictGatewayChatModel
    from graph_agent.core._predict_internal.strategy import MockStrategy
    from graph_agent.core.compiler import compile_skill
    from graph_agent.core.runner import SDKPredictContext

    skill_root = tmp_path / "artifact-runtime-predict-agent"
    _write_single_agent_skill(skill_root)
    compiled = compile_skill(skill_root, cache=False, skill_resolver=mock_skill_resolver)
    provider = FailIfInvokedProvider()
    captured: dict[str, Any] = {}

    class _Agent:
        def invoke(self, input: Any, config: Any | None = None, **kwargs: Any) -> Any:
            del config, kwargs
            return input

    def fake_create_agent(**kwargs: Any) -> _Agent:
        captured["model"] = kwargs["model"]
        return _Agent()

    monkeypatch.setattr(graph_assembler, "create_agent", fake_create_agent, raising=False)

    graph = graph_assembler.assemble_graph(
        compiled,
        llm_provider=provider,
        skill_resolver=mock_skill_resolver,
        predict_context=SDKPredictContext(MockStrategy.from_param({"draft": {"answer": "mocked"}})),
    ).graph
    graph.invoke(
        {"data": {"topic": "ceres"}, "flow": {"thread_id": "predict-d4"}, "messages": []},
        config={"configurable": {"thread_id": "predict-d4"}},
    )

    assert isinstance(captured["model"], PredictGatewayChatModel)
    assert provider.calls == 0


def test_predict_graph_predict_context_overrides_explicit_chat_model(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    from graph_agent.core import graph_assembler
    from graph_agent.core._predict_internal.interception import PredictGatewayChatModel
    from graph_agent.core._predict_internal.strategy import MockStrategy
    from graph_agent.core.compiler import compile_skill
    from graph_agent.core.runner import SDKPredictContext

    skill_root = tmp_path / "artifact-runtime-predict-explicit-chat-model"
    _write_single_agent_skill(skill_root)
    compiled = compile_skill(skill_root, cache=False, skill_resolver=mock_skill_resolver)
    live_chat_model = object()
    captured: dict[str, Any] = {}

    class _Agent:
        def invoke(self, input: Any, config: Any | None = None, **kwargs: Any) -> Any:
            del config, kwargs
            return input

    def fake_create_agent(**kwargs: Any) -> _Agent:
        captured["model"] = kwargs["model"]
        return _Agent()

    monkeypatch.setattr(graph_assembler, "create_agent", fake_create_agent, raising=False)

    graph = graph_assembler.assemble_graph(
        compiled,
        chat_model=live_chat_model,
        skill_resolver=mock_skill_resolver,
        predict_context=SDKPredictContext(MockStrategy.from_param({"draft": {"answer": "mocked"}})),
    ).graph
    graph.invoke(
        {"data": {"topic": "ceres"}, "flow": {"thread_id": "predict-d4-explicit"}, "messages": []},
        config={"configurable": {"thread_id": "predict-d4-explicit"}},
    )

    assert isinstance(captured["model"], PredictGatewayChatModel)
    assert captured["model"] is not live_chat_model


def test_predict_artifact_replays_cached_file_result_through_run_artifact_store(
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    runner = importlib.import_module("graph_agent.core.runner")
    idempotency_key = "idem-real-graph-predict-store-after-file-cache"
    getattr(runner, "_RUN_CACHE", {}).pop(idempotency_key, None)
    skill_root = tmp_path / "artifact-runtime-real-graph"
    _write_two_phase_logic_skill(skill_root)
    manifest = compile_artifact(source_root=skill_root, skill_resolver=mock_skill_resolver)
    workspace_dir = tmp_path / "workspace"
    request = PredictArtifactRequest(
        artifact_ref=manifest.artifact_ref,
        inputs={"topic": "neptune"},
        execution_context={
            "artifact_root": str(skill_root),
            "workspace_dir": str(workspace_dir),
            "thread_id": "artifact-real-predict-cache-store",
            "mock_llm": {"draft": {"answer": "mocked-answer"}},
        },
        idempotency_key=idempotency_key,
    )

    first = runner.predict_artifact(request, skill_resolver=mock_skill_resolver)
    assert isinstance(first, RunSession)
    assert first.result_ref is not None
    assert first.result_ref.startswith("file://")

    store = HashingFakeRunArtifactStore()
    second = runner.predict_artifact(
        request,
        run_artifact_store=store,
        skill_resolver=mock_skill_resolver,
    )

    assert isinstance(second, RunSession)
    assert second.result_ref is not None
    assert second.result_ref.startswith("bytes://")
    assert store.put_calls == 1
    stored = store.get_object(hash=second.result_ref.removeprefix("bytes://"))
    result = json.loads(stored.decode("utf-8"))
    assert result["source"] == "predict"
    assert result["context"]["prepared"] == "prepared:neptune"


def test_predict_artifact_real_graph_persists_result_through_run_artifact_store(
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    from graph_agent.core.storage_contracts import ObjectRef

    runner = importlib.import_module("graph_agent.core.runner")
    skill_root = tmp_path / "artifact-runtime-real-graph"
    _write_two_phase_logic_skill(skill_root)
    manifest = compile_artifact(source_root=skill_root, skill_resolver=mock_skill_resolver)
    workspace_dir = tmp_path / "workspace"

    class FakeRunArtifactStore:
        def __init__(self) -> None:
            self.objects: dict[str, bytes] = {}

        def begin_run(self, run_id: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
            return {"run_id": run_id, "metadata": metadata or {}}

        def put_batch(self, run_id: str, objects: dict[str, bytes]) -> dict[str, ObjectRef]:
            refs: dict[str, ObjectRef] = {}
            for path, content in objects.items():
                content_hash = f"sha256:{run_id}-{path}"
                self.objects[content_hash] = content
                refs[path] = ObjectRef(
                    bytes_ref=f"bytes://{content_hash}",
                    content_hash=content_hash,
                    size_bytes=len(content),
                    path=path,
                )
            return refs

        def seal_run(self, run_id: str) -> object:
            return {"run_id": run_id, "sealed": True}

        def get_object(self, *, hash: str) -> bytes:
            return self.objects[hash]

    store = FakeRunArtifactStore()
    request = PredictArtifactRequest(
        artifact_ref=manifest.artifact_ref,
        inputs={"topic": "jupiter"},
        execution_context={
            "artifact_root": str(skill_root),
            "workspace_dir": str(workspace_dir),
            "thread_id": "artifact-real-predict-store",
            "mock_llm": {"draft": {"answer": "mocked-answer"}},
        },
        idempotency_key="idem-real-graph-predict-store",
    )

    session = runner.predict_artifact(
        request,
        run_artifact_store=store,
        skill_resolver=mock_skill_resolver,
    )

    assert isinstance(session, RunSession)
    assert session.result_ref is not None
    assert session.result_ref.startswith("bytes://")
    stored = store.get_object(hash=session.result_ref.removeprefix("bytes://"))
    result = json.loads(stored.decode("utf-8"))
    assert result["source"] == "predict"
    assert result["context"]["prepared"] == "prepared:jupiter"


def test_run_artifact_store_result_rejects_missing_object_ref() -> None:
    runner = importlib.import_module("graph_agent.core.runner")
    request = RunArtifactRequest(
        artifact_ref=_artifact_ref(),
        inputs={"topic": "red"},
        execution_context={"workspace_id": "local"},
        idempotency_key="idem-empty-store-refs",
    )
    getattr(runner, "_RUN_CACHE", {}).pop(request.idempotency_key, None)
    store = EmptyRefsRunArtifactStore()

    with pytest.raises(Exception) as exc_info:
        runner.run_artifact(
            request,
            artifact_executor=lambda _request: {"success": True},
            run_artifact_store=store,
        )

    assert getattr(exc_info.value, "error_code", None) == "artifact.missing_object_ref"
    assert store.put_calls == 1
    assert store.sealed == []


def test_run_artifact_store_result_rejects_wrong_path_object_ref() -> None:
    runner = importlib.import_module("graph_agent.core.runner")
    request = RunArtifactRequest(
        artifact_ref=_artifact_ref(),
        inputs={"topic": "red"},
        execution_context={"workspace_id": "local"},
        idempotency_key="idem-wrong-path-store-refs",
    )
    getattr(runner, "_RUN_CACHE", {}).pop(request.idempotency_key, None)
    store = WrongPathRefsRunArtifactStore()

    with pytest.raises(Exception) as exc_info:
        runner.run_artifact(
            request,
            artifact_executor=lambda _request: {"success": True},
            run_artifact_store=store,
        )

    assert isinstance(exc_info.value, runner.MissingRunArtifactObjectRefError)
    assert getattr(exc_info.value, "error_code", None) == "artifact.missing_object_ref"
    assert getattr(exc_info.value, "details", {}) == {
        "run_id": "run-artifact-runtime-demo-idem-wrong-path-store-refs",
        "path": "outputs.json",
    }
    assert store.put_calls == 1
    assert store.sealed == []
