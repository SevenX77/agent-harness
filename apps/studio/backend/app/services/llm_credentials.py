"""Local v4 endpoint/route registry storage for Studio LLM credentials."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import SecretStr, ValidationError

from app.core.adapters.gateway import (
    CapabilitySource,
    canonicalize_base_url,
    canonicalize_model,
    normalize_route_capabilities,
)
from app.models.llm_config import LLMCredentialsFile, ProviderEndpoint, ProviderRoute
from app.services.llm_paths import credentials_path
from graph_agent_gateway.registry.route_identity import (
    route_slug as identity_route_slug,
    stable_endpoint_id as url_stable_endpoint_id,
)

_WRITE_LOCK = threading.Lock()
_credentials_lock = _WRITE_LOCK
SECRET_REDACTION_PLACEHOLDER = "**********"
LEGACY_FAKE_TEST_MESSAGE = "Credential present."
LEGACY_FAKE_TEST_REPLACEMENT_MESSAGE = "Needs retest after v4 provider probe upgrade."
CATALOG_ONLY_PROBE_MESSAGE = "No verified language route profile."
CURATED_PROVIDER_KIND_BY_ENDPOINT_ID = {
    "anthropic-official": "official",
    "ark-official": "official",
    "openai-official": "official",
    "deepseek-official": "official",
    "gemini-official": "official",
}


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
        raise ValueError(f"LLM_CREDENTIALS_SCHEMA: invalid llm_credentials.json: {credential_path}") from exc
    if isinstance(payload, dict) and (payload.get("schema_version") != 4 or "providers" in payload):
        raise ValueError(
            f"LLM_CREDENTIALS_SCHEMA: llm_credentials.json must use schema_version 4; "
            f"legacy provider credentials are rejected: {credential_path}"
        )
    try:
        return _normalize_loaded_credentials(LLMCredentialsFile.model_validate(payload))
    except ValidationError as exc:
        raise ValueError(f"LLM_CREDENTIALS_SCHEMA: invalid v4 llm credentials schema: {credential_path}") from exc


def save_credentials(data: LLMCredentialsFile, path: Path | None = None) -> None:
    """Atomically write credentials and force file permissions to ``0600``."""
    credential_path = path or credentials_path()
    from app.services.file_watcher import record_api_write

    try:
        record_api_write(credential_path)
    except Exception:
        pass
    with _credentials_lock:
        _save_credentials_unlocked(data, credential_path)


def migrate_v3_credentials_to_v4(path: Path | None = None) -> LLMCredentialsFile:
    """Convert a legacy Studio v3 credentials file into the v4 route registry.

    The migration is explicit, creates a sibling backup first, preserves
    secrets, and writes the v4 file atomically through the normal storage path.
    """
    credential_path = path or credentials_path()
    payload = json.loads(credential_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 3:
        raise ValueError(f"expected schema_version 3 credentials: {credential_path}")

    backup_path = _next_backup_path(credential_path)
    shutil.copy2(credential_path, backup_path)
    backup_path.chmod(0o600)

    migrated = _v3_payload_to_v4(payload)
    save_credentials(migrated, credential_path)
    return migrated


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
            incoming = _endpoint_from_payload(_endpoint_authoring_payload(payload))
            canonical_base_url = canonicalize_base_url(incoming.base_url, incoming.protocol)
            persisted_endpoint_id = _persisted_endpoint_id(
                endpoint_id=endpoint_id,
                endpoint=incoming,
                canonical_base_url=canonical_base_url,
            )
            current = endpoints.get(persisted_endpoint_id) or endpoints.get(endpoint_id)
            api_key = _preserved_secret(incoming, current)
            updates: dict[str, Any] = {
                "endpoint_id": persisted_endpoint_id,
                "api_key": api_key,
                "base_url": canonical_base_url,
                "status": current.status if current is not None else "unverified_manual",
                "last_test_at": current.last_test_at if current is not None else None,
                "last_test_message": current.last_test_message if current is not None else None,
            }
            curated_provider_kind = CURATED_PROVIDER_KIND_BY_ENDPOINT_ID.get(persisted_endpoint_id)
            if curated_provider_kind is not None and _field_omitted(payload, "provider_kind"):
                updates["provider_kind"] = curated_provider_kind
            elif current is None:
                updates["provider_kind"] = _seeded_provider_kind(persisted_endpoint_id, incoming, payload)
            elif _field_omitted(payload, "provider_kind"):
                updates["provider_kind"] = current.provider_kind
            if current is not None and _field_omitted(payload, "rate_limit_bucket"):
                updates["rate_limit_bucket"] = current.rate_limit_bucket
            if current is not None and _field_omitted(payload, "credential_ref"):
                updates["credential_ref"] = current.credential_ref
            if persisted_endpoint_id != endpoint_id:
                endpoints.pop(endpoint_id, None)
            endpoints[persisted_endpoint_id] = incoming.model_copy(update=updates)
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
            route_id: route for route_id, route in data.provider_routes.items() if route.endpoint_id != endpoint_id
        }
        data = data.model_copy(update={"provider_endpoints": endpoints, "provider_routes": routes})
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
            if isinstance(payload, ProviderRoute):
                route = payload
            else:
                route = ProviderRoute.model_validate(payload)
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
    return ProviderEndpoint.model_validate(payload)


def _endpoint_authoring_payload(payload: dict[str, Any] | ProviderEndpoint) -> dict[str, Any] | ProviderEndpoint:
    fact_fields = {"status", "last_test_at", "last_test_message"}
    if isinstance(payload, dict):
        return {key: value for key, value in payload.items() if key not in fact_fields}
    return payload.model_copy(
        update={
            "status": "unverified_manual",
            "last_test_at": None,
            "last_test_message": None,
        }
    )


def _field_omitted(payload: dict[str, Any] | ProviderEndpoint, field_name: str) -> bool:
    if isinstance(payload, dict):
        return field_name not in payload
    return field_name not in payload.model_fields_set


def _seeded_provider_kind(
    endpoint_id: str,
    incoming: ProviderEndpoint,
    payload: dict[str, Any] | ProviderEndpoint,
) -> str:
    if not _field_omitted(payload, "provider_kind"):
        return incoming.provider_kind
    return CURATED_PROVIDER_KIND_BY_ENDPOINT_ID.get(endpoint_id, "third_party")


def _persisted_endpoint_id(
    *,
    endpoint_id: str,
    endpoint: ProviderEndpoint,
    canonical_base_url: str,
) -> str:
    official_endpoint_id = _official_endpoint_id_for_base_url(canonical_base_url)
    if official_endpoint_id is not None:
        return official_endpoint_id
    if endpoint_id in CURATED_PROVIDER_KIND_BY_ENDPOINT_ID:
        return endpoint_id
    return url_stable_endpoint_id(protocol=endpoint.protocol, base_url=canonical_base_url)


def _official_endpoint_id_for_base_url(base_url: str) -> str | None:
    base_host = _url_hostname(base_url)
    if base_host == "api.anthropic.com":
        return "anthropic-official"
    if base_host == "api.openai.com":
        return "openai-official"
    if base_host == "api.deepseek.com":
        return "deepseek-official"
    if base_host == "generativelanguage.googleapis.com":
        return "gemini-official"
    if _host_matches(base_host, "volces.com"):
        return "ark-official"
    return None


def _normalize_loaded_credentials(data: LLMCredentialsFile) -> LLMCredentialsFile:
    return _repair_catalog_candidate_route_statuses(
        _repair_curated_provider_kinds(_invalidate_legacy_fake_test_statuses(data))
    )


def _repair_curated_provider_kinds(data: LLMCredentialsFile) -> LLMCredentialsFile:
    endpoints = {}
    changed = False
    for endpoint_id, endpoint in data.provider_endpoints.items():
        curated_provider_kind = CURATED_PROVIDER_KIND_BY_ENDPOINT_ID.get(endpoint_id)
        if curated_provider_kind is not None and endpoint.provider_kind != curated_provider_kind:
            endpoints[endpoint_id] = endpoint.model_copy(update={"provider_kind": curated_provider_kind})
            changed = True
        else:
            endpoints[endpoint_id] = endpoint
    if not changed:
        return data
    return data.model_copy(update={"provider_endpoints": endpoints})


def _invalidate_legacy_fake_test_statuses(data: LLMCredentialsFile) -> LLMCredentialsFile:
    endpoints = {}
    changed = False
    for endpoint_id, endpoint in data.provider_endpoints.items():
        if endpoint.status == "verified" and endpoint.last_test_message == LEGACY_FAKE_TEST_MESSAGE:
            endpoints[endpoint_id] = endpoint.model_copy(
                update={
                    "status": "unverified_manual",
                    "last_test_message": LEGACY_FAKE_TEST_REPLACEMENT_MESSAGE,
                }
            )
            changed = True
        else:
            endpoints[endpoint_id] = endpoint
    if not changed:
        return data
    return data.model_copy(update={"provider_endpoints": endpoints})


def _repair_catalog_candidate_route_statuses(data: LLMCredentialsFile) -> LLMCredentialsFile:
    endpoints = {}
    changed = False
    for endpoint_id, endpoint in data.provider_endpoints.items():
        library = endpoint.metadata.get("capability_library")
        if not isinstance(library, list):
            endpoints[endpoint_id] = endpoint
            continue
        next_library = []
        endpoint_changed = False
        for entry in library:
            if (
                isinstance(entry, dict)
                and entry.get("status") == "catalog_candidate"
                and entry.get("route_status") == "failed"
                and entry.get("last_probe_message") == CATALOG_ONLY_PROBE_MESSAGE
            ):
                next_library.append({**entry, "route_status": "unverified_manual"})
                endpoint_changed = True
            else:
                next_library.append(entry)
        if endpoint_changed:
            endpoints[endpoint_id] = endpoint.model_copy(
                update={
                    "metadata": {
                        **endpoint.metadata,
                        "capability_library": next_library,
                    }
                }
            )
            changed = True
        else:
            endpoints[endpoint_id] = endpoint
    if not changed:
        return data
    return data.model_copy(update={"provider_endpoints": endpoints})


def _v3_payload_to_v4(payload: dict[str, Any]) -> LLMCredentialsFile:
    endpoints: dict[str, ProviderEndpoint] = {}
    routes: dict[str, ProviderRoute] = {}
    for provider in payload.get("providers") or []:
        if not isinstance(provider, dict):
            continue
        endpoint_id = _stable_endpoint_id(provider)
        protocol = provider.get("provider_type") or provider.get("type")
        base_url = str(provider.get("base_url") or "").strip()
        supported_protocols = {
            "anthropic_compatible",
            "openai_compatible",
            "google_genai",
            "ark_runtime",
        }
        if not endpoint_id or protocol not in supported_protocols:
            continue
        canonical_url = canonicalize_base_url(base_url, protocol)
        endpoint = ProviderEndpoint(
            endpoint_id=endpoint_id,
            display_name=str(provider.get("name") or endpoint_id),
            protocol=protocol,
            base_url=canonical_url,
            api_key=provider.get("api_key") or None,
            status="verified" if provider.get("last_test_status") == "ok" else "unverified_manual",
            last_test_at=provider.get("last_test_at"),
            last_test_message=provider.get("last_test_message") or None,
        )
        endpoints[endpoint_id] = endpoint
        capability_source: CapabilitySource = (
            "probed_verified" if provider.get("last_test_status") == "ok" else "api_list"
        )
        for model in _legacy_models(provider):
            model_id = str(model.get("id") or "").strip()
            if not model_id:
                continue
            raw_capabilities = model.get("capabilities")
            if not isinstance(raw_capabilities, dict):
                raw_capabilities = {}
            route_slug = _route_slug(model_id)
            canonical = canonicalize_model(endpoint_id=endpoint_id, provider_model_id=route_slug)
            route_id = f"{endpoint_id}:{route_slug}"
            routes[route_id] = ProviderRoute(
                route_id=route_id,
                endpoint_id=endpoint_id,
                route_slug=route_slug,
                provider_model_id=model_id,
                canonical_id=canonical.canonical_id,
                display_name=str(raw_capabilities.get("display_name") or model_id),
                status=endpoint.status,
                capabilities=normalize_route_capabilities(
                    protocol=endpoint.protocol,
                    provider_model_id=model_id,
                    raw_capabilities=raw_capabilities,
                    source=capability_source,
                ),
                metadata={"legacy_migrated_from": "schema_version_3"},
            )
    return LLMCredentialsFile(provider_endpoints=endpoints, provider_routes=routes)


def _legacy_models(provider: dict[str, Any]) -> list[dict[str, Any]]:
    models = provider.get("available_models")
    if isinstance(models, list):
        return [item for item in models if isinstance(item, dict)]
    models = provider.get("models")
    if isinstance(models, list):
        return [item for item in models if isinstance(item, dict)]
    return []


def _stable_endpoint_id(provider: dict[str, Any]) -> str:
    raw = str(provider.get("id") or provider.get("code") or "").strip()
    base_url = str(provider.get("base_url") or "").strip()
    protocol = provider.get("provider_type") or provider.get("type")
    if protocol not in {"anthropic_compatible", "openai_compatible", "google_genai", "ark_runtime"}:
        return raw
    canonical_base_url = canonicalize_base_url(base_url, protocol)
    official_endpoint_id = _official_endpoint_id_for_base_url(canonical_base_url)
    if official_endpoint_id is not None:
        return official_endpoint_id
    if raw in CURATED_PROVIDER_KIND_BY_ENDPOINT_ID:
        return raw
    if base_url:
        return url_stable_endpoint_id(protocol=protocol, base_url=canonical_base_url)
    return raw


def _url_hostname(raw_url: str) -> str:
    if not raw_url:
        return ""
    parsed = urlparse(raw_url if "://" in raw_url else f"https://{raw_url}")
    return (parsed.hostname or "").lower().rstrip(".")


def _host_matches(hostname: str, domain: str) -> bool:
    normalized_domain = domain.lower().rstrip(".")
    return hostname == normalized_domain or hostname.endswith(f".{normalized_domain}")


def _route_slug(provider_model_id: str) -> str:
    return identity_route_slug(provider_model_id)


def _next_backup_path(path: Path) -> Path:
    backup = path.with_name(f"{path.name}.v3.bak")
    if not backup.exists():
        return backup
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return path.with_name(f"{path.name}.v3.{stamp}.bak")


def _preserved_secret(
    incoming: ProviderEndpoint,
    current: ProviderEndpoint | None,
) -> SecretStr | None:
    if incoming.api_key is not None and incoming.api_key.get_secret_value() == "":
        return None
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
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False)
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
    "migrate_v3_credentials_to_v4",
    "save_credentials",
    "serialize_for_response",
    "upsert_endpoints",
    "upsert_routes",
]
