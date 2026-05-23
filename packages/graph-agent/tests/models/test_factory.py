from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest
from graph_agent.models import factory


class _FakeChatModel:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


def test_first_env_returns_first_present_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FIRST_KEY", raising=False)
    monkeypatch.setenv("SECOND_KEY", "second")

    assert factory._first_env("FIRST_KEY", "SECOND_KEY") == "second"


def test_first_env_returns_none_when_all_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FIRST_KEY", raising=False)
    monkeypatch.delenv("SECOND_KEY", raising=False)

    assert factory._first_env("FIRST_KEY", "SECOND_KEY") is None


def test_create_openai_model_from_explicit_args(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "langchain_openai",
        SimpleNamespace(ChatOpenAI=_FakeChatModel),
    )

    model = factory.create_chat_model(
        provider="openai_compatible",
        model="gpt-test",
        api_key="key",
        base_url="https://example.test/v1",
        timeout=12,
        temperature=0.1,
        custom="value",
    )

    assert isinstance(model, _FakeChatModel)
    assert model.kwargs == {
        "model": "gpt-test",
        "base_url": "https://example.test/v1",
        "timeout": 12,
        "temperature": 0.1,
        "custom": "value",
        "api_key": "key",
    }


def test_create_openai_model_uses_environment_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "langchain_openai",
        SimpleNamespace(ChatOpenAI=_FakeChatModel),
    )
    monkeypatch.setenv("GRAPH_AGENT_MODEL_PROVIDER", "openai")
    monkeypatch.setenv("GRAPH_AGENT_MODEL", "env-model")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("GRAPH_AGENT_API_KEY", "env-key")
    monkeypatch.setenv("GRAPH_AGENT_BASE_URL", "https://env.example/v1")

    model = factory.create_chat_model()

    assert isinstance(model, _FakeChatModel)
    assert model.kwargs["model"] == "env-model"
    assert model.kwargs["api_key"] == "env-key"
    assert model.kwargs["base_url"] == "https://env.example/v1"


def test_create_anthropic_model_from_explicit_args(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "langchain_anthropic",
        SimpleNamespace(ChatAnthropic=_FakeChatModel),
    )

    model = factory.create_chat_model(
        provider="anthropic_compatible",
        model="claude-test",
        api_key="key",
        base_url="https://anthropic.example",
        timeout=20,
        temperature=0.2,
    )

    assert isinstance(model, _FakeChatModel)
    assert model.kwargs == {
        "model_name": "claude-test",
        "base_url": "https://anthropic.example",
        "timeout": 20,
        "temperature": 0.2,
        "api_key": "key",
    }


def test_create_anthropic_model_uses_environment_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "langchain_anthropic",
        SimpleNamespace(ChatAnthropic=_FakeChatModel),
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://anthropic.env")

    model = factory.create_chat_model(provider="anthropic")

    assert isinstance(model, _FakeChatModel)
    assert model.kwargs["model_name"] == "claude-3-5-sonnet-latest"
    assert model.kwargs["api_key"] == "anthropic-key"
    assert model.kwargs["base_url"] == "https://anthropic.env"


def test_create_chat_model_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unsupported chat model provider"):
        factory.create_chat_model(provider="unsupported")
