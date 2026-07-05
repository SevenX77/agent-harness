"""W3-A / T2: the provider-identity config drives provider_key matching (no hardcode)."""

from __future__ import annotations

from app.services.provider_config import (
    language_model_classification,
    notable_provider_key_for,
    official_endpoint_id_for_host,
    official_endpoint_id_for_host_protocol,
    official_provider_key_for_host,
    provider_identities,
    static_probe_candidate_specs,
)


def test_keyword_in_id_or_name_maps_to_provider_key() -> None:
    assert notable_provider_key_for("my-qiniu-endpoint", "") == "qiniu"
    assert notable_provider_key_for("OpenRouter prod", "") == "openrouter"


def test_registrable_domain_maps_to_provider_key() -> None:
    assert notable_provider_key_for("custom-id", "api.qnaigc.com") == "qiniu"
    assert notable_provider_key_for("custom-id", "openrouter.ai") == "openrouter"
    # W3-A adds wavespeed (it has a notes doc but was previously unmapped -> fell back
    # to the probe backend); now it's a one-line config entry.
    assert notable_provider_key_for("custom-id", "llm.wavespeed.ai") == "wavespeed"


def test_unconfigured_endpoint_returns_none_so_caller_falls_back() -> None:
    assert notable_provider_key_for("openai-direct", "api.openai.com") is None
    assert notable_provider_key_for("", "") is None


def test_matching_is_case_insensitive() -> None:
    assert notable_provider_key_for("QINIU", "API.QNAIGC.COM") == "qiniu"


def test_config_exposes_display_aliases() -> None:
    aliases = {identity.key: identity.display_alias for identity in provider_identities()}
    assert aliases["qiniu"] == "Qiniu"
    assert aliases["wavespeed"] == "WaveSpeed"


def test_official_host_maps_to_stable_endpoint_id() -> None:
    assert official_endpoint_id_for_host("api.openai.com") == "openai-official"
    assert official_endpoint_id_for_host("api.anthropic.com") == "anthropic-official"
    assert official_endpoint_id_for_host("api.deepseek.com") == "deepseek-official"
    assert official_endpoint_id_for_host("generativelanguage.googleapis.com") == "gemini-official"
    # ARK matches by registrable domain — any *.volces.com host, or the bare domain.
    assert official_endpoint_id_for_host("ark.cn-beijing.volces.com") is None
    assert official_endpoint_id_for_host("volces.com") is None
    assert official_endpoint_id_for_host("API.OPENAI.COM") == "openai-official"


def test_official_host_protocol_maps_to_stable_endpoint_id() -> None:
    assert (
        official_endpoint_id_for_host_protocol("ark.cn-beijing.volces.com", "ark_runtime")
        == "ark-official"
    )
    assert (
        official_endpoint_id_for_host_protocol("ark.cn-beijing.volces.com", "openai_compatible")
        == "ark-openai-official"
    )
    assert official_endpoint_id_for_host_protocol("api.openai.com", "openai_compatible") == "openai-official"
    assert official_endpoint_id_for_host_protocol("api.openai.com", "anthropic_compatible") is None


def test_official_host_maps_to_provider_catalog_key() -> None:
    assert official_provider_key_for_host("ark.cn-beijing.volces.com") == "ark"
    assert official_provider_key_for_host("api.openai.com") == "openai"
    assert official_provider_key_for_host("api.qnaigc.com") is None


def test_non_official_host_returns_none() -> None:
    # Third-party identity providers have no official endpoint id.
    assert official_endpoint_id_for_host("api.qnaigc.com") is None
    assert official_endpoint_id_for_host("") is None


def test_probe_candidates_configured_only_for_static_backends() -> None:
    assert static_probe_candidate_specs("claude") is not None
    assert static_probe_candidate_specs("deepseek") is not None
    assert static_probe_candidate_specs("ark") is not None
    # openai + gemini pick candidates from the model id, so they stay in code.
    assert static_probe_candidate_specs("openai") is None
    assert static_probe_candidate_specs("gemini") is None
    assert static_probe_candidate_specs("unknown") is None


def test_probe_candidate_specs_match_the_static_tables() -> None:
    claude = static_probe_candidate_specs("claude")
    deepseek = static_probe_candidate_specs("deepseek")
    ark = static_probe_candidate_specs("ark")
    assert claude is not None and deepseek is not None and ark is not None
    assert (len(claude), len(deepseek), len(ark)) == (3, 4, 6)
    # ARK's primary chat candidate is rank 10 / fallback 2.
    assert ark[0]["method_id"] == "ark_chat"
    assert ark[0]["profile_id"] == "text:ark_chat"
    assert ark[0]["default_rank"] == 10
    assert ark[0]["fallback_rank"] == 2
    # Every spec carries the keyword args _candidate() requires.
    required = {"method_id", "profile_id", "capability", "request_mapper_id", "default_rank", "fallback_rank"}
    for specs in (claude, deepseek, ark):
        for spec in specs:
            assert required <= set(spec)


def test_language_model_classification_only_for_configured_providers() -> None:
    assert language_model_classification("ark") is not None
    # identity-only / dynamic-code providers have no configured classifier.
    assert language_model_classification("qiniu") is None
    assert language_model_classification("openai") is None
    assert language_model_classification("unknown") is None


def test_ark_classification_accepts_language_models_and_rejects_media() -> None:
    classification = language_model_classification("ark")
    assert classification is not None
    prefixes, non_language_tokens = classification

    def is_language(model: str) -> bool:
        lowered = model.lower()
        if any(token in lowered for token in non_language_tokens):
            return False
        return any(lowered.startswith(prefix) for prefix in prefixes)

    assert is_language("doubao-seed-1-6") is True
    assert is_language("qwen-max") is True
    assert is_language("ep-20240101120000") is True
    assert is_language("doubao-seedream-3-0") is False  # image token
    assert is_language("doubao-embedding-large") is False
    assert is_language("gpt-4o") is False  # not an ARK prefix
