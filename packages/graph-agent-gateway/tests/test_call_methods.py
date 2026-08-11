from graph_agent_gateway.registry import (
    ProviderEndpoint,
    apply_call_method_base_url,
    call_method_client_compatibility,
    call_method_ids_for_client,
    call_method_ids_for_endpoint,
    call_method_is_officially_probeable,
    official_call_method_ids,
    provider_backend_for_endpoint,
    provider_backend_for_method,
    provider_backend_for_protocol,
)
from pydantic import SecretStr


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


def test_the_vendor_an_endpoint_belongs_to_is_not_a_probe() -> None:
    """No request is sent to answer it, so `probing` does not own it.

    The answer decides which official call methods the registry offers for an
    endpoint, it returns a type the call-method table defines, and it needs the
    same host rules the table already applies — all three say it belongs here.
    """

    from graph_agent_gateway import probing

    assert "endpoint_probe_backend" not in probing.__all__
    assert "probe_wire_backend" not in probing.__all__


def test_a_host_is_the_same_host_whether_or_not_the_scheme_was_typed() -> None:
    """One host rule, one answer, for every question the table is asked.

    `base_url` is free text on `ProviderEndpoint` — nothing requires a scheme —
    and the two rules used to read it through two different parsers. The vendor
    rule recognised `api.deepseek.com`; the candidate rule read the same string
    as hostless and silently withheld the extra method that host publishes.
    """

    assert call_method_ids_for_endpoint("openai_compatible", "api.qnaigc.com/v1") == (
        call_method_ids_for_endpoint("openai_compatible", "https://api.qnaigc.com/v1")
    )
    assert call_method_ids_for_endpoint("openai_compatible", "https://api.qnaigc.com./v1") == (
        call_method_ids_for_endpoint("openai_compatible", "https://api.qnaigc.com/v1")
    )
    assert provider_backend_for_endpoint(
        ProviderEndpoint(
            endpoint_id="scheme-less",
            protocol="openai_compatible",
            base_url="api.deepseek.com/v1",
        )
    ) == "deepseek"


def test_whose_api_it_is_and_how_to_speak_to_it_are_answered_separately() -> None:
    """DeepSeek's Anthropic surface is DeepSeek's, and it speaks Anthropic.

    The vendor decides which official methods are offered for the endpoint; the
    declared protocol decides the wire. Collapsing them is how an endpoint that
    said `anthropic_compatible` came to be probed with an OpenAI chat request:
    `probe_official_call_method` already speaks x-api-key and /v1/messages to
    this very surface.
    """

    endpoint = ProviderEndpoint(
        endpoint_id="deepseek-official",
        protocol="anthropic_compatible",
        base_url="https://api.deepseek.com/anthropic",
        api_key=SecretStr("secret"),
        provider_kind="official",
    )

    assert provider_backend_for_endpoint(endpoint) == "deepseek"
    assert provider_backend_for_protocol(endpoint.protocol) == "claude"


def test_a_host_that_does_not_publish_that_protocol_is_not_that_vendor() -> None:
    # DeepSeek publishes an OpenAI-compatible and an Anthropic-compatible
    # surface. A url on that host declaring anything else is neither.
    endpoint = ProviderEndpoint(
        endpoint_id="odd-one",
        protocol="ark_runtime",
        base_url="https://api.deepseek.com/api/v3",
        api_key=SecretStr("secret"),
        provider_kind="third_party",
    )

    assert provider_backend_for_endpoint(endpoint) == "ark"


def test_an_endpoint_named_after_a_vendor_is_not_that_vendor() -> None:
    # The name is a label the user typed. It used to decide which official
    # method menu the endpoint got and which token budget field it was sent.
    endpoint = ProviderEndpoint(
        endpoint_id="deepseek-fast",
        protocol="openai_compatible",
        base_url="https://gateway.example/v1",
        api_key=SecretStr("secret"),
        provider_kind="third_party",
    )

    assert provider_backend_for_endpoint(endpoint) == "openai"


def test_ark_openai_compatible_endpoint_backend_uses_openai_protocol() -> None:
    endpoint = ProviderEndpoint(
        endpoint_id="ark-openai-official",
        protocol="openai_compatible",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        api_key=SecretStr("secret"),
        provider_kind="official",
    )

    assert provider_backend_for_endpoint(endpoint) == "openai"
