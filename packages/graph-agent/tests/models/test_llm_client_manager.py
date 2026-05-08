from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
from graph_agent.config.llm_config import ModelDef, ProviderDef, ResolvedProvider
from graph_agent.models.llm_client_manager import LLMClientManager


def _provider(
    provider_code: str = "OC_DS",
    provider_type: str = "openai_compatible",
    *,
    api_key_env: str = "TEST_API_KEY",
    api_key_env_fallback: str = "",
) -> ProviderDef:
    return ProviderDef(
        code=provider_code,
        name=f"Provider {provider_code}",
        type=provider_type,
        api_key_env=api_key_env,
        api_key_env_fallback=api_key_env_fallback,
        base_url="https://provider.example/v1",
        llm_base_url="https://llm.provider.example/v1",
        timeout=12,
        trust_env=False,
    )


def _model(
    provider_code: str = "OC_DS",
    model_name: str = "test-model",
    *,
    reasoning: bool = False,
) -> ModelDef:
    return ModelDef(
        code="TM",
        name="Test Model",
        reasoning=reasoning,
        min_max_tokens=64,
        providers={provider_code: model_name},
    )


def _rp(
    provider_code: str = "OC_DS",
    provider_type: str = "openai_compatible",
    model_name: str = "test-model",
    *,
    provider_options: dict[str, Any] | None = None,
    reasoning: bool = False,
) -> ResolvedProvider:
    return ResolvedProvider(
        provider_code=provider_code,
        provider_def=_provider(provider_code, provider_type),
        model_name=model_name,
        model_def=_model(provider_code, model_name, reasoning=reasoning),
        provider_options=provider_options or {},
    )


def _openai_response(
    content: str = "hello",
    *,
    finish_reason: str | None = "stop",
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
) -> SimpleNamespace:
    return SimpleNamespace(
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason=finish_reason,
            )
        ],
    )


def _anthropic_response(
    content: str = "hello",
    *,
    stop_reason: str | None = "end_turn",
    input_tokens: int = 7,
    output_tokens: int = 3,
) -> SimpleNamespace:
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=content)],
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
        stop_reason=stop_reason,
    )


@pytest.fixture(autouse=True)
def _clean_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    LLMClientManager._clients.clear()
    LLMClientManager._usage_stats.clear()
    LLMClientManager._provider_down_cache.clear()
    monkeypatch.setenv("TEST_API_KEY", "secret")
    monkeypatch.delenv("TEST_FALLBACK_KEY", raising=False)


def test_get_openai_client_caches_by_provider() -> None:
    pdef = _provider()

    first = LLMClientManager._get_openai_client("OC_DS", pdef)
    second = LLMClientManager._get_openai_client("OC_DS", pdef)

    assert first is second
    assert "OC_DS" in LLMClientManager.get_usage_stats()


def test_get_openai_client_uses_fallback_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PRIMARY_KEY", raising=False)
    monkeypatch.setenv("TEST_FALLBACK_KEY", "fallback-secret")
    pdef = _provider(api_key_env="PRIMARY_KEY", api_key_env_fallback="TEST_FALLBACK_KEY")

    client = LLMClientManager._get_openai_client("OC_FB", pdef)

    assert client is LLMClientManager._clients["openai:OC_FB"]


def test_get_openai_client_timeout_override_uses_separate_cache() -> None:
    pdef = _provider()

    default_client = LLMClientManager._get_openai_client("OC_DS", pdef)
    probe_client = LLMClientManager._get_openai_client("OC_DS", pdef, timeout_override=5.0)

    assert default_client is not probe_client
    assert "openai:OC_DS:timeout:5" in LLMClientManager._clients


def test_get_openai_client_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISSING_KEY", raising=False)

    with pytest.raises(ValueError, match="MISSING_KEY not configured"):
        LLMClientManager._get_openai_client("OC_MISSING", _provider(api_key_env="MISSING_KEY"))


