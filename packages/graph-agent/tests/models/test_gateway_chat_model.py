from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
from graph_agent_gateway.exceptions import AllProvidersFailedError
from graph_agent_gateway.gateway_chat_model import GatewayChatModel, _langchain_messages_to_dict
from graph_agent_gateway.llm_config import ModelDef, ProviderDef, ResolvedProvider, ResolvedRole
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import Runnable

from graph_agent.callbacks.base import Callback
from graph_agent.callbacks.events import CallbackEvent, LLMFallbackEvent
from graph_agent.models.llm_client_manager import LLMClientManager


class RecordingCallback(Callback):
    def __init__(self) -> None:
        self.events: list[CallbackEvent] = []

    def on_event(self, event: CallbackEvent) -> None:
        self.events.append(event)


class RaisingCallback(Callback):
    def on_event(self, event: CallbackEvent) -> None:
        raise RuntimeError(f"callback rejected {event.event_type}")


def _provider(
    provider_code: str,
    provider_type: str = "openai_compatible",
) -> ProviderDef:
    return ProviderDef(
        code=provider_code,
        name=f"Provider {provider_code}",
        type=provider_type,
        api_key_env="TEST_API_KEY",
        base_url="https://provider.example/v1",
        timeout=12,
    )


def _model(
    provider_code: str,
    model_name: str,
    *,
    reasoning: bool = False,
) -> ModelDef:
    return ModelDef(
        code=f"M_{provider_code}",
        name=f"Model {provider_code}",
        reasoning=reasoning,
        min_max_tokens=64,
        providers={provider_code: model_name},
    )


def _rp(
    provider_code: str,
    model_name: str,
    *,
    provider_type: str = "openai_compatible",
    reasoning: bool = False,
) -> ResolvedProvider:
    return ResolvedProvider(
        provider_code=provider_code,
        provider_def=_provider(provider_code, provider_type),
        model_name=model_name,
        model_def=_model(provider_code, model_name, reasoning=reasoning),
    )


def _role(*providers: ResolvedProvider) -> ResolvedRole:
    return ResolvedRole(
        role_name="writer",
        temperature=0.3,
        system_prompt_prefix="",
        active_model_code="M_P1",
        model_fallback=True,
        call_chain=list(providers),
    )


def _model_instance(
    *providers: ResolvedProvider,
    callbacks: list[Callback] | None = None,
    probe_before_call: bool = True,
) -> GatewayChatModel:
    return GatewayChatModel(
        "writer",
        _role(*providers),
        max_tokens=128,
        temperature=0.2,
        callbacks=callbacks or [],
        phase_name="draft",
        probe_before_call=probe_before_call,
    )


def _response(
    content: str = "ok",
    *,
    prompt_tokens: int = 11,
    completion_tokens: int = 4,
    finish_reason: str | None = "stop",
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "content": content,
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
        "finish_reason": finish_reason,
    }
    if extra:
        payload.update(extra)
    return payload


@pytest.fixture(autouse=True)
def _clean_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    LLMClientManager._clients.clear()
    LLMClientManager._usage_stats.clear()
    LLMClientManager._provider_down_cache.clear()
    monkeypatch.setenv("TEST_API_KEY", "secret")


def test_generate_success_first_provider_returns_chat_result() -> None:
    rp = _rp("P1", "model-a")
    model = _model_instance(rp)

    with (
        patch.object(LLMClientManager, "_probe_provider", return_value=True) as probe,
        patch.object(
            LLMClientManager, "_dispatch_provider_call", return_value=_response("hello")
        ) as dispatch,
    ):
        result = model._generate([HumanMessage(content="hi")])

    assert result.generations[0].message.content == "hello"
    assert result.llm_output == {
        "token_usage": {"prompt_tokens": 11, "completion_tokens": 4, "total_tokens": 15},
        "model_name": "model-a",
        "provider": "P1",
    }
    probe.assert_called_once_with(rp)
    dispatch.assert_called_once()


def test_generate_skip_marked_down_provider_uses_next_candidate() -> None:
    first = _rp("P1", "model-a")
    second = _rp("P2", "model-b")
    model = _model_instance(first, second)
    LLMClientManager._mark_provider_down("P1", "model-a")

    with (
        patch.object(LLMClientManager, "_probe_provider", return_value=True) as probe,
        patch.object(
            LLMClientManager, "_dispatch_provider_call", return_value=_response("second")
        ) as dispatch,
    ):
        result = model._generate([HumanMessage(content="hi")])

    assert result.generations[0].message.content == "second"
    probe.assert_called_once_with(second)
    assert dispatch.call_args.args[0] is second


