"""Provider capability normalization tests."""

from __future__ import annotations


def test_anthropic_doc_constraints_are_normalized_for_thinking_models() -> None:
    from graph_agent_gateway.registry import normalize_route_capabilities

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


def test_provider_model_list_token_limit_aliases_are_normalized() -> None:
    from graph_agent_gateway.registry import normalize_route_capabilities

    gemini_capabilities = normalize_route_capabilities(
        protocol="google_genai",
        provider_model_id="gemini-2.5-pro",
        raw_capabilities={
            "inputTokenLimit": 1_048_576,
            "outputTokenLimit": 65_536,
        },
        source="api_list",
    )
    anthropic_capabilities = normalize_route_capabilities(
        protocol="anthropic_compatible",
        provider_model_id="claude-sonnet-4-6",
        raw_capabilities={
            "context_window": 200_000,
            "maxOutputTokens": 64_000,
        },
        source="api_list",
    )

    assert gemini_capabilities["max_input_tokens"].value == 1_048_576
    assert gemini_capabilities["max_output_tokens"].value == 65_536
    assert anthropic_capabilities["max_input_tokens"].value == 200_000
    assert anthropic_capabilities["max_output_tokens"].value == 64_000


def test_provider_model_list_nested_modalities_and_token_limits_are_normalized() -> None:
    from graph_agent_gateway.registry import normalize_route_capabilities

    capabilities = normalize_route_capabilities(
        protocol="ark_runtime",
        provider_model_id="doubao-seed-1-6-thinking-250715",
        raw_capabilities={
            "modalities": {
                "input_modalities": ["text", "image", "video"],
                "output_modalities": ["text"],
            },
            "token_limits": {
                "context_window": 262_144,
                "max_input_token_length": 229_376,
                "max_output_token_length": 32_768,
            },
            "features": {
                "tools": {"function_calling": True},
                "structured_outputs": {"json_object": True, "json_schema": True},
            },
        },
        source="api_list",
    )

    assert capabilities["input_modalities"].value == ["text", "image", "video"]
    assert capabilities["output_modalities"].value == ["text"]
    assert capabilities["max_input_tokens"].value == 229_376
    assert capabilities["max_output_tokens"].value == 32_768
    assert capabilities["tool_protocol"].value is True
    assert capabilities["structured_output_protocol"].value is True


def test_openai_and_deepseek_models_do_not_get_fake_thinking_budget_tokens() -> None:
    from graph_agent_gateway.registry import normalize_route_capabilities

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
    from graph_agent_gateway.registry import normalize_route_capabilities

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
    from graph_agent_gateway.registry import normalize_route_capabilities

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


def test_a_protocol_that_pins_its_effort_vocabulary_bounds_what_is_worth_asking() -> None:
    """A name the request body cannot spell would spend a round trip to be
    refused, so it is never offered to the probe."""
    from graph_agent_gateway.registry import effort_probe_candidates

    assert effort_probe_candidates("anthropic_compatible") == (
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    )
    assert effort_probe_candidates("google_genai") == ("minimal", "low", "medium", "high")


def test_a_protocol_that_pins_nothing_offers_the_whole_ladder_to_the_probe() -> None:
    """OpenAI's set moves between model versions — exactly the case a document
    cannot answer and only asking can."""
    from graph_agent_gateway.registry import EFFORT_LADDER, effort_probe_candidates

    assert effort_probe_candidates("openai_compatible") == EFFORT_LADDER
    assert effort_probe_candidates(None) == EFFORT_LADDER


def test_measured_levels_become_the_capability_the_fitting_rules_read() -> None:
    """A measurement that lands anywhere else has changed nothing."""
    from graph_agent_gateway.registry import measured_effort_capability

    capability = measured_effort_capability(["low", "high", "max"])

    assert capability.source == "probed_verified"
    assert capability.value == {"supported": True, "values": ["low", "high", "max"]}


def test_a_route_that_sells_no_level_records_that_rather_than_staying_silent() -> None:
    """Absent reads as "nobody asked yet" and invites the same spend again."""
    from graph_agent_gateway.registry import measured_effort_capability

    capability = measured_effort_capability([])

    assert capability.value == {"supported": False, "values": []}
    assert "refused every" in (capability.message or "")


def test_an_image_a_route_accepted_becomes_the_capability_the_ui_reads() -> None:
    """The measurement has to land on the capability or nothing changed.

    Studio's image button asks whether image input is verified, and only a
    `probed_verified` answer counts; a probe whose answer stops at the evidence
    log leaves that button unable to ever say yes.
    """
    from graph_agent_gateway.registry import measured_image_input

    measured = measured_image_input(accepted=True)

    assert measured["vision"].value is True
    assert measured["vision"].source == "probed_verified"
    assert measured["input_modalities"].value == ["text", "image"]
    assert measured["input_modalities"].source == "probed_verified"


def test_a_route_that_refused_the_image_records_the_refusal_on_vision() -> None:
    """"It only takes text" is an answer, and it outranks the document claim.

    Same rule `measured_effort_capability` states for an empty measurement: an
    absent capability reads as "nobody has asked yet" and invites the same spend
    again, while a catalog's `provider_doc` claim of image support would stand
    unchallenged forever. Role lint reads `vision` and treats a falsy value as
    unmet, so the refusal is enforceable where it lands.
    """
    from graph_agent_gateway.registry import measured_image_input

    measured = measured_image_input(accepted=False)

    assert measured["vision"].value is False
    assert measured["vision"].source == "probed_verified"


def test_a_refusal_does_not_rewrite_the_modality_list_it_cannot_settle() -> None:
    """A modality list is a lower bound that hosts union together.

    One refused image proves images are out; it proves nothing about audio, pdf
    or anything else a document might list, so writing `["text"]` into the list
    would state a completeness this probe never established — and any host that
    unions lists would blend it back into the document's claim anyway.
    """
    from graph_agent_gateway.registry import measured_image_input

    assert "input_modalities" not in measured_image_input(accepted=False)
