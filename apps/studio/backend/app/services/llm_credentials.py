"""Local credential storage for Studio LLM providers."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from app.models.llm_config import (
    TEST_OUTCOME_FIELDS,
    LLMCredentialsFile,
    ModelInfo,
    ProviderCredential,
    TestStatus,
)

_WRITE_LOCK = threading.Lock()
_credentials_lock = _WRITE_LOCK


def credentials_path() -> Path:
    """Return the local Studio LLM credentials path."""

    return Path.home() / ".studio" / "llm_credentials.json"


def load_credentials(path: Path | None = None) -> LLMCredentialsFile:
    """Read LLM credentials, returning an empty v2 file if absent."""

    credential_path = path or credentials_path()
    if not credential_path.exists():
        return LLMCredentialsFile()
    return LLMCredentialsFile.model_validate_json(credential_path.read_text(encoding="utf-8"))


def save_credentials(data: LLMCredentialsFile, path: Path | None = None) -> None:
    """Atomically write credentials and force file permissions to ``0600``."""

    credential_path = path or credentials_path()
    with _credentials_lock:
        _save_credentials_unlocked(data, credential_path)


def redacted_for_response(
    data: LLMCredentialsFile,
    provider_metadata: dict[str, dict[str, Any]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Return credentials metadata suitable for API responses."""

    credentials_by_code = {provider.provider_code: provider for provider in data.providers}
    if provider_metadata is not None:
        providers: list[dict[str, Any]] = []
        for provider_code, metadata in provider_metadata.items():
            credential = credentials_by_code.get(provider_code)
            saved_base_url = credential.base_url if credential is not None else ""
            entry: dict[str, Any] = {
                **metadata,
                "provider_code": provider_code,
                "has_key": bool(credential and credential.api_key.strip()),
                "base_url": saved_base_url or metadata.get("base_url", ""),
            }
            if credential is not None:
                # Merge credential metadata, but never blank-out non-empty YAML
                # values (title/provider_type/vendor_hint may be empty on the
                # credential when the provider was added before v2.1).
                credential_view = _credential_metadata_view(credential)
                for key, value in credential_view.items():
                    if key in ("title", "provider_type", "vendor_hint") and not value:
                        entry.setdefault(key, metadata.get(key, ""))
                        continue
                    entry[key] = value
            providers.append(entry)
        return {"providers": providers}

    return {
        "providers": [
            {
                "provider_code": provider.provider_code,
                "has_key": bool(provider.api_key.strip()),
                "base_url": provider.base_url,
                **_credential_metadata_view(provider),
            }
            for provider in data.providers
        ]
    }


def _credential_metadata_view(credential: ProviderCredential) -> dict[str, Any]:
    """Return the user-visible metadata view (no secrets) for one provider."""

    return {
        "title": credential.title,
        "provider_type": credential.provider_type,
        "vendor_hint": credential.vendor_hint,
        "last_test_status": credential.last_test_status,
        "last_test_at": credential.last_test_at,
        "last_test_message": credential.last_test_message,
        "last_error_code": credential.last_error_code,
        "available_models": [model.model_dump(mode="json") for model in credential.available_models],
    }


def _persist_test_outcome(
    provider_code: str,
    *,
    last_test_status: TestStatus,
    last_test_at: str,
    last_test_message: str = "",
    last_error_code: str = "",
    available_models: list[ModelInfo] | None = None,
    path: Path | None = None,
) -> ProviderCredential | None:
    """Atomically patch only the 5 Test outcome fields on one provider.

    Other fields (api_key, base_url, title, provider_type, vendor_hint) are
    untouched. Returns the updated credential or ``None`` if the provider
    is not present in storage (silently no-op).

    This shares ``_credentials_lock`` with ``save_credentials`` so that a
    concurrent PUT does not lose Test writeback or vice versa.
    """

    credential_path = path or credentials_path()
    models = list(available_models or [])

    with _credentials_lock:
        data = load_credentials(credential_path)
        existing = next(
            (provider for provider in data.providers if provider.provider_code == provider_code),
            None,
        )
        if existing is None:
            return None
        updated_fields: dict[str, Any] = {
            "last_test_status": last_test_status,
            "last_test_at": last_test_at,
            "last_test_message": last_test_message,
            "last_error_code": last_error_code,
            "available_models": models,
        }
        updated = existing.model_copy(update=updated_fields)
        data.providers = [
            updated if provider.provider_code == provider_code else provider
            for provider in data.providers
        ]
        _save_credentials_unlocked(data, credential_path)
        return updated


def _save_credentials_unlocked(data: LLMCredentialsFile, credential_path: Path) -> None:
    """Atomic write without acquiring the lock (caller must hold it)."""

    payload = data.model_dump(mode="json")
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


__all__ = [
    "_credentials_lock",
    "_persist_test_outcome",
    "credentials_path",
    "load_credentials",
    "redacted_for_response",
    "save_credentials",
]
