"""Static capability lookup for known LLM model ids.

The Studio Test flow records a model list returned by ``/v1/models`` (or
``/v1beta/models``). Vendors do not expose capability flags on that endpoint,
so this module supplies a lightweight static lookup keyed by ``(provider_type,
model_id_prefix)``. Unknown ids degrade to ``ModelCapabilities()`` defaults
(``text=True`` only).

The table is intentionally small and conservative — it is a baseline for the
UI's per-model badges, not a full vendor matrix. Operators can extend it
without touching the request/response schema.
"""

from __future__ import annotations

from app.models.llm_config import ModelCapabilities, ProviderType

# (provider_type, model id prefix) -> capabilities. Longer prefixes win.
CAPABILITY_TABLE: dict[tuple[ProviderType, str], ModelCapabilities] = {
    ("anthropic_compatible", "claude-opus-4"): ModelCapabilities(
        text=True, function_calling=True, vision=True, reasoning=True
    ),
    ("anthropic_compatible", "claude-sonnet-4"): ModelCapabilities(
        text=True, function_calling=True, vision=True, reasoning=True
    ),
    ("anthropic_compatible", "claude-haiku-4"): ModelCapabilities(
        text=True, function_calling=True, vision=True, reasoning=False
    ),
    ("anthropic_compatible", "claude-3-5"): ModelCapabilities(
        text=True, function_calling=True, vision=True, reasoning=False
    ),
    ("anthropic_compatible", "claude-3-opus"): ModelCapabilities(
        text=True, function_calling=True, vision=True, reasoning=False
    ),
    ("anthropic_compatible", "claude-3-sonnet"): ModelCapabilities(
        text=True, function_calling=True, vision=True, reasoning=False
    ),
    ("anthropic_compatible", "claude-3-haiku"): ModelCapabilities(
        text=True, function_calling=True, vision=True, reasoning=False
    ),
    ("openai_compatible", "gpt-5"): ModelCapabilities(
        text=True, function_calling=True, vision=True, reasoning=True
    ),
    ("openai_compatible", "gpt-4o"): ModelCapabilities(
        text=True, function_calling=True, vision=True, reasoning=False
    ),
    ("openai_compatible", "gpt-4"): ModelCapabilities(
        text=True, function_calling=True, vision=False, reasoning=False
    ),
    ("openai_compatible", "gpt-3.5"): ModelCapabilities(
        text=True, function_calling=True, vision=False, reasoning=False
    ),
    ("openai_compatible", "o3"): ModelCapabilities(
        text=True, function_calling=True, vision=False, reasoning=True
    ),
    ("openai_compatible", "o1"): ModelCapabilities(
        text=True, function_calling=False, vision=False, reasoning=True
    ),
    ("openai_compatible", "deepseek-r1"): ModelCapabilities(
        text=True, function_calling=True, vision=False, reasoning=True
    ),
    ("openai_compatible", "deepseek-chat"): ModelCapabilities(
        text=True, function_calling=True, vision=False, reasoning=False
    ),
    ("openai_compatible", "deepseek-coder"): ModelCapabilities(
        text=True, function_calling=True, vision=False, reasoning=False
    ),
    ("gemini_official", "gemini-2.5-pro"): ModelCapabilities(
        text=True, function_calling=True, vision=True, reasoning=True
    ),
    ("gemini_official", "gemini-2.5-flash"): ModelCapabilities(
        text=True, function_calling=True, vision=True, reasoning=False
    ),
    ("gemini_official", "gemini-2.0"): ModelCapabilities(
        text=True, function_calling=True, vision=True, reasoning=False
    ),
    ("gemini_official", "gemini-1.5"): ModelCapabilities(
        text=True, function_calling=True, vision=True, reasoning=False
    ),
}

# Fallback model ids surfaced when a /models call returns an empty list
# (typically because the vendor scopes /models per-key and the key has zero
# allow-listed models). These give the user something selectable in the UI
# without lying about capability.
STATIC_FALLBACK_MODELS: dict[ProviderType, tuple[str, ...]] = {
    "anthropic_compatible": (
        "claude-opus-4-1",
        "claude-sonnet-4-5",
        "claude-haiku-4-5",
    ),
    "openai_compatible": (
        "gpt-5",
        "gpt-4o",
        "gpt-4o-mini",
    ),
    "gemini_official": (
        "gemini-2.5-pro",
        "gemini-2.5-flash",
    ),
}


def lookup_capabilities(provider_type: ProviderType, model_id: str) -> ModelCapabilities:
    """Look up capabilities for a model id, picking the longest matching prefix.

    Returns default ``ModelCapabilities()`` (text-only) when no prefix matches —
    safer than guessing, since the UI can fall back to a generic "text" badge.
    """

    normalized = model_id.strip().lower()
    if not normalized:
        return ModelCapabilities()

    best_prefix = ""
    best_caps: ModelCapabilities | None = None
    for (table_provider, prefix), caps in CAPABILITY_TABLE.items():
        if table_provider != provider_type:
            continue
        prefix_lower = prefix.lower()
        if normalized.startswith(prefix_lower) and len(prefix_lower) > len(best_prefix):
            best_prefix = prefix_lower
            best_caps = caps
    return best_caps if best_caps is not None else ModelCapabilities()


__all__ = [
    "CAPABILITY_TABLE",
    "STATIC_FALLBACK_MODELS",
    "lookup_capabilities",
]
