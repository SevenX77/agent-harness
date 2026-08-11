"""Gateway ChatX invocation runtime contract tests."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any

import httpx
import openai
import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from stream_fakes import as_one_piece


def _route(
    *,
    endpoint_id: str = "qiniu-anthropic",
    route_slug: str = "claude-sonnet-4-6",
    protocol: str = "anthropic_compatible",
    provider_model_id: str = "claude-sonnet-4-6",
):
    from graph_agent_gateway.registry import ResolvedRoute

    return ResolvedRoute(
        role_name="graph_agent",
        route_id=f"{endpoint_id}:{route_slug}",
        endpoint_id=endpoint_id,
        protocol=protocol,  # type: ignore[arg-type]
        base_url="https://llm.wavespeed.ai",
        credential_ref=f"endpoint:{endpoint_id}",
        credential_fingerprint="fingerprint-a",
        provider_model_id=provider_model_id,
        canonical_id=provider_model_id,
    )


def _role(routes: Sequence[Any], *, token_escalation_rounds: int = 0):
    from graph_agent_gateway.registry import ResolvedRole, RuntimePolicy

    return ResolvedRole(
        role_name="graph_agent",
        system_prompt_prefix="Always keep tool-call context.",
        runtime_policy=RuntimePolicy(token_escalation_rounds=token_escalation_rounds),
        routes=list(routes),
    )


class RecordingManager:
    def __init__(self) -> None:
        self.marked_down: list[str] = []
        self.usage_records: list[tuple[str, int, int]] = []

    def is_provider_marked_down(self, route: Any, runtime_policy: Any) -> bool:
        return False


    def mark_provider_down(self, route: Any, exc: BaseException, runtime_policy: Any) -> None:
        self.marked_down.append(route.route_id)

    def usage_total_calls(self, route: Any) -> int:
        return 0

    def record_usage(
        self,
        provider_code: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        self.usage_records.append((provider_code, prompt_tokens, completion_tokens))


class FakeChatModel:
    def __init__(self, responses: list[AIMessage | BaseException]) -> None:
        self.responses = responses
        self.invocations: list[list[BaseMessage]] = []

    def stream(self, messages: list[BaseMessage], **kwargs: Any) -> Iterator[AIMessageChunk]:
        del kwargs
        self.invocations.append(list(messages))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        yield from as_one_piece(response)


class FakeFactory:
    def __init__(self, chat_model: FakeChatModel) -> None:
        self.chat_model = chat_model
        self.build_calls: list[dict[str, object]] = []

    def build(self, route: Any, **kwargs: object) -> FakeChatModel:
        self.build_calls.append({"route_id": route.route_id, **kwargs})
        return self.chat_model


def test_gateway_invokes_chatx_with_raw_base_messages_for_empty_content_tool_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from graph_agent_gateway.call import GatewayChatModel
    from graph_agent_gateway.call import chat_model as gateway_chat_model

    chat_model = FakeChatModel(
        [
            AIMessage(
                content="chatx-ok",
                usage_metadata={"input_tokens": 5, "output_tokens": 7, "total_tokens": 12},
                response_metadata={"finish_reason": "stop", "provider_meta": "kept"},
            )
        ]
    )
    fake_factory = FakeFactory(chat_model)
    monkeypatch.setattr(
        gateway_chat_model,
        "RouteChatModelFactory",
        lambda **_kwargs: fake_factory,
        raising=False,
    )
    manager = RecordingManager()
    model = GatewayChatModel(
        "graph_agent",
        _role([_route()]),
        max_tokens=512,
        client_manager=manager,
        probe_before_call=False,
    )
    messages = [
        HumanMessage(content="First question"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "lookup_weather",
                    "args": {"city": "Shenzhen"},
                    "id": "call_1",
                }
            ],
        ),
        ToolMessage(content="sunny", tool_call_id="call_1"),
        HumanMessage(content="Continue"),
    ]

    result = model.invoke(messages)

    assert result.content == "chatx-ok"
    assert manager.usage_records == [("qiniu-anthropic", 5, 7)]
    assert chat_model.invocations
    recorded_messages = chat_model.invocations[0]
    assert isinstance(recorded_messages[0], SystemMessage)
    assert recorded_messages[0].content == "Always keep tool-call context."
    assert isinstance(recorded_messages[2], AIMessage)
    assert recorded_messages[2].content == ""
    assert recorded_messages[2].tool_calls[0]["args"] == {"city": "Shenzhen"}
    assert isinstance(recorded_messages[3], ToolMessage)
    assert recorded_messages[3].tool_call_id == "call_1"


def test_build_chat_result_preserves_ai_message_blocks_and_provider_metadata() -> None:
    from graph_agent_gateway.call import GatewayChatModel

    route = _route()
    model = GatewayChatModel(
        "graph_agent",
        _role([route]),
        client_manager=RecordingManager(),
        probe_before_call=False,
    )
    message = AIMessage(
        content=[
            {"type": "reasoning", "text": "because"},
            {"type": "text", "text": "answer"},
        ],
        usage_metadata={"input_tokens": 3, "output_tokens": 4, "total_tokens": 7},
        response_metadata={"finish_reason": "stop", "provider_meta": "kept"},
    )

    result = model._build_chat_result(message, route)  # type: ignore[arg-type]

    bridged = result.generations[0].message
    assert bridged.content == message.content
    assert bridged.response_metadata["provider_meta"] == "kept"
    assert bridged.response_metadata["route_id"] == route.route_id
    assert result.llm_output["token_usage"] == {
        "prompt_tokens": 3,
        "completion_tokens": 4,
        "total_tokens": 7,
    }


def test_truncated_chatx_response_rebuilds_with_doubled_token_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from graph_agent_gateway.call import GatewayChatModel
    from graph_agent_gateway.call import chat_model as gateway_chat_model

    chat_model = FakeChatModel(
        [
            AIMessage(
                content="partial",
                usage_metadata={"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
                response_metadata={"finish_reason": "length"},
            ),
            AIMessage(
                content="complete",
                usage_metadata={"input_tokens": 1, "output_tokens": 4, "total_tokens": 5},
                response_metadata={"finish_reason": "stop"},
            ),
        ]
    )
    fake_factory = FakeFactory(chat_model)
    monkeypatch.setattr(
        gateway_chat_model,
        "RouteChatModelFactory",
        lambda **_kwargs: fake_factory,
        raising=False,
    )
    route = _route()
    model = GatewayChatModel(
        "graph_agent",
        _role([route], token_escalation_rounds=1),
        max_tokens=2,
        client_manager=RecordingManager(),
        probe_before_call=False,
    )

    result = model.invoke([HumanMessage(content="hello")])

    assert result.content == "complete"
    assert [call["max_tokens"] for call in fake_factory.build_calls] == [2, 4]


class FakeResponse:
    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self._message = message

    def json(self) -> dict[str, object]:
        return {"error": {"message": self._message, "type": "provider_error"}}


class ProviderHTTPError(RuntimeError):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.response = FakeResponse(status_code, message)


class RouteAwareFactory:
    def __init__(self, behaviors: dict[str, AIMessage | BaseException]) -> None:
        self.behaviors = behaviors
        self.invoked_routes: list[str] = []

    def build(self, route: Any, **kwargs: object):
        factory = self

        class RouteAwareChatModel:
            def stream(
                self, messages: list[BaseMessage], **kwargs: Any
            ) -> Iterator[AIMessageChunk]:
                del messages, kwargs
                factory.invoked_routes.append(route.route_id)
                behavior = factory.behaviors[route.route_id]
                if isinstance(behavior, BaseException):
                    raise behavior
                yield from as_one_piece(behavior)

        return RouteAwareChatModel()


def _gateway_with_factory(
    monkeypatch: pytest.MonkeyPatch,
    factory: RouteAwareFactory,
    routes: list[Any],
):
    from graph_agent_gateway.call import GatewayChatModel
    from graph_agent_gateway.call import chat_model as gateway_chat_model

    monkeypatch.setattr(
        gateway_chat_model,
        "RouteChatModelFactory",
        lambda **_kwargs: factory,
        raising=False,
    )
    return GatewayChatModel(
        "graph_agent",
        _role(routes),
        client_manager=RecordingManager(),
        probe_before_call=False,
    )


@pytest.mark.parametrize(
    ("exception", "expected_invocation_pattern"),
    [
        (ProviderHTTPError(401, "bad key after chatx retries"), ("primary", "fallback")),
        (httpx.ConnectError("connection failed after chatx retries"), ("primary", "primary", "fallback")),
    ],
)
def test_chatx_retry_exhaustion_fallback_shapes_remain_fallback_allowed(
    monkeypatch: pytest.MonkeyPatch,
    exception: BaseException,
    expected_invocation_pattern: tuple[str, ...],
) -> None:
    bad_route = _route(endpoint_id="primary", route_slug="bad")
    fallback_route = _route(endpoint_id="fallback", route_slug="ok")
    factory = RouteAwareFactory(
        {
            bad_route.route_id: exception,
            fallback_route.route_id: AIMessage(
                content="fallback-ok",
                usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
                response_metadata={"finish_reason": "stop"},
            ),
        }
    )
    model = _gateway_with_factory(monkeypatch, factory, [bad_route, fallback_route])

    result = model.invoke([HumanMessage(content="hello")])

    assert result.content == "fallback-ok"
    expected_routes = [
        bad_route.route_id if provider == "primary" else fallback_route.route_id
        for provider in expected_invocation_pattern
    ]
    assert factory.invoked_routes == expected_routes


def test_gateway_chat_model_retries_same_route_before_switching_on_retryable_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary_route = _route(endpoint_id="primary", route_slug="bad")
    fallback_route = _route(endpoint_id="fallback", route_slug="ok")

    class RetrySameFactory:
        def __init__(self) -> None:
            self.invoked_routes: list[str] = []
            self.route_attempts: dict[str, int] = {}

        def build(self, route: Any, **kwargs: object):
            factory = self

            class RouteAwareChatModel:
                def stream(
                    self, messages: list[BaseMessage], **kwargs: Any
                ) -> Iterator[AIMessageChunk]:
                    del messages, kwargs
                    factory.invoked_routes.append(route.route_id)
                    attempt = factory.route_attempts.get(route.route_id, 0)
                    factory.route_attempts[route.route_id] = attempt + 1
                    if route.route_id == primary_route.route_id and attempt == 0:
                        raise ProviderHTTPError(503, "transient upstream overload")
                    if route.route_id == primary_route.route_id:
                        yield from as_one_piece(AIMessage(content="primary-recovered"))
                        return
                    yield from as_one_piece(AIMessage(content="fallback-used"))

            return RouteAwareChatModel()

    factory = RetrySameFactory()
    model = _gateway_with_factory(monkeypatch, factory, [primary_route, fallback_route])

    result = model.invoke([HumanMessage(content="hello")])

    assert result.content == "primary-recovered"
    assert factory.invoked_routes == [primary_route.route_id, primary_route.route_id]


def test_chatx_retry_exhaustion_400_non_capability_shape_remains_fail_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from graph_agent_gateway.errors import AllProvidersFailedError

    bad_route = _route(endpoint_id="primary", route_slug="bad")
    fallback_route = _route(endpoint_id="fallback", route_slug="ok")
    factory = RouteAwareFactory(
        {
            bad_route.route_id: ProviderHTTPError(400, "malformed request body"),
            fallback_route.route_id: AIMessage(content="must-not-run"),
        }
    )
    model = _gateway_with_factory(monkeypatch, factory, [bad_route, fallback_route])

    with pytest.raises(AllProvidersFailedError) as exc_info:
        model.invoke([HumanMessage(content="hello")])

    # Asked twice, on the same route: a refused request is the one failure the
    # runtime settings can cause, so the second ask drops them to find out. The
    # rule under test is that this refusal never reaches the next route.
    assert factory.invoked_routes == [bad_route.route_id, bad_route.route_id]
    assert exc_info.value.context["last_error_chain"][0]["fallback_decision"] == "fail_fast"
    assert exc_info.value.context["last_error_chain"][0]["provider_status_code"] == 400


def _openai_status_error(error_cls: type[Exception], status_code: int, message: str) -> Exception:
    response = httpx.Response(
        status_code,
        request=httpx.Request("POST", "https://api.openai.example/v1/chat/completions"),
        json={"error": {"message": message, "type": "provider_error"}},
    )
    return error_cls(message, response=response, body=response.json())


def test_real_openai_authentication_error_shape_remains_fallback_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad_route = _route(endpoint_id="primary", route_slug="bad", protocol="openai_compatible")
    fallback_route = _route(endpoint_id="fallback", route_slug="ok", protocol="openai_compatible")
    factory = RouteAwareFactory(
        {
            bad_route.route_id: _openai_status_error(
                openai.AuthenticationError,
                401,
                "invalid api key",
            ),
            fallback_route.route_id: AIMessage(
                content="fallback-ok",
                usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
                response_metadata={"finish_reason": "stop"},
            ),
        }
    )
    model = _gateway_with_factory(monkeypatch, factory, [bad_route, fallback_route])

    result = model.invoke([HumanMessage(content="hello")])

    assert result.content == "fallback-ok"
    assert factory.invoked_routes == [bad_route.route_id, fallback_route.route_id]


def test_real_openai_bad_request_error_shape_remains_fail_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from graph_agent_gateway.errors import AllProvidersFailedError

    bad_route = _route(endpoint_id="primary", route_slug="bad", protocol="openai_compatible")
    fallback_route = _route(endpoint_id="fallback", route_slug="ok", protocol="openai_compatible")
    factory = RouteAwareFactory(
        {
            bad_route.route_id: _openai_status_error(
                openai.BadRequestError,
                400,
                "malformed request body",
            ),
            fallback_route.route_id: AIMessage(content="must-not-run"),
        }
    )
    model = _gateway_with_factory(monkeypatch, factory, [bad_route, fallback_route])

    with pytest.raises(AllProvidersFailedError) as exc_info:
        model.invoke([HumanMessage(content="hello")])

    # Asked twice, on the same route: a refused request is the one failure the
    # runtime settings can cause, so the second ask drops them to find out. The
    # rule under test is that this refusal never reaches the next route.
    assert factory.invoked_routes == [bad_route.route_id, bad_route.route_id]
    assert exc_info.value.context["last_error_chain"][0]["fallback_decision"] == "fail_fast"
    assert exc_info.value.context["last_error_chain"][0]["provider_status_code"] == 400


def test_predict_gateway_model_stays_self_contained_and_skips_chatx_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from graph_agent_gateway.call import PredictGatewayChatModel
    from graph_agent_gateway.call import chat_model as gateway_chat_model

    class PredictContext:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def resolve_generation(
            self,
            *,
            phase_name: str,
            role_name: str,
            messages: list[BaseMessage],
        ) -> tuple[dict[str, object], str]:
            self.calls.append(
                {
                    "phase_name": phase_name,
                    "role_name": role_name,
                    "messages": messages,
                }
            )
            return {"answer": "predict-ok"}, "predict-fixture"

    def fail_if_chatx_factory_is_used(**_kwargs: object) -> object:
        raise AssertionError("PredictGatewayChatModel must not construct ChatX models")

    monkeypatch.setattr(
        gateway_chat_model,
        "RouteChatModelFactory",
        fail_if_chatx_factory_is_used,
        raising=False,
    )
    context = PredictContext()
    model = PredictGatewayChatModel(
        "graph_agent",
        _role([_route()]),
        predict_context=context,  # type: ignore[arg-type]
        phase_name="draft",
    )

    result = model.invoke([HumanMessage(content="hello")])

    assert result.__class__.__name__ == "AIMessage"
    assert result.content == '{"answer":"predict-ok"}'
    assert result.response_metadata["mocked_source"] == "predict-fixture"
    assert result.response_metadata["provider"] == "predict"
    assert result.response_metadata["model_name"] == "graph_agent"
    assert context.calls[0]["phase_name"] == "draft"
    assert context.calls[0]["role_name"] == "graph_agent"
