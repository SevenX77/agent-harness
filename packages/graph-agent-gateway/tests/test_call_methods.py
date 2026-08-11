from graph_agent_gateway.registry import (
    apply_call_method_base_url,
    call_method_client_compatibility,
    call_method_ids_for_client,
    call_method_ids_for_endpoint,
    call_method_is_officially_probeable,
    official_call_method_ids,
    provider_backend_for_method,
)


def test_call_method_catalog_marks_anthropic_client_compatible_methods() -> None:
    assert call_method_ids_for_client("anthropic_messages_client") == frozenset(
        {
            "anthropic_messages",
            "ark_anthropic_messages",
            "deepseek_anthropic_messages",
            "openrouter_anthropic_messages",
        }
    )
    assert call_method_client_compatibility(
        "openai_responses",
        "anthropic_messages_client",
    ) == "incompatible"
    assert call_method_client_compatibility(
        "gemini_generate_content",
        "anthropic_messages_client",
    ) == "incompatible"
    assert call_method_client_compatibility(
        "future_provider_anthropicish",
        "anthropic_messages_client",
    ) == "unknown"


def test_call_method_catalog_owns_probe_backend_and_base_url_transform() -> None:
    assert provider_backend_for_method("deepseek_anthropic_messages") == "deepseek"
    assert provider_backend_for_method("ark_anthropic_messages") == "ark"
    assert "openrouter_anthropic_messages" not in official_call_method_ids()


def test_a_method_the_official_probe_skips_still_names_its_provider() -> None:
    # Whether a method can be sent and whether the official-method probe offers
    # it are two questions: an OpenRouter endpoint is still reachable, and
    # asking who stands behind its method must not fail because no official
    # probe lists it.
    assert not call_method_is_officially_probeable("openrouter_anthropic_messages")
    assert provider_backend_for_method("openrouter_anthropic_messages") == "claude"

    assert (
        apply_call_method_base_url("deepseek_anthropic_messages", "https://api.deepseek.com/v1")
        == "https://api.deepseek.com/anthropic"
    )
    assert (
        apply_call_method_base_url("ark_anthropic_messages", "https://ark.cn-beijing.volces.com/api/v3")
        == "https://ark.cn-beijing.volces.com/api/compatible"
    )


def test_endpoint_method_candidates_are_gateway_catalog_truth() -> None:
    assert call_method_ids_for_endpoint(
        "anthropic_compatible",
        "https://api.qnaigc.com",
    ) == ("anthropic_messages",)
    assert call_method_ids_for_endpoint(
        "openai_compatible",
        "https://api.openai.com",
    ) == ("openai_chat_completions",)
    assert call_method_ids_for_endpoint(
        "openai_compatible",
        "https://api.qnaigc.com/v1",
    ) == ("openai_chat_completions", "anthropic_messages")
    assert call_method_ids_for_endpoint(
        "openai_compatible",
        "https://openrouter.ai/api/v1",
    ) == ("openai_chat_completions", "openrouter_anthropic_messages")


def test_anthropic_messages_base_url_transform_uses_anthropic_canonical_shape() -> None:
    assert (
        apply_call_method_base_url("anthropic_messages", "https://api.qnaigc.com/v1")
        == "https://api.qnaigc.com"
    )
    assert (
        apply_call_method_base_url("openrouter_anthropic_messages", "https://openrouter.ai/api/v1")
        == "https://openrouter.ai/api"
    )
