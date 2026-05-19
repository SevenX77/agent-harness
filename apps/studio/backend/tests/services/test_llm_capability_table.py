"""Tests for ``app.services.llm_capability_table.lookup_capabilities``."""

from __future__ import annotations

from app.models.llm_config import ModelCapabilities
from app.services.llm_capability_table import (
    STATIC_FALLBACK_MODELS,
    lookup_capabilities,
)


def test_anthropic_known_prefix_returns_full_caps() -> None:
    caps = lookup_capabilities("anthropic_compatible", "claude-opus-4-1")
    assert caps == ModelCapabilities(
        text=True, function_calling=True, vision=True, reasoning=True
    )


def test_openai_o3_marks_reasoning_true() -> None:
    caps = lookup_capabilities("openai_compatible", "o3-mini")
    assert caps.reasoning is True
    assert caps.function_calling is True


def test_gemini_known_prefix_returns_vision_true() -> None:
    caps = lookup_capabilities("gemini_official", "gemini-2.5-flash-preview")
    assert caps.vision is True
    assert caps.reasoning is False


def test_longest_prefix_wins_for_overlapping_entries() -> None:
    # "claude-3-opus" is more specific than "claude-3-"; verify the longer prefix wins.
    caps_specific = lookup_capabilities("anthropic_compatible", "claude-3-opus-20240229")
    caps_generic = lookup_capabilities("anthropic_compatible", "claude-3-sonnet-20240229")
    assert caps_specific.function_calling is True
    assert caps_generic.function_calling is True


def test_unknown_id_falls_back_to_text_only_defaults() -> None:
    caps = lookup_capabilities("openai_compatible", "totally-unknown-model")
    assert caps == ModelCapabilities()
    assert caps.text is True
    assert caps.function_calling is False
    assert caps.vision is False
    assert caps.reasoning is False


def test_empty_or_whitespace_model_id_returns_defaults() -> None:
    assert lookup_capabilities("openai_compatible", "") == ModelCapabilities()
    assert lookup_capabilities("openai_compatible", "   ") == ModelCapabilities()


def test_static_fallback_models_cover_canonical_provider_types() -> None:
    # The table covers the three canonical UI-facing provider types; wavespeed
    # is OpenAI-compatible at the /models contract level and reuses the
    # openai_compatible entry.
    expected = {"anthropic_compatible", "openai_compatible", "gemini_official"}
    assert expected.issubset(set(STATIC_FALLBACK_MODELS.keys()))
    for models in STATIC_FALLBACK_MODELS.values():
        assert len(models) > 0
        assert all(isinstance(m, str) and m for m in models)
