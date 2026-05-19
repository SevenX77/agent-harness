"""Local credential storage for Studio LLM providers."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.models.llm_config import (
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
    """Read LLM credentials, returning an empty v3 file if absent or stale."""

    credential_path = path or credentials_path()
    if not credential_path.exists():
        return LLMCredentialsFile()
    try:
        return LLMCredentialsFile.model_validate_json(credential_path.read_text(encoding="utf-8"))
    except ValidationError:
        return LLMCredentialsFile()


def save_credentials(data: LLMCredentialsFile, path: Path | None = None) -> None:
    """Atomically write credentials and force file permissions to ``0600``."""

    credential_path = path or credentials_path()
    with _credentials_lock:
        _save_credentials_unlocked(data, credential_path)


def serialize_for_response(
    data: LLMCredentialsFile,
    provider_metadata: dict[str, dict[str, Any]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Return credentials suitable for API responses."""

    del provider_metadata

    return {
        "providers": [
            provider.model_dump(mode="json")
            for provider in data.providers
        ]
    }


def _persist_test_outcome(
    provider_id: str,
    *,
    last_test_status: TestStatus,
    last_test_at: str,
    last_test_message: str = "",
    last_error_code: str = "",
    available_sdks: list[str] | None = None,
    available_models: list[ModelInfo] | None = None,
    path: Path | None = None,
) -> ProviderCredential | None:
    """Atomically patch only the 5 Test outcome fields on one provider.

    Other fields (api_key, base_url, name, provider_type) are
    untouched. Returns the updated credential or ``None`` if the provider
    is not present in storage (silently no-op).

    This shares ``_credentials_lock`` with ``save_credentials`` so that a
    concurrent PUT does not lose Test writeback or vice versa.
    """

    credential_path = path or credentials_path()
    sdks = list(available_sdks or [])
    models = list(available_models or [])

    with _credentials_lock:
        data = load_credentials(credential_path)
        existing = next(
            (provider for provider in data.providers if provider.id == provider_id),
            None,
        )
        if existing is None:
            return None
        updated_fields: dict[str, Any] = {
            "last_test_status": last_test_status,
            "last_test_at": last_test_at,
            "last_test_message": last_test_message,
            "last_error_code": last_error_code,
            "available_sdks": sdks,
            "available_models": models,
        }
        updated = existing.model_copy(update=updated_fields)
        data.providers = [
            updated if provider.id == provider_id else provider
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
    "save_credentials",
    "serialize_for_response",
]