def test_get_anthropic_client_caches_by_provider() -> None:
    pdef = _provider("JK_CL_ANT", "anthropic_compatible")

    first = LLMClientManager._get_anthropic_client("JK_CL_ANT", pdef)
    second = LLMClientManager._get_anthropic_client("JK_CL_ANT", pdef)

    assert first is second
    assert "JK_CL_ANT" in LLMClientManager.get_usage_stats()


def test_probe_openai_compatible_success() -> None:
    rp = _rp()
    client = MagicMock()
    client.chat.completions.create.return_value = _openai_response()

    with patch.object(LLMClientManager, "_get_openai_client", return_value=client):
        assert LLMClientManager._probe_provider(rp) is True

    client.chat.completions.create.assert_called_once()
    assert not LLMClientManager._is_provider_marked_down(rp.provider_code, rp.model_name)


def test_probe_openai_compatible_failure_marks_down() -> None:
    rp = _rp()
    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError("dns failed")

    with patch.object(LLMClientManager, "_get_openai_client", return_value=client):
        assert LLMClientManager._probe_provider(rp) is False

    assert LLMClientManager._is_provider_marked_down(rp.provider_code, rp.model_name)


def test_probe_anthropic_compatible_success() -> None:
    rp = _rp("JK_CL_ANT", "anthropic_compatible")
    client = MagicMock()
    client.messages.create.return_value = _anthropic_response()

    with patch.object(LLMClientManager, "_get_anthropic_client", return_value=client):
        assert LLMClientManager._probe_provider(rp) is True

    client.messages.create.assert_called_once()


def test_probe_anthropic_compatible_failure_marks_down() -> None:
    rp = _rp("JK_CL_ANT", "anthropic_compatible")
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("bad upstream")

    with patch.object(LLMClientManager, "_get_anthropic_client", return_value=client):
        assert LLMClientManager._probe_provider(rp) is False

    assert LLMClientManager._is_provider_marked_down(rp.provider_code, rp.model_name)


def test_probe_wavespeed_returns_true() -> None:
    assert LLMClientManager._probe_provider(_rp("WS_LLM", "wavespeed_any_llm")) is True


def test_probe_unknown_provider_returns_true() -> None:
    assert LLMClientManager._probe_provider(_rp("GM_OFF", "gemini_official")) is True


def test_mark_provider_down_sets_ttl() -> None:
    LLMClientManager._mark_provider_down("OC_DS", "model")

    assert LLMClientManager._is_provider_marked_down("OC_DS", "model")


def test_mark_provider_down_ttl_expires() -> None:
    LLMClientManager._mark_provider_down("OC_DS", "model")
    key = LLMClientManager._make_down_key("OC_DS", "model")
    LLMClientManager._provider_down_cache[key] = time.monotonic() - 0.1

    assert not LLMClientManager._is_provider_marked_down("OC_DS", "model")
    assert key not in LLMClientManager._provider_down_cache


def test_record_usage_accumulates() -> None:
    LLMClientManager.record_usage("OC_DS", 10, 5)
    LLMClientManager.record_usage("OC_DS", 1, 2)

    assert LLMClientManager.get_usage_stats()["OC_DS"] == {
        "total_calls": 2,
        "prompt_tokens": 11,
        "completion_tokens": 7,
        "total_tokens": 18,
    }


def test_get_usage_stats_returns_copy() -> None:
    LLMClientManager.record_usage("OC_DS", 10, 5)
    returned = LLMClientManager.get_usage_stats()

    returned["OC_DS"]["prompt_tokens"] = 999

    assert LLMClientManager.get_usage_stats()["OC_DS"]["prompt_tokens"] == 10


def test_reset_stats_clears_all() -> None:
    LLMClientManager.record_usage("OC_DS", 10, 5)

    LLMClientManager.reset_stats()

    assert LLMClientManager.get_usage_stats() == {}


