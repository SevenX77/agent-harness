"""Schema migrations for Studio LLM config files."""

from __future__ import annotations

from typing import Any

_PROVIDER_TYPE_REPLACEMENTS: dict[str, str] = {
    "gemini_official": "google_genai",
    "wavespeed_any_llm": "openai_compatible",
}


def migrate_provider_type_value(value: Any) -> Any:
    """Map legacy ProviderType strings to their current canonical equivalents.

    ``gemini_official`` was renamed to ``google_genai`` to match the SDK name.
    Wavespeed used the OpenAI /v1/models contract; collapsing it to
    ``openai_compatible`` preserves runtime behavior while removing a redundant
    enum branch from ``ProviderType``.
    """

    if isinstance(value, str) and value in _PROVIDER_TYPE_REPLACEMENTS:
        return _PROVIDER_TYPE_REPLACEMENTS[value]
    return value


def migrate_roles_payload(payload: Any) -> Any:
    """Walk a llm_roles.yaml payload and rewrite legacy values in place."""

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
    roles = payload.get("roles")
    if isinstance(roles, dict):
        for role in roles.values():
            if not isinstance(role, dict):
                continue
            role_temperature = role.pop("temperature", None)
            models = role.get("models")
            if role_temperature is None or not isinstance(models, dict):
                continue
            for role_model in models.values():
                if not isinstance(role_model, dict):
                    continue
                role_model.setdefault("temperature", role_temperature)
    return payload


def migrate_credentials_payload(payload: Any) -> Any:
    """Walk an llm_credentials.json payload and rewrite legacy provider_type values."""

    if not isinstance(payload, dict):
        return payload
    providers = payload.get("providers")
    if isinstance(providers, list):
        for provider in providers:
            if not isinstance(provider, dict):
                continue
            current = provider.get("provider_type")
            migrated = migrate_provider_type_value(current)
            if migrated != current:
                provider["provider_type"] = migrated
    return payload


__all__ = [
    "migrate_credentials_payload",
    "migrate_provider_type_value",
    "migrate_roles_payload",
]
