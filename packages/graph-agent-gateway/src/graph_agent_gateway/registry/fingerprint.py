"""Registry storage helpers."""

from __future__ import annotations

import hashlib
import json

from pydantic import SecretStr

from graph_agent_gateway.registry.base_url import canonicalize_base_url
from graph_agent_gateway.registry.schema import ProviderEndpoint


def compute_credential_fingerprint(
    endpoint: ProviderEndpoint,
    secret: SecretStr | str | None = None,
) -> str:
    """Compute a non-reversible cache key fingerprint for endpoint credentials."""
    raw_secret = secret
    if raw_secret is None:
        raw_secret = endpoint.api_key
    if isinstance(raw_secret, SecretStr):
        secret_value = raw_secret.get_secret_value()
    else:
        secret_value = raw_secret or ""

    payload = {
        "endpoint_id": endpoint.endpoint_id,
        "protocol": endpoint.protocol,
        "base_url": _normalize_base_url(endpoint.base_url, endpoint.protocol),
        "secret": secret_value,
        "timeout_seconds": endpoint.timeout_seconds,
        "trust_env": endpoint.trust_env,
        "proxy_env": endpoint.proxy_env or "",
    }
    if endpoint.credential_ref:
        payload["credential_ref"] = endpoint.credential_ref
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _normalize_base_url(value: str, protocol: str) -> str:
    return canonicalize_base_url(value, protocol)