def test_generate_probe_fail_marks_down_and_tries_next_without_event() -> None:
    first = _rp("P1", "model-a")
    second = _rp("P2", "model-b")
    callback = RecordingCallback()
    model = _model_instance(first, second, callbacks=[callback])

    with (
        patch.object(LLMClientManager, "_probe_provider", side_effect=[False, True]),
        patch.object(LLMClientManager, "_dispatch_provider_call", return_value=_response("second")),
    ):
        result = model._generate([HumanMessage(content="hi")])

    assert result.generations[0].message.content == "second"
    assert LLMClientManager._is_provider_marked_down("P1", "model-a")
    assert callback.events == []


def test_generate_dispatch_fail_marks_down_and_emits_fallback_event() -> None:
    first = _rp("P1", "model-a")
    second = _rp("P2", "model-b")
    callback = RecordingCallback()
    model = _model_instance(first, second, callbacks=[callback])

    with (
        patch.object(LLMClientManager, "_probe_provider", return_value=True),
        patch.object(
            LLMClientManager,
            "_dispatch_provider_call",
            side_effect=[httpx.ConnectError("dns failed"), _response("second")],
        ),
    ):
        result = model._generate([HumanMessage(content="hi")])

    assert result.generations[0].message.content == "second"
    assert LLMClientManager._is_provider_marked_down("P1", "model-a")
    assert len(callback.events) == 1
    event = callback.events[0]
    assert isinstance(event, LLMFallbackEvent)
    assert event.phase_name == "draft"
    assert event.from_provider == "P1/model-a"
    assert event.to_provider == "P2/model-b"
    assert "ConnectError" in event.reason


def test_generate_all_providers_fail_raises_runtime_error() -> None:
    first = _rp("P1", "model-a")
    second = _rp("P2", "model-b")
    model = _model_instance(first, second)

    with (
        patch.object(LLMClientManager, "_probe_provider", return_value=True),
        patch.object(LLMClientManager, "_dispatch_provider_call", side_effect=RuntimeError("502")),
        pytest.raises(AllProvidersFailedError),
    ):
        model._generate([HumanMessage(content="hi")])

    assert LLMClientManager._is_provider_marked_down("P1", "model-a")
    assert LLMClientManager._is_provider_marked_down("P2", "model-b")


def test_emit_fallback_event_only_after_confirmed_dispatch_failure() -> None:
    first = _rp("P1", "model-a")
    second = _rp("P2", "model-b")
    callback = RecordingCallback()
    model = _model_instance(first, second, callbacks=[callback])

    with (
        patch.object(LLMClientManager, "_probe_provider", side_effect=[False, True]),
        patch.object(LLMClientManager, "_dispatch_provider_call", return_value=_response("ok")),
    ):
        model._generate([HumanMessage(content="hi")])

    assert callback.events == []


def test_generate_all_marked_down_raises_without_fallback_event() -> None:
    first = _rp("P1", "model-a")
    callback = RecordingCallback()
    model = _model_instance(first, callbacks=[callback])
    LLMClientManager._mark_provider_down("P1", "model-a")

    with pytest.raises(AllProvidersFailedError):
        model._generate([HumanMessage(content="hi")])

    assert callback.events == []


def test_generate_non_failover_exception_propagates_without_mark_down() -> None:
    rp = _rp("P1", "model-a")
    model = _model_instance(rp)

    with (
        patch.object(LLMClientManager, "_probe_provider", return_value=True),
        patch.object(
            LLMClientManager, "_dispatch_provider_call", side_effect=ValueError("bad test")
        ),
        pytest.raises(AllProvidersFailedError),
    ):
        model._generate([HumanMessage(content="hi")])

    assert LLMClientManager._is_provider_marked_down("P1", "model-a")


def test_generate_callback_failure_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    first = _rp("P1", "model-a")
    second = _rp("P2", "model-b")
    model = _model_instance(first, second, callbacks=[RaisingCallback()])

    with (
        patch.object(LLMClientManager, "_probe_provider", return_value=True),
        patch.object(
            LLMClientManager,
            "_dispatch_provider_call",
            side_effect=[RuntimeError("upstream down"), _response("second")],
        ),
        caplog.at_level("ERROR"),
    ):
        model._generate([HumanMessage(content="hi")])

    assert "action=callback_failed" in caplog.text


def test_probe_can_be_disabled_for_unit_or_future_policy() -> None:
    rp = _rp("P1", "model-a")
    model = _model_instance(rp, probe_before_call=False)

    with (
        patch.object(LLMClientManager, "_probe_provider") as probe,
        patch.object(LLMClientManager, "_dispatch_provider_call", return_value=_response("ok")),
    ):
        model._generate([HumanMessage(content="hi")])

    probe.assert_not_called()


