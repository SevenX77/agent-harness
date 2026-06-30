"""Data-driven provider identity config (W3-A / T2).

The router used to hardcode provider keyword/domain matches (``"qiniu"`` /
``"qnaigc.com"`` -> ``"qiniu"``, ``"openrouter"`` -> ``"openrouter"``). That meant
teaching Studio about a new provider required a code change. This module reads those
mappings from ``app/data/provider_identity.json`` instead, so a new provider is a config
edit. The ``key`` indexes ``docs/development/llm_provider_notes/<key>.md`` for notable
model suggestions.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, NamedTuple

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "data" / "provider_identity.json"
_PROBE_CANDIDATES_PATH = Path(__file__).resolve().parents[1] / "data" / "probe_candidates.json"


class ProviderIdentity(NamedTuple):
    """One configured provider's identity-matching rules."""

    key: str
    display_alias: str
    keywords: tuple[str, ...]
    registrable_domains: tuple[str, ...]
    official_hosts: tuple[str, ...]
    official_endpoint_id: str | None
    language_model_prefixes: tuple[str, ...]
    non_language_model_tokens: tuple[str, ...]


@lru_cache(maxsize=1)
def provider_identities() -> tuple[ProviderIdentity, ...]:
    """Load (and cache) the provider-identity config."""
    raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    providers = raw.get("providers", [])
    return tuple(
        ProviderIdentity(
            key=str(entry["key"]),
            display_alias=str(entry.get("display_alias", entry["key"])),
            keywords=tuple(str(keyword).lower() for keyword in entry.get("keywords", [])),
            registrable_domains=tuple(
                str(domain).lower() for domain in entry.get("registrable_domains", [])
            ),
            official_hosts=tuple(
                str(host).lower() for host in entry.get("official_hosts", [])
            ),
            official_endpoint_id=(
                str(entry["official_endpoint_id"]) if entry.get("official_endpoint_id") else None
            ),
            language_model_prefixes=tuple(
                str(prefix).lower() for prefix in entry.get("language_model_prefixes", [])
            ),
            non_language_model_tokens=tuple(
                str(token).lower() for token in entry.get("non_language_model_tokens", [])
            ),
        )
        for entry in providers
    )


def _host_in_domain(host: str, domain: str) -> bool:
    return host == domain or host.endswith(f".{domain}")


def notable_provider_key_for(text_haystack: str, hostname: str) -> str | None:
    """Return the configured provider key matching this endpoint, or ``None``.

    Matched by a keyword in ``text_haystack`` (the endpoint id + display name) or by the
    endpoint ``hostname`` falling within a configured registrable domain. Both inputs are
    matched case-insensitively.
    """
    haystack = text_haystack.lower()
    host = hostname.lower()
    for identity in provider_identities():
        if any(keyword in haystack for keyword in identity.keywords):
            return identity.key
        if any(_host_in_domain(host, domain) for domain in identity.registrable_domains):
            return identity.key
    return None


def official_endpoint_id_for_host(hostname: str) -> str | None:
    """Return the stable official endpoint id for an official-provider host, or ``None``.

    Matched by the endpoint ``hostname`` falling within a configured ``official_hosts``
    entry (host == value or host endswith .value). Case-insensitive.
    """
    host = hostname.lower()
    for identity in provider_identities():
        if identity.official_endpoint_id is None:
            continue
        if any(_host_in_domain(host, official) for official in identity.official_hosts):
            return identity.official_endpoint_id
    return None


@lru_cache(maxsize=1)
def _probe_candidate_table() -> dict[str, tuple[dict[str, Any], ...]]:
    raw = json.loads(_PROBE_CANDIDATES_PATH.read_text(encoding="utf-8"))
    table = raw.get("probe_candidates", {})
    return {str(backend): tuple(specs) for backend, specs in table.items()}


def static_probe_candidate_specs(backend: str) -> tuple[dict[str, Any], ...] | None:
    """Return the static ``_candidate(**spec)`` kwargs for a backend's official
    language-model probe, or ``None`` if that backend computes candidates in code.

    Only backends whose candidate list is fixed (model-independent) are configured in
    ``app/data/probe_candidates.json`` (claude / deepseek / ark). openai and gemini pick
    candidates from the model id and stay in ``routers/llm.py``.
    """
    return _probe_candidate_table().get(backend)


def language_model_classification(key: str) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    """Return ``(language_prefixes, non_language_tokens)`` for a provider, or ``None`` if it
    has no configured language-model classifier.

    A model is a language model when it contains NONE of the non-language tokens AND
    starts with one of the language prefixes (the model id is matched lowercased).
    """
    for identity in provider_identities():
        if identity.key == key and identity.language_model_prefixes:
            return identity.language_model_prefixes, identity.non_language_model_tokens
    return None
