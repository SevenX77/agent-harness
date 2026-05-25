"""Local v4 endpoint/route registry storage for Studio LLM credentials."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from pydantic import SecretStr, ValidationError

from app.models.llm_config import LLMCredentialsFile, ProviderEndpoint

_WRITE_LOCK = threading.Lock()
_credentials_lock = _WRITE_LOCK
SECRET_REDACTION_PLACEHOLDER = "**********"


def credentials_path() -> Path:
    """Return the local Studio LLM credentials path."""
    return Path.home() / ".studio" / "llm_credentials.json"


def load_credentials(path: Path | None = None) -> LLMCredentialsFile:
    """Read v4 credentials.

    A missing file is first-run setup and returns an empty v4 registry.
    Legacy or malformed files are fatal so runtime never silently falls back
    to old provider/env behavior.
    """
    credential_path = path or credentials_path()
    if not credential_path.exists():
        return LLMCredentialsFile()
    try:
        payload = json.loads(credential_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid llm_credentials.json: {credential_path}") from exc
    if isinstance(payload, dict) and (
        payload.get("schema_version") != 4 or "providers" in payload
    ):
        raise ValueError(
            f"llm_credentials.json must use schema_version 4; legacy provider "
            f"credentials are not runtime-compatible: {credential_path}"
        )
    try:
        return LLMCredentialsFile.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"invalid v4 llm credentials schema: {credential_path}") from exc


def save_credentials(data: LLMCredentialsFile, path: Path | None = None) -> None:
    """Atomically write credentials and force file permissions to ``0600``."""
    credential_path = path or credentials_path()
    with _credentials_lock:
        _save_credentials_unlocked(data, credential_path)


def serialize_for_response(data: LLMCredentialsFile, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
    """Return redacted credentials suitable for API responses."""
    return data.model_dump(mode="json")


def upsert_endpoints(
    endpoint_payloads: dict[str, dict[str, Any] | ProviderEndpoint],
    *,
    path: Path | None = None,
) -> LLMCredentialsFile:
    """Upsert endpoints while retaining absent endpoints and omitted secrets."""
    credential_path = path or credentials_path()
    with _credentials_lock:
        data = load_credentials(credential_path)
        endpoints = dict(data.provider_endpoints)
        for endpoint_id, payload in endpoint_payloads.items():
            incoming = _endpoint_from_payload(payload)
            if incoming.endpoint_id != endpoint_id:
                raise ValueError(f"endpoint payload key does not match endpoint_id: {endpoint_id}")
            current = endpoints.get(endpoint_id)
            api_key = _preserved_secret(incoming, current)
            endpoints[endpoint_id] = incoming.model_copy(update={"api_key": api_key})
        data = data.model_copy(update={"provider_endpoints": endpoints})
        _save_credentials_unlocked(data, credential_path)
        return data


def delete_endpoint(endpoint_id: str, *, path: Path | None = None) -> LLMCredentialsFile:
    """Delete one endpoint from active credentials."""
    credential_path = path or credentials_path()
    with _credentials_lock:
        data = load_credentials(credential_path)
        endpoints = dict(data.provider_endpoints)
        endpoints.pop(endpoint_id, None)
        routes = {
            route_id: route
            for route_id, route in data.provider_routes.items()
            if route.endpoint_id != endpoint_id
        }
        data = data.model_copy(
            update={"provider_endpoints": endpoints, "provider_routes": routes}
        )
        _save_credentials_unlocked(data, credential_path)
        return data


def upsert_routes(
    route_payloads: dict[str, Any],
    *,
    path: Path | None = None,
) -> LLMCredentialsFile:
    """Upsert route records while retaining absent routes."""
    from app.models.llm_config import ProviderRoute

    credential_path = path or credentials_path()
    with _credentials_lock:
        data = load_credentials(credential_path)
        routes = dict(data.provider_routes)
        for route_id, payload in route_payloads.items():
            route = payload if isinstance(payload, ProviderRoute) else ProviderRoute.model_validate(payload)
            if route.route_id != route_id:
                raise ValueError(f"route payload key does not match route_id: {route_id}")
            if route.endpoint_id not in data.provider_endpoints:
                raise ValueError(f"route references unknown endpoint: {route.endpoint_id}")
            routes[route_id] = route
        data = data.model_copy(update={"provider_routes": routes})
        _save_credentials_unlocked(data, credential_path)
        return data


def delete_route(route_id: str, *, path: Path | None = None) -> LLMCredentialsFile:
    """Delete one route from active credentials."""
    credential_path = path or credentials_path()
    with _credentials_lock:
        data = load_credentials(credential_path)
        routes = dict(data.provider_routes)
        routes.pop(route_id, None)
        data = data.model_copy(update={"provider_routes": routes})
        _save_credentials_unlocked(data, credential_path)
        return data


def _endpoint_from_payload(payload: dict[str, Any] | ProviderEndpoint) -> ProviderEndpoint:
    if isinstance(payload, ProviderEndpoint):
        return payload
    normalized = dict(payload)
    if normalized.get("api_key") == "":
        normalized["api_key"] = None
    return ProviderEndpoint.model_validate(normalized)


def _preserved_secret(
    incoming: ProviderEndpoint,
    current: ProviderEndpoint | None,
) -> SecretStr | None:
    if incoming.api_key is not None and _is_new_secret(incoming.api_key):
        return incoming.api_key
    if current is not None:
        return current.api_key
    return incoming.api_key


def _is_new_secret(secret: SecretStr) -> bool:
    value = secret.get_secret_value()
    return bool(value) and value != SECRET_REDACTION_PLACEHOLDER


def _save_credentials_unlocked(data: LLMCredentialsFile, credential_path: Path) -> None:
    """Atomic write without acquiring the lock; caller must hold it."""
    payload = _credentials_payload_for_storage(data)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    credential_path.parent.mkdir(parents=True, exist_ok=True)
    credential_path.parent.chmod(0o700)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{credential_path.name}.",
        suffix=".tmp",
        dir=credential_path.parent,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            tmp_file.write(serialized)
            tmp_file.write("\n")
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        tmp_path.chmod(0o600)
        os.replace(tmp_path, credential_path)
        credential_path.chmod(0o600)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _credentials_payload_for_storage(data: LLMCredentialsFile) -> dict[str, Any]:
    payload = data.model_dump(mode="json")
    for endpoint_id, endpoint in data.provider_endpoints.items():
        api_key = endpoint.api_key
        payload["provider_endpoints"][endpoint_id]["api_key"] = (
            api_key.get_secret_value() if api_key is not None else None
        )
    return payload


__all__ = [
    "_credentials_lock",
    "_save_credentials_unlocked",
    "credentials_path",
    "delete_endpoint",
    "delete_route",
    "load_credentials",
    "save_credentials",
    "serialize_for_response",
    "upsert_endpoints",
    "upsert_routes",
]
