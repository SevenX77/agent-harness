from graph_agent_gateway.registry.call_methods import (
    apply_call_method_base_url,
    call_method_client_compatibility,
    call_method_ids_for_client,
    official_call_method_ids,
    provider_probe_backend_for_method,
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
    assert provider_probe_backend_for_method("deepseek_anthropic_messages") == "deepseek"
    assert provider_probe_backend_for_method("ark_anthropic_messages") == "ark"
    assert "openrouter_anthropic_messages" not in official_call_method_ids()

    assert (
        apply_call_method_base_url("deepseek_anthropic_messages", "https://api.deepseek.com/v1")
        == "https://api.deepseek.com/anthropic"
    )
    assert (
        apply_call_method_base_url("ark_anthropic_messages", "https://ark.cn-beijing.volces.com/api/v3")
        == "https://ark.cn-beijing.volces.com/api/compatible"
    )
