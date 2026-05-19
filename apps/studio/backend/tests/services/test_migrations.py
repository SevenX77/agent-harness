"""Tests for ``app.services.migrations`` (ProviderType legacy value remap)."""

from __future__ import annotations

from app.services.migrations import migrate_provider_type_value, migrate_roles_payload


def test_migrate_wavespeed_any_llm_to_openai_compatible() -> None:
    assert migrate_provider_type_value("wavespeed_any_llm") == "openai_compatible"


def test_migrate_passes_through_known_canonical_values() -> None:
    for value in ("anthropic_compatible", "openai_compatible", "gemini_official"):
        assert migrate_provider_type_value(value) == value


def test_migrate_passes_through_unknown_strings_and_non_strings() -> None:
    assert migrate_provider_type_value("future_provider") == "future_provider"
    assert migrate_provider_type_value(None) is None
    assert migrate_provider_type_value(42) == 42


def test_migrate_roles_payload_rewrites_provider_type_in_place() -> None:
    payload = {
        "providers": {
            "WS_LLM": {"type": "wavespeed_any_llm", "base_url": "https://x"},
            "OC_CL": {"type": "anthropic_compatible"},
        },
    }
    migrated = migrate_roles_payload(payload)

    assert migrated["providers"]["WS_LLM"]["type"] == "openai_compatible"
    assert migrated["providers"]["WS_LLM"]["base_url"] == "https://x"
    assert migrated["providers"]["OC_CL"]["type"] == "anthropic_compatible"


def test_migrate_roles_payload_handles_missing_or_malformed_keys() -> None:
    # No providers key at all.
    assert migrate_roles_payload({}) == {}
    # Providers is not a dict.
    assert migrate_roles_payload({"providers": []}) == {"providers": []}
    # Provider entry is not a dict.
    assert migrate_roles_payload({"providers": {"X": "scalar"}}) == {"providers": {"X": "scalar"}}
    # Non-dict top-level payload.
    assert migrate_roles_payload(None) is None