def test_generate_passes_runtime_kwargs_and_reasoning_flag() -> None:
    rp = _rp("P1", "model-a", reasoning=True)
    model = _model_instance(rp)

    with (
        patch.object(LLMClientManager, "_probe_provider", return_value=True),
        patch.object(
            LLMClientManager, "_dispatch_provider_call", return_value=_response("ok")
        ) as dispatch,
    ):
        model._generate(
            [HumanMessage(content="hi")],
            max_tokens="33",
            temperature="0.15",
            reasoning=True,
        )

    assert dispatch.call_args.args[2] == 33
    assert dispatch.call_args.args[3] == 0.15
    assert dispatch.call_args.kwargs["reasoning"] is True
    assert dispatch.call_args.kwargs["tools"] is None
    assert dispatch.call_args.kwargs["tool_choice"] is None


def test_generate_invalid_runtime_kwargs_fall_back_to_defaults() -> None:
    rp = _rp("P1", "model-a")
    model = _model_instance(rp)

    with (
        patch.object(LLMClientManager, "_probe_provider", return_value=True),
        patch.object(
            LLMClientManager, "_dispatch_provider_call", return_value=_response("ok")
        ) as dispatch,
    ):
        model._generate(
            [HumanMessage(content="hi")],
            max_tokens="bad",
            temperature=True,
            reasoning="yes",
        )

    assert dispatch.call_args.args[2] == 128
    assert dispatch.call_args.args[3] == 0.2
    assert dispatch.call_args.kwargs["reasoning"] is False


def test_generate_numeric_temperature_kwarg_is_forwarded() -> None:
    rp = _rp("P1", "model-a")
    model = _model_instance(rp)

    with (
        patch.object(LLMClientManager, "_probe_provider", return_value=True),
        patch.object(
            LLMClientManager, "_dispatch_provider_call", return_value=_response("ok")
        ) as dispatch,
    ):
        model._generate([HumanMessage(content="hi")], temperature=1)

    assert dispatch.call_args.args[3] == 1.0


def test_record_usage_called_on_success_when_dispatch_is_mocked() -> None:
    rp = _rp("P1", "model-a")
    model = _model_instance(rp)

    with (
        patch.object(LLMClientManager, "_probe_provider", return_value=True),
        patch.object(LLMClientManager, "_dispatch_provider_call", return_value=_response("ok")),
    ):
        model._generate([HumanMessage(content="hi")])

    assert LLMClientManager.get_usage_stats()["P1"] == {
        "total_calls": 1,
        "prompt_tokens": 11,
        "completion_tokens": 4,
        "total_tokens": 15,
    }


def test_success_does_not_double_count_when_manager_already_recorded_usage() -> None:
    rp = _rp("P1", "model-a")
    model = _model_instance(rp)

    def _dispatch(*args: object, **kwargs: object) -> dict[str, object]:
        LLMClientManager.record_usage("P1", 11, 4)
        return _response("ok")

    with (
        patch.object(LLMClientManager, "_probe_provider", return_value=True),
        patch.object(LLMClientManager, "_dispatch_provider_call", side_effect=_dispatch),
    ):
        model._generate([HumanMessage(content="hi")])

    assert LLMClientManager.get_usage_stats()["P1"]["total_calls"] == 1


def test_chat_result_message_content_and_metadata_are_correct() -> None:
    rp = _rp("P1", "model-a")
    model = _model_instance(rp)
    response = _response(
        "final",
        finish_reason=None,
        extra={"additional_kwargs": {"custom": "value"}, "reasoning_content": "thoughts"},
    )

    result = model._build_chat_result(response, rp)

    message = result.generations[0].message
    assert message.content == "final"
    assert message.additional_kwargs["custom"] == "value"
    assert message.additional_kwargs["reasoning_content"] == "thoughts"
    assert message.response_metadata["provider"] == "P1"
    assert result.generations[0].generation_info is not None
    assert result.generations[0].generation_info["finish_reason"] is None


def test_chat_result_handles_missing_usage_and_non_string_content() -> None:
    rp = _rp("P1", "model-a")
    model = _model_instance(rp)

    result = model._build_chat_result({"content": ["part"], "finish_reason": "stop"}, rp)

    assert result.generations[0].message.content == "['part']"
    assert result.llm_output is not None
    assert result.llm_output["token_usage"] == {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }


def test_chat_result_normalizes_odd_usage_values() -> None:
    rp = _rp("P1", "model-a")
    model = _model_instance(rp)

    result = model._build_chat_result(
        {
            "content": None,
            "usage": {
                "prompt_tokens": True,
                "completion_tokens": 2.8,
                "total_tokens": "bad",
            },
        },
        rp,
    )

    assert result.generations[0].message.content == ""
    assert result.llm_output is not None
    assert result.llm_output["token_usage"] == {
        "prompt_tokens": 1,
        "completion_tokens": 2,
        "total_tokens": 3,
    }


