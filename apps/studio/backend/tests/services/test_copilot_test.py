from __future__ import annotations

import json

import httpx
import pytest
from app.services import copilot_test
from app.services.copilot_test import (
    PingResult,
    _extract_vendor_error_code,
    _join_base_url_and_endpoint,
)


def _response(payload: object) -> httpx.Response:
    return httpx.Response(200, json=payload)


def test_extract_vendor_error_code_prefers_specific_openai_code() -> None:
    response = httpx.Response(
        401,
        json={
            "error": {
                "type": "invalid_request_error",
                "code": "invalid_api_key",
                "message": "Incorrect API key provided.",
            }
        },
    )

    assert _extract_vendor_error_code(response, default="unauthorized") == "invalid_api_key"


def test_ping_result_retains_first_model_seen_for_compatibility() -> None:
    result = PingResult(latency_ms=12, model_ids=("gpt-5", "gpt-5-mini"))

    assert result.model_seen == "gpt-5"


def test_model_ids_collects_openai_style_data_ids_in_order() -> None:
    response = _response(
        {
            "data": [
                {"id": "gpt-5"},
                {"id": "gpt-5-mini"},
                {"id": "gpt-5"},
                {"id": ""},
                {"not_id": "ignored"},
            ]
        }
    )

    model_ids = getattr(copilot_test, "_model_ids", lambda _response: ())
    assert model_ids(response) == ("gpt-5", "gpt-5-mini")


def test_model_ids_collects_gemini_model_names_without_prefix() -> None:
    response = _response(
        {
            "models": [
                {"name": "models/gemini-2.5-pro"},
                {"name": "gemini-2.5-flash"},
                {"name": 123},
            ]
        }
    )

    model_ids = getattr(copilot_test, "_model_ids", lambda _response: ())
    assert model_ids(response) == ("gemini-2.5-pro", "gemini-2.5-flash")


def test_join_base_url_and_endpoint_deduplicates_protocol_prefixes() -> None:
    assert (
        _join_base_url_and_endpoint("https://api.qnaigc.com/v1", "/v1/models")
        == "https://api.qnaigc.com/v1/models"
    )
    assert (
        _join_base_url_and_endpoint(
            "https://ark.cn-beijing.volces.com/api/v3",
            "/api/v3/models",
        )
        == "https://ark.cn-beijing.volces.com/api/v3/models"
    )


