"""Schema migrations for Studio LLM config files."""

from __future__ import annotations

from typing import Any

_PROVIDER_TYPE_REPLACEMENTS: dict[str, str] = {
    "wavespeed_any_llm": "openai_compatible",
}


def migrate_provider_type_value(value: Any) -> Any:
    """Map legacy ProviderType strings to their current canonical equivalents.

    Wavespeed used the OpenAI /v1/models contract; collapsing it to
    ``openai_compatible`` preserves runtime behavior while removing a redundant
    enum branch from ``ProviderType``.
    """

    if isinstance(value, str) and value in _PROVIDER_TYPE_REPLACEMENTS:
        return _PROVIDER_TYPE_REPLACEMENTS[value]
    return value


def migrate_roles_payload(payload: Any) -> Any:
    """Walk a llm_roles.yaml payload and rewrite legacy provider ``type`` values."""

    if not isinstance(payload, dict):
        return payload
    providers = payload.get("providers")
    if isinstance(providers, dict):
        for provider in providers.values():
            if not isinstance(provider, dict):
                continue
            current = provider.get("type")
            migrated = migrate_provider_type_value(current)
            if migrated != current:
                provider["type"] = migrated
    return payload


__all__ = ["migrate_provider_type_value", "migrate_roles_payload"]
