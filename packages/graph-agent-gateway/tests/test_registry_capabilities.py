"""Provider capability normalization tests."""

from __future__ import annotations


def test_anthropic_doc_constraints_are_normalized_for_thinking_models() -> None:
    from graph_agent_gateway.registry.capabilities import normalize_route_capabilities

    capabilities = normalize_route_capabilities(
        protocol="anthropic_compatible",
        provider_model_id="claude-sonnet-4-6",
        raw_capabilities={
            "max_input_tokens": 1_000_000,
            "max_output_tokens": 128_000,
            "thinking": {"supported": True},
            "structured_outputs": {"supported": True},
            "image_input": {"supported": True},
        },
        source="api_list",
    )

    assert capabilities["thinking_protocol"].value is True
    assert capabilities["min_output_tokens"].value == 1
    assert capabilities["reasoning_budget_tokens"].value == {"min": 1024, "default": 4096}
    assert capabilities["min_thinking_budget_tokens"].value == 1024
    assert capabilities["default_thinking_budget_tokens"].value == 4096
    assert capabilities["requires_thinking_budget_lt_max_output"].value is True
    assert capabilities["max_output_tokens"].value == 128_000
    assert capabilities["structured_output_protocol"].value is True
    assert capabilities["vision"].value is True
    assert capabilities["tool_protocol"].value is True
    assert capabilities["tool_protocol"].source == "provider_doc"


def test_openai_and_deepseek_models_do_not_get_fake_thinking_budget_tokens() -> None:
    from graph_agent_gateway.registry.capabilities import normalize_route_capabilities

    openai_caps = normalize_route_capabilities(
        protocol="openai_compatible",
        provider_model_id="gpt-5",
        raw_capabilities={"owned_by": "system"},
        source="api_list",
    )
    deepseek_caps = normalize_route_capabilities(
        protocol="openai_compatible",
        provider_model_id="deepseek-r1",
        raw_capabilities={},
        source="api_list",
    )

    assert openai_caps["min_output_tokens"].value == 1
    assert "min_thinking_budget_tokens" not in openai_caps
    assert "min_thinking_budget_tokens" not in deepseek_caps


def test_anthropic_opus_47_marks_manual_thinking_budget_unsupported() -> None:
    from graph_agent_gateway.registry.capabilities import normalize_route_capabilities

    capabilities = normalize_route_capabilities(
        protocol="anthropic_compatible",
        provider_model_id="claude-opus-4-7",
        raw_capabilities={"thinking": {"supported": True}},
        source="probed_verified",
    )

    assert capabilities["thinking_protocol"].value is True
    assert capabilities["manual_thinking_budget_supported"].value is False
    assert capabilities["adaptive_thinking"].value is True
    assert "min_thinking_budget_tokens" not in capabilities


def test_anthropic_haiku_thinking_uses_manual_budget_not_adaptive() -> None:
    from graph_agent_gateway.registry.capabilities import normalize_route_capabilities

    capabilities = normalize_route_capabilities(
        protocol="anthropic_compatible",
        provider_model_id="claude-haiku-4-5-20251001",
        raw_capabilities={"thinking": {"supported": True}},
        source="probed_verified",
    )

    assert capabilities["thinking_protocol"].value is True
    assert capabilities["adaptive_thinking"].value is False
    assert capabilities["manual_thinking_budget_supported"].value is True
    assert capabilities["min_thinking_budget_tokens"].value == 1024
