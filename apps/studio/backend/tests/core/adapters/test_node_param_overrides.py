"""PR3: per-node LLM param overrides reach the gateway resolver.

The run worker sets STUDIO_RUNTIME_CONFIG_PATH to the run's runtime_config snapshot;
_GatewayBackedLLMProvider.invoke reads the focused node's override and passes
thinking / max_output_tokens / temperature to resolver.resolve() (where a
present override wins over the role default). Node overrides stay a studio-side
concern — the engine + gateway resolver never learn the skill.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from app.core.adapters.engine import _GatewayBackedLLMProvider, _node_param_overrides
from graph_agent.core.llm_provider import LLMProviderRequest


def _write_params(path: Path, nodes: dict[str, dict[str, Any]]) -> None:
    path.write_text(json.dumps({"llm": {"node_params": {"nodes": nodes}}}), encoding="utf-8")


def test_overrides_absent_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STUDIO_RUNTIME_CONFIG_PATH", raising=False)
    assert _node_param_overrides("phase") == {}


def test_overrides_read_focused_node(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    params = tmp_path / "runtime_config.json"
    _write_params(
        params,
        {
            "writer": {"enabled": True, "thinking": True, "max_output_tokens": 2048, "temperature": 0.3},
            "other": {"enabled": True, "thinking": False},
        },
    )
    monkeypatch.setenv("STUDIO_RUNTIME_CONFIG_PATH", str(params))
    assert _node_param_overrides("writer") == {
        "thinking": True,
        "max_output_tokens": 2048,
        "temperature": 0.3,
    }
    # a different node's overrides don't leak
    assert _node_param_overrides("other") == {"thinking": False}
    # unknown node / no phase -> empty
    assert _node_param_overrides("nope") == {}
    assert _node_param_overrides(None) == {}


def test_null_fields_dropped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    params = tmp_path / "runtime_config.json"
    _write_params(params, {"writer": {"enabled": True, "thinking": None, "max_output_tokens": 4096, "temperature": None}})
    monkeypatch.setenv("STUDIO_RUNTIME_CONFIG_PATH", str(params))
    assert _node_param_overrides("writer") == {"max_output_tokens": 4096}


def test_disabled_node_params_are_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    params = tmp_path / "runtime_config.json"
    _write_params(params, {"writer": {"enabled": False, "thinking": True, "temperature": 0.8}})
    monkeypatch.setenv("STUDIO_RUNTIME_CONFIG_PATH", str(params))
    assert _node_param_overrides("writer") == {}


def test_missing_file_is_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STUDIO_RUNTIME_CONFIG_PATH", str(tmp_path / "absent.json"))
    assert _node_param_overrides("writer") == {}


class _FakeChunk:
    """One slice, addable the way LangChain chunks are."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.response_metadata: dict[str, Any] = {}
        self.tool_calls: list[Any] = []
        self.usage_metadata = None

    def __add__(self, other: _FakeChunk) -> _FakeChunk:
        return _FakeChunk(self.content + other.content)


class _RecordingResolver:
    def __init__(self) -> None:
        self.resolve_kwargs: dict[str, Any] = {}

    def resolve(self, role: str, **kwargs: Any) -> Any:
        self.resolve_kwargs = {"role": role, **kwargs}

        class _Model:
            model_name = "fake"

            def stream(self, messages: Any, stop: Any = None) -> Any:
                del messages, stop
                yield _FakeChunk("ok")

        return _Model()


def test_streaming_passes_node_overrides_to_resolve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    params = tmp_path / "runtime_config.json"
    _write_params(params, {"writer": {"enabled": True, "thinking": True, "max_output_tokens": 999, "temperature": 0.9}})
    monkeypatch.setenv("STUDIO_RUNTIME_CONFIG_PATH", str(params))

    resolver = _RecordingResolver()
    provider = _GatewayBackedLLMProvider(resolver)
    list(
        provider.stream(
            LLMProviderRequest(role="graph_agent", messages=[], metadata={"phase_name": "writer"})
        )
    )

    assert resolver.resolve_kwargs["thinking_enabled"] is True
    assert resolver.resolve_kwargs["max_output_tokens"] == 999
    assert resolver.resolve_kwargs["temperature"] == 0.9
    assert resolver.resolve_kwargs["phase_name"] == "writer"


def test_streaming_without_override_passes_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("STUDIO_RUNTIME_CONFIG_PATH", raising=False)
    resolver = _RecordingResolver()
    provider = _GatewayBackedLLMProvider(resolver)
    list(
        provider.stream(
            LLMProviderRequest(role="graph_agent", messages=[], metadata={"phase_name": "writer"})
        )
    )
    assert resolver.resolve_kwargs["thinking_enabled"] is None
    assert resolver.resolve_kwargs["max_output_tokens"] is None
    assert resolver.resolve_kwargs["temperature"] is None