def test_call_openai_compatible_normal() -> None:
    client = MagicMock()
    client.chat.completions.create.return_value = _openai_response(
        "ok",
        prompt_tokens=11,
        completion_tokens=4,
    )

    result = LLMClientManager._call_openai_compatible(
        client,
        "model",
        [{"role": "user", "content": "hello"}],
        128,
        0.2,
    )

    assert result == {
        "content": "ok",
        "usage": {"prompt_tokens": 11, "completion_tokens": 4, "total_tokens": 15},
        "finish_reason": "stop",
    }


def test_call_openai_compatible_forwards_and_parses_tool_calls() -> None:
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=2, completion_tokens=1, total_tokens=3),
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="",
                    tool_calls=[
                        SimpleNamespace(
                            id="call_1",
                            type="function",
                            function=SimpleNamespace(
                                name="finish_task",
                                arguments='{"ok": true}',
                            ),
                        )
                    ],
                ),
                finish_reason="tool_calls",
            )
        ],
    )

    result = LLMClientManager._call_openai_compatible(
        client,
        "model",
        [{"role": "user", "content": "hello"}],
        128,
        0.2,
        tools=[{"type": "function", "function": {"name": "finish_task"}}],
        tool_choice="finish_task",
    )

    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["tools"] == [{"type": "function", "function": {"name": "finish_task"}}]
    assert kwargs["tool_choice"] == "finish_task"
    assert result["tool_calls"] == [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "finish_task", "arguments": '{"ok": true}'},
        }
    ]


def test_call_openai_compatible_handles_missing_usage() -> None:
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        usage=None,
        choices=[SimpleNamespace(message=SimpleNamespace(content=None), finish_reason=None)],
    )

    result = LLMClientManager._call_openai_compatible(
        client,
        "model",
        [{"role": "user", "content": "hello"}],
        128,
        0.2,
    )

    assert result["content"] == ""
    assert result["usage"] == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    assert result["finish_reason"] is None


def test_call_openai_compatible_handles_empty_choices() -> None:
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        usage={"prompt_tokens": "3", "completion_tokens": "bad", "total_tokens": 0},
        choices=[],
    )

    result = LLMClientManager._call_openai_compatible(
        client,
        "model",
        [{"role": "user", "content": "hello"}],
        128,
        0.2,
    )

    assert result["content"] == ""
    assert result["usage"] == {"prompt_tokens": 3, "completion_tokens": 0, "total_tokens": 3}


def test_call_anthropic_compatible_normal() -> None:
    client = MagicMock()
    client.messages.create.return_value = _anthropic_response("anth ok")

    result = LLMClientManager._call_anthropic_compatible(
        client,
        "claude",
        [
            {"role": "system", "content": "rules"},
            {"role": "user", "content": "hello"},
        ],
        128,
        0.4,
    )

    assert result == {
        "content": "anth ok",
        "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
        "finish_reason": "end_turn",
    }
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["system"] == "rules"
    assert kwargs["temperature"] == 0.4


def test_call_anthropic_compatible_forwards_and_parses_tool_calls() -> None:
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        content=[
            SimpleNamespace(
                type="tool_use",
                id="toolu_1",
                name="finish_task",
                input={"ok": True},
            )
        ],
        usage=SimpleNamespace(input_tokens=5, output_tokens=2),
        stop_reason="tool_use",
    )

    result = LLMClientManager._call_anthropic_compatible(
        client,
        "claude",
        [{"role": "user", "content": "hello"}],
        128,
        0.4,
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "finish_task",
                    "description": "Finish",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
    )

    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["tools"] == [
        {
            "name": "finish_task",
            "input_schema": {"type": "object", "properties": {}},
            "description": "Finish",
        }
    ]
    assert result["tool_calls"] == [
        {
            "id": "toolu_1",
            "type": "function",
            "function": {"name": "finish_task", "arguments": '{"ok": true}'},
        }
    ]


