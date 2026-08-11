"""Base URL canonicalization contract tests."""

from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    ("url", "protocol", "expected"),
    [
        (
            "https://llm.wavespeed.ai/v1",
            "anthropic_compatible",
            "https://llm.wavespeed.ai",
        ),
        (
            "https://llm.wavespeed.ai/v1/",
            "anthropic_compatible",
            "https://llm.wavespeed.ai",
        ),
        (
            "https://api.anthropic.example/v1",
            "anthropic_compatible",
            "https://api.anthropic.example",
        ),
        (
            "https://openrouter.example/api/v1/",
            "openai_compatible",
            "https://openrouter.example/api/v1",
        ),
        (
            "https://api.openai.example",
            "openai_compatible",
            "https://api.openai.example",
        ),
        (
            "https://api.deepseek.com/v1",
            "anthropic_compatible",
            "https://api.deepseek.com/anthropic",
        ),
        (
            "https://api.deepseek.com/anthropic",
            "anthropic_compatible",
            "https://api.deepseek.com/anthropic",
        ),
        (
            "https://ark.cn-beijing.volces.com",
            "ark_runtime",
            "https://ark.cn-beijing.volces.com/api/v3",
        ),
        (
            "https://ark.cn-beijing.volces.com/api/v3/",
            "ark_runtime",
            "https://ark.cn-beijing.volces.com/api/v3",
        ),
    ],
)
def test_canonicalize_base_url_is_idempotent_per_protocol(
    url: str,
    protocol: str,
    expected: str,
) -> None:
    from graph_agent_gateway.registry import canonicalize_base_url

    assert canonicalize_base_url(url, protocol) == expected
    assert canonicalize_base_url(expected, protocol) == expected
