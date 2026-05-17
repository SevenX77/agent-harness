"""Local credential storage for Studio LLM providers."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from app.models.llm_config import LLMCredentialsFile

_WRITE_LOCK = threading.Lock()


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
    payload = data.model_dump(mode="json")
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)

    with _WRITE_LOCK:
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
            providers.append(
                {
                    **metadata,
                    "provider_code": provider_code,
                    "has_key": bool(credential and credential.api_key.strip()),
                    "base_url": saved_base_url or metadata.get("base_url", ""),
                }
            )
        return {"providers": providers}

    return {
        "providers": [
            {
                "provider_code": provider.provider_code,
                "has_key": bool(provider.api_key.strip()),
                "base_url": provider.base_url,
            }
            for provider in data.providers
        ]
    }


__all__ = [
    "credentials_path",
    "load_credentials",
    "redacted_for_response",
    "save_credentials",
]
