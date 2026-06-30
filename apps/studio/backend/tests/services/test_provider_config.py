"""W3-A / T2: the provider-identity config drives provider_key matching (no hardcode)."""

from __future__ import annotations

from app.services.provider_config import notable_provider_key_for, provider_identities


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