def test_call_anthropic_compatible_thinking_adaptive_fallback() -> None:
    client = MagicMock()
    client.messages.create.side_effect = [
        RuntimeError("extra inputs are not permitted: adaptive"),
        _anthropic_response("fallback ok"),
    ]

    result = LLMClientManager._call_anthropic_compatible(
        client,
        "claude",
        [{"role": "user", "content": "hello"}],
        128,
        0.4,
        reasoning=True,
    )

    assert result["content"] == "fallback ok"
    first_call, second_call = client.messages.create.call_args_list
    assert first_call.kwargs["thinking"]["type"] == "adaptive"
    assert second_call.kwargs["thinking"]["type"] == "enabled"
    assert second_call.kwargs["temperature"] == 1.0


def test_call_anthropic_compatible_thinking_reraises_non_adaptive_error() -> None:
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("auth failed")

    with pytest.raises(RuntimeError, match="auth failed"):
        LLMClientManager._call_anthropic_compatible(
            client,
            "claude",
            [{"role": "user", "content": "hello"}],
            128,
            0.4,
            reasoning=True,
        )


def test_call_anthropic_compatible_handles_non_text_content() -> None:
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        content=None,
        usage=SimpleNamespace(input_tokens=1, output_tokens=2),
        stop_reason=None,
    )

    result = LLMClientManager._call_anthropic_compatible(
        client,
        "claude",
        [{"role": "developer", "content": 123}],
        128,
        0.4,
    )

    assert result["content"] == ""
    assert result["usage"] == {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}


def test_call_wavespeed_502_retries_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = [
        httpx.Response(502, text="bad gateway"),
        httpx.Response(503, text="busy"),
        httpx.Response(
            200,
            json={"code": 200, "data": {"status": "completed", "outputs": ["ok"]}},
        ),
    ]
    post = MagicMock(side_effect=responses)
    sleep = MagicMock()
    monkeypatch.setattr("graph_agent.models.llm_client_manager.httpx.post", post)
    monkeypatch.setattr("graph_agent.models.llm_client_manager.time.sleep", sleep)

    result = LLMClientManager._call_wavespeed_any_llm(
        _provider("WS_LLM", "wavespeed_any_llm"),
        [{"role": "system", "content": "rules"}, {"role": "user", "content": "hello"}],
        "anthropic/claude",
        64,
        0.7,
        reasoning=True,
    )

    assert result["content"] == "ok"
    assert post.call_count == 3
    sleep.assert_any_call(10)
    sleep.assert_any_call(20)
    payload = post.call_args.kwargs["json"]
    assert payload["system_prompt"] == "rules"
    assert payload["reasoning"] is True


def test_call_wavespeed_502_max_retries_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "graph_agent.models.llm_client_manager.httpx.post",
        MagicMock(return_value=httpx.Response(502, text="bad gateway")),
    )
    monkeypatch.setattr("graph_agent.models.llm_client_manager.time.sleep", MagicMock())

    with pytest.raises(RuntimeError, match="WaveSpeed HTTP 502"):
        LLMClientManager._call_wavespeed_any_llm(
            _provider("WS_LLM", "wavespeed_any_llm"),
            [{"role": "user", "content": "hello"}],
            "anthropic/claude",
            64,
            0.7,
            reasoning=False,
        )


def test_call_wavespeed_application_error_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "graph_agent.models.llm_client_manager.httpx.post",
        MagicMock(return_value=httpx.Response(200, json={"code": 500, "message": "oops"})),
    )

    with pytest.raises(RuntimeError, match="WaveSpeed error: oops"):
        LLMClientManager._call_wavespeed_any_llm(
            _provider("WS_LLM", "wavespeed_any_llm"),
            [{"role": "user", "content": "hello"}],
            "anthropic/claude",
            64,
            0.7,
            reasoning=False,
        )