@pytest.mark.anyio
async def test_request_models_uses_protocol_specific_model_list_url() -> None:
    requested: list[tuple[str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append((str(request.url), request.headers.get("authorization")))
        return httpx.Response(200, json={"data": [{"id": "ep-test"}]}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await copilot_test._request_models(
            client,
            "ark",
            "secret",
            "https://ark.cn-beijing.volces.com/api/v3",
        )
        await copilot_test._request_models(
            client,
            "claude",
            "secret",
            "https://anthropic.qnaigc.com",
        )

    assert requested == [
        ("https://ark.cn-beijing.volces.com/api/v3/models", "Bearer secret"),
        ("https://anthropic.qnaigc.com/v1/models", None),
    ]


@pytest.mark.anyio
async def test_request_model_generation_uses_ark_responses_api() -> None:
    requested: list[tuple[str, dict[str, object]]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested.append((str(request.url), dict(request.headers)))
        return httpx.Response(200, json={"id": "response-id"}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await copilot_test._request_model_generation(
            client,
            "ark",
            "secret",
            "https://ark.cn-beijing.volces.com/api/v3",
            "ep-20260316142940-b74bm",
        )

    assert requested[0][0] == "https://ark.cn-beijing.volces.com/api/v3/responses"
    assert requested[0][1]["authorization"] == "Bearer secret"


@pytest.mark.anyio
async def test_request_model_generation_uses_runtime_settings_for_openai_probe() -> None:
    bodies: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content.decode()))
        return httpx.Response(200, json={"id": "chatcmpl-id"}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await copilot_test._request_model_generation(
            client,
            "openai",
            "secret",
            "https://api.openai.example/v1",
            "gpt-5",
            runtime_settings={
                "max_output_tokens": 333,
                "reasoning": {"effort": "medium"},
            },
        )

    assert bodies == [
        {
            "model": "gpt-5",
            "messages": [{"role": "user", "content": "."}],
            "max_completion_tokens": 333,
            "reasoning_effort": "medium",
        }
    ]


@pytest.mark.anyio
async def test_request_official_call_method_generation_uses_method_specific_payloads() -> None:
    requests: list[tuple[str, dict[str, object]]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append((str(request.url), json.loads(request.content.decode())))
        return httpx.Response(200, json={"id": "ok"}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await copilot_test._request_official_call_method_generation(
            client,
            "openai_responses",
            "secret",
            "https://api.openai.example/v1",
            "gpt-5.2",
            runtime_settings={"max_output_tokens": 16, "reasoning": {"enabled": True, "effort": "low"}},
        )
        await copilot_test._request_official_call_method_generation(
            client,
            "ark_chat",
            "secret",
            "https://ark.cn-beijing.volces.com/api/v3",
            "doubao-1-5-pro-32k-250115",
            runtime_settings={"reasoning": {"enabled": False}},
        )
        await copilot_test._request_official_call_method_generation(
            client,
            "deepseek_anthropic_messages",
            "secret",
            "https://api.deepseek.com",
            "deepseek-v4-pro",
            runtime_settings={"max_output_tokens": 1025, "reasoning": {"enabled": True, "budget_tokens": 1024}},
        )

    assert requests == [
        (
            "https://api.openai.example/v1/responses",
            {
                "model": "gpt-5.2",
                "input": "Reply with one short word.",
                "max_output_tokens": 16,
                "reasoning": {"effort": "low"},
            },
        ),
        (
            "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
            {
                "model": "doubao-1-5-pro-32k-250115",
                "messages": [{"role": "user", "content": "Reply with one short word."}],
                "max_tokens": 16,
                "thinking": {"type": "disabled"},
            },
        ),
        (
            "https://api.deepseek.com/anthropic/v1/messages",
            {
                "model": "deepseek-v4-pro",
                "max_tokens": 1025,
                "thinking": {"type": "enabled", "budget_tokens": 1024},
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": "Reply with one short word."}],
                    }
                ],
            },
        ),
    ]


@pytest.mark.anyio
async def test_request_official_gemini_generation_uses_thinking_level_payload() -> None:
    requests: list[tuple[str, dict[str, object]]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append((str(request.url), json.loads(request.content.decode())))
        return httpx.Response(200, json={"id": "ok"}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await copilot_test._request_official_call_method_generation(
            client,
            "gemini_generate_content",
            "secret",
            "https://generativelanguage.googleapis.com",
            "gemini-3.1-pro-preview",
            runtime_settings={
                "max_output_tokens": 16,
                "reasoning": {"enabled": True, "effort": "low"},
            },
        )

    assert requests == [
        (
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-pro-preview:generateContent?key=secret",
            {
                "contents": [{"parts": [{"text": "Reply with one short word."}]}],
                "generationConfig": {
                    "maxOutputTokens": 16,
                    "thinkingConfig": {"thinkingLevel": "low"},
                },
            },
        )
    ]
    assert "thinkingBudget" not in json.dumps(requests[0][1])


def test_model_probe_message_includes_vendor_error_message() -> None:
    response = httpx.Response(
        404,
        json={
            "error": {
                "code": 404,
                "message": (
                    "This model models/gemini-3-pro-preview is no longer available. "
                    "Please update your code to use a newer model."
                ),
                "status": "NOT_FOUND",
            }
        },
    )

    assert copilot_test._model_probe_message(response) == (
        "Provider returned HTTP 404 (NOT_FOUND). "
        "This model models/gemini-3-pro-preview is no longer available. "
        "Please update your code to use a newer model."
    )
