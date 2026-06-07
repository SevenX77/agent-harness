"""Per-protocol base URL canonicalization helpers."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from graph_agent_gateway.registry.schema import Protocol


def canonicalize_base_url(url: str, protocol: Protocol | str) -> str:
    """Return the runtime-canonical base URL for a provider protocol."""

    normalized = url.strip().rstrip("/")
    if not normalized:
        return normalized

    if protocol == "anthropic_compatible":
        return _canonicalize_anthropic_base_url(normalized)
    if protocol == "ark_runtime":
        return _canonicalize_ark_base_url(normalized)
    return normalized


def _canonicalize_anthropic_base_url(url: str) -> str:
    parsed = urlsplit(url)
    path = parsed.path.rstrip("/")
    is_deepseek = "deepseek" in parsed.netloc.lower()

    if path.endswith("/v1"):
        path = path[:-3] or ""

    if is_deepseek:
        if path == "/anthropic" or path.endswith("/anthropic"):
            canonical_path = path
        else:
            canonical_path = f"{path.rstrip('/')}/anthropic" if path else "/anthropic"
        return urlunsplit(parsed._replace(path=canonical_path))

    return urlunsplit(parsed._replace(path=path))


def _canonicalize_ark_base_url(url: str) -> str:
    parsed = urlsplit(url)
    path = parsed.path.rstrip("/")
    if path.endswith("/api/v3"):
        canonical_path = path
    else:
        canonical_path = f"{path.rstrip('/')}/api/v3" if path else "/api/v3"
    return urlunsplit(parsed._replace(path=canonical_path))