def test_call_wavespeed_non_object_response_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "graph_agent.models.llm_client_manager.httpx.post",
        MagicMock(return_value=httpx.Response(200, json=["not", "object"])),
    )

    with pytest.raises(RuntimeError, match="non-object response"):
        LLMClientManager._call_wavespeed_any_llm(
            _provider("WS_LLM", "wavespeed_any_llm"),
            [{"role": "user", "content": "hello"}],
            "anthropic/claude",
            64,
            0.7,
            reasoning=False,
        )


def test_call_wavespeed_missing_data_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "graph_agent.models.llm_client_manager.httpx.post",
        MagicMock(return_value=httpx.Response(200, json={"code": 200, "data": None})),
    )

    with pytest.raises(RuntimeError, match="no data object"):
        LLMClientManager._call_wavespeed_any_llm(
            _provider("WS_LLM", "wavespeed_any_llm"),
            [{"role": "user", "content": "hello"}],
            "anthropic/claude",
            64,
            0.7,
            reasoning=False,
        )


def test_call_wavespeed_task_failed_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "graph_agent.models.llm_client_manager.httpx.post",
        MagicMock(
            return_value=httpx.Response(
                200,
                json={"code": 200, "data": {"status": "failed", "error": "model down"}},
            )
        ),
    )

    with pytest.raises(RuntimeError, match="WaveSpeed task failed: model down"):
        LLMClientManager._call_wavespeed_any_llm(
            _provider("WS_LLM", "wavespeed_any_llm"),
            [{"role": "user", "content": "hello"}],
            "anthropic/claude",
            64,
            0.7,
            reasoning=False,
        )


def test_call_wavespeed_unexpected_status_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "graph_agent.models.llm_client_manager.httpx.post",
        MagicMock(
            return_value=httpx.Response(200, json={"code": 200, "data": {"status": "queued"}})
        ),
    )

    with pytest.raises(RuntimeError, match="unexpected status: queued"):
        LLMClientManager._call_wavespeed_any_llm(
            _provider("WS_LLM", "wavespeed_any_llm"),
            [{"role": "user", "content": "hello"}],
            "anthropic/claude",
            64,
            0.7,
            reasoning=False,
        )


def test_call_wavespeed_no_outputs_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "graph_agent.models.llm_client_manager.httpx.post",
        MagicMock(
            return_value=httpx.Response(
                200, json={"code": 200, "data": {"status": "completed", "outputs": []}}
            )
        ),
    )

    with pytest.raises(RuntimeError, match="returned no outputs"):
        LLMClientManager._call_wavespeed_any_llm(
            _provider("WS_LLM", "wavespeed_any_llm"),
            [{"role": "user", "content": "hello"}],
            "anthropic/claude",
            64,
            0.7,
            reasoning=False,
        )


def test_dispatch_provider_call_routes_openai_and_records_usage() -> None:
    client = MagicMock()
    client.chat.completions.create.return_value = _openai_response("openai ok")

    with patch.object(LLMClientManager, "_get_openai_client", return_value=client):
        result = LLMClientManager._dispatch_provider_call(
            _rp(),
            [{"role": "user", "content": "hello"}],
            64,
            0.7,
        )

    assert result["content"] == "openai ok"
    assert LLMClientManager.get_usage_stats()["OC_DS"]["total_calls"] == 1


def test_dispatch_provider_call_routes_anthropic() -> None:
    client = MagicMock()
    client.messages.create.return_value = _anthropic_response("anth ok")

    with patch.object(LLMClientManager, "_get_anthropic_client", return_value=client):
        result = LLMClientManager._dispatch_provider_call(
            _rp("JK_CL_ANT", "anthropic_compatible"),
            [{"role": "user", "content": "hello"}],
            64,
            0.7,
            reasoning=True,
        )

    assert result["content"] == "anth ok"
    assert LLMClientManager.get_usage_stats()["JK_CL_ANT"]["completion_tokens"] == 3