def test_bind_tools_returns_runnable_with_tools() -> None:
    rp = _rp("P1", "model-a")
    model = _model_instance(rp)

    bound = model.bind_tools([{"name": "finish_task"}], tool_choice="finish_task", strict=True)

    assert isinstance(bound, Runnable)
    assert isinstance(bound, GatewayChatModel)
    assert bound.bound_tools == (
        {
            "type": "function",
            "function": {
                "name": "finish_task",
                "description": "",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    )
    assert bound.tool_choice == "finish_task"
    assert bound.tool_kwargs == {"strict": True}


def test_bind_tools_invoke_with_tool_calls() -> None:
    rp = _rp("P1", "model-a")
    model = _model_instance(rp)
    tool_calls = [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "finish_task", "arguments": "{}"},
        }
    ]

    with (
        patch.object(LLMClientManager, "_probe_provider", return_value=True),
        patch.object(
            LLMClientManager,
            "_dispatch_provider_call",
            return_value=_response(
                "", finish_reason="tool_calls", extra={"tool_calls": tool_calls}
            ),
        ),
    ):
        message = model.bind_tools([{"name": "finish_task"}]).invoke("finish")

    assert isinstance(message, AIMessage)
    assert message.additional_kwargs["tool_calls"] == tool_calls
    assert message.response_metadata["finish_reason"] == "tool_calls"


def test_bind_tools_forwards_tool_payload_to_dispatch() -> None:
    rp = _rp("P1", "model-a")
    model = _model_instance(rp)

    with (
        patch.object(LLMClientManager, "_probe_provider", return_value=True),
        patch.object(
            LLMClientManager, "_dispatch_provider_call", return_value=_response("ok")
        ) as dispatch,
    ):
        model.bind_tools([{"name": "finish_task"}], tool_choice="finish_task").invoke("finish")

    assert dispatch.call_args.kwargs["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "finish_task",
                "description": "",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]
    assert dispatch.call_args.kwargs["tool_choice"] == "finish_task"


def test_langchain_message_conversion_preserves_roles_and_tool_fields() -> None:
    ai_message = AIMessage(
        content="assistant",
        additional_kwargs={"reasoning_content": "why"},
        tool_calls=[{"name": "finish_task", "args": {}, "id": "call_1", "type": "tool_call"}],
    )

    converted = _langchain_messages_to_dict(
        [
            SystemMessage(content="rules"),
            HumanMessage(content="hello", name="user_name"),
            ai_message,
            ToolMessage(content="tool result", tool_call_id="call_1"),
        ]
    )

    assert converted[0] == {"role": "system", "content": "rules"}
    assert converted[1] == {"role": "user", "content": "hello", "name": "user_name"}
    assert converted[2]["role"] == "assistant"
    assert converted[2]["tool_calls"] == [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "finish_task", "arguments": "{}"},
        }
    ]
    assert converted[2]["reasoning_content"] == "why"
    assert converted[3] == {"role": "tool", "content": "tool result", "tool_call_id": "call_1"}


def test_message_conversion_preserves_raw_tool_calls_and_unknown_roles() -> None:
    raw_tool_calls = [{"id": "raw"}]
    converted = _langchain_messages_to_dict(
        [
            HumanMessage(content="hello", additional_kwargs={"tool_calls": raw_tool_calls}),
            BaseMessage(content="", type="custom"),
        ]
    )

    assert converted[0]["tool_calls"] == raw_tool_calls
    assert converted[1] == {"role": "user", "content": ""}


def test_generate_converts_messages_before_dispatch() -> None:
    rp = _rp("P1", "model-a")
    model = _model_instance(rp)

    with (
        patch.object(LLMClientManager, "_probe_provider", return_value=True),
        patch.object(
            LLMClientManager, "_dispatch_provider_call", return_value=_response("ok")
        ) as dispatch,
    ):
        model._generate([SystemMessage(content="rules"), HumanMessage(content=["hello"])])

    assert dispatch.call_args.args[1] == [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": ["hello"]},
    ]


def test_model_identity_params_and_llm_type() -> None:
    first = _rp("P1", "model-a")
    second = _rp("P2", "model-b")
    model = _model_instance(first, second)

    assert model._llm_type == "graph_agent_gateway"
    assert model._identifying_params == {
        "role_name": "writer",
        "active_model_code": "M_P1",
        "candidates": ["P1/model-a", "P2/model-b"],
    }


def test_empty_call_chain_raises_clear_error() -> None:
    model = GatewayChatModel("writer", _role(), phase_name="draft")

    with pytest.raises(AllProvidersFailedError):
        model._generate([HumanMessage(content="hi")])