def test_dispatch_provider_call_routes_wavespeed() -> None:
    with patch.object(
        LLMClientManager,
        "_call_wavespeed_any_llm",
        return_value={
            "content": "ws ok",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "finish_reason": None,
        },
    ) as call:
        result = LLMClientManager._dispatch_provider_call(
            _rp("WS_LLM", "wavespeed_any_llm"),
            [{"role": "user", "content": "hello"}],
            64,
            0.7,
            reasoning=True,
        )

    assert result["content"] == "ws ok"
    call.assert_called_once()


def test_dispatch_provider_call_routes_wavespeed_tools_through_openai_endpoint() -> None:
    client = MagicMock()
    client.chat.completions.create.return_value = _openai_response("tool ok")

    with (
        patch.object(LLMClientManager, "_get_openai_client", return_value=client) as get_client,
        patch.object(LLMClientManager, "_call_wavespeed_any_llm") as wavespeed_call,
    ):
        result = LLMClientManager._dispatch_provider_call(
            _rp("WS_LLM", "wavespeed_any_llm"),
            [{"role": "user", "content": "hello"}],
            64,
            0.7,
            tools=[{"type": "function", "function": {"name": "finish_task"}}],
            tool_choice="finish_task",
        )

    assert result["content"] == "tool ok"
    get_client.assert_called_once()
    wavespeed_call.assert_not_called()
    assert client.chat.completions.create.call_args.kwargs["tools"] == [
        {"type": "function", "function": {"name": "finish_task"}}
    ]


def test_dispatch_provider_call_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unknown provider type"):
        LLMClientManager._dispatch_provider_call(
            _rp("GM_OFF", "gemini_official"),
            [{"role": "user", "content": "hello"}],
            64,
            0.7,
        )


def test_dispatch_provider_call_escalates_tokens_on_truncation() -> None:
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _openai_response("cut", finish_reason="length", prompt_tokens=10, completion_tokens=4),
        _openai_response("complete", finish_reason="stop", prompt_tokens=11, completion_tokens=5),
    ]

    with patch.object(LLMClientManager, "_get_openai_client", return_value=client):
        result = LLMClientManager._dispatch_provider_call(
            _rp(provider_options={"max_max_tokens": 128}),
            [{"role": "user", "content": "hello"}],
            32,
            0.7,
        )

    assert result["content"] == "complete"
    assert client.chat.completions.create.call_args_list[0].kwargs["max_tokens"] == 32
    assert client.chat.completions.create.call_args_list[1].kwargs["max_tokens"] == 64
    assert LLMClientManager.get_usage_stats()["OC_DS"]["total_calls"] == 2


def test_dispatch_provider_call_stops_escalation_at_cap() -> None:
    client = MagicMock()
    client.chat.completions.create.return_value = _openai_response(
        "still cut",
        finish_reason="length",
        prompt_tokens=2,
        completion_tokens=1,
    )

    with patch.object(LLMClientManager, "_get_openai_client", return_value=client):
        result = LLMClientManager._dispatch_provider_call(
            _rp(provider_options={"max_max_tokens": 32}),
            [{"role": "user", "content": "hello"}],
            32,
            0.7,
        )

    assert result["finish_reason"] == "length"
    assert client.chat.completions.create.call_count == 1


def test_record_usage_from_result_handles_missing_usage() -> None:
    LLMClientManager._record_usage_from_result("OC_DS", {"content": "ok"})

    assert LLMClientManager.get_usage_stats()["OC_DS"] == {
        "total_calls": 1,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }


def test_record_usage_from_result_coerces_numeric_shapes() -> None:
    LLMClientManager._record_usage_from_result(
        "OC_DS",
        {"usage": {"prompt_tokens": True, "completion_tokens": 2.9}},
    )

    assert LLMClientManager.get_usage_stats()["OC_DS"] == {
        "total_calls": 1,
        "prompt_tokens": 1,
        "completion_tokens": 2,
        "total_tokens": 3,
    }
