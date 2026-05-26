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
    ProviderTestResult,
    TestStatus,
)
from app.services.migrations import migrate_credentials_payload

_WRITE_LOCK = threading.Lock()
_credentials_lock = _WRITE_LOCK
MAX_TEST_RESULT_CACHE_SIZE = 20


def credentials_path() -> Path:
    """Return the local Studio LLM credentials path."""

    return Path.home() / ".studio" / "llm_credentials.json"


def load_credentials(path: Path | None = None) -> LLMCredentialsFile:
    """Read LLM credentials, returning an empty v3 file if absent or stale."""

    credential_path = path or credentials_path()
    if not credential_path.exists():
        return LLMCredentialsFile()
    try:
        payload = json.loads(credential_path.read_text(encoding="utf-8"))
        return LLMCredentialsFile.model_validate(migrate_credentials_payload(payload))
    except ValidationError:
        return LLMCredentialsFile()
    except json.JSONDecodeError:
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

    return {"providers": [provider.model_dump(mode="json") for provider in data.providers]}


def _persist_test_outcome(
    provider_id: str,
    *,
    last_test_status: TestStatus,
    last_test_at: str,
    last_test_message: str = "",
    last_error_code: str = "",
    available_sdks: list[str] | None = None,
    available_models: list[ModelInfo] | None = None,
    expected_api_key: str | None = None,
    expected_base_url: str | None = None,
    expected_provider_type: str | None = None,
    path: Path | None = None,
) -> ProviderCredential | None:
    """Atomically patch only the Test outcome fields on one provider.

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
        target_api_key = existing.api_key if expected_api_key is None else expected_api_key
        target_base_url = existing.base_url if expected_base_url is None else expected_base_url
        target_provider_type = (
            existing.provider_type if expected_provider_type is None else expected_provider_type
        )
        test_result = ProviderTestResult(
            params_fingerprint=provider_test_params_fingerprint(
                api_key=target_api_key,
                base_url=target_base_url,
                provider_type=target_provider_type,
            ),
            base_url=target_base_url,
            provider_type=target_provider_type,  # type: ignore[arg-type]
            last_test_status=last_test_status,
            last_test_at=last_test_at,
            last_test_message=last_test_message,
            last_error_code=last_error_code,
            available_sdks=sdks,
            available_models=models,
        )
        test_results = upsert_provider_test_result(existing.test_results, test_result)
        updated_fields: dict[str, Any] = {
            "test_results": test_results,
        }
        if _provider_matches_expected_test_params(
            existing,
            expected_api_key=target_api_key,
            expected_base_url=target_base_url,
            expected_provider_type=target_provider_type,
        ):
            updated_fields.update(test_outcome_values_from_result(test_result))
        updated = existing.model_copy(update=updated_fields)
        data.providers = [
            updated if provider.id == provider_id else provider for provider in data.providers
        ]
        _save_credentials_unlocked(data, credential_path)
        return updated


def provider_test_params_fingerprint(
    *,
    api_key: str,
    base_url: str | None,
    provider_type: str | None,
) -> str:
    payload = json.dumps(
        {
            "api_key": api_key or "",
            "base_url": base_url or "",
            "provider_type": provider_type or None,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return _fnv1a_32(payload)


def provider_current_test_result(provider: ProviderCredential) -> ProviderTestResult | None:
    if not provider_has_test_outcome(provider):
        return None
    return ProviderTestResult(
        params_fingerprint=provider_test_params_fingerprint(
            api_key=provider.api_key,
            base_url=provider.base_url,
            provider_type=provider.provider_type,
        ),
        base_url=provider.base_url or "",
        provider_type=provider.provider_type,
        last_test_status=provider.last_test_status,
        last_test_at=provider.last_test_at,
        last_test_message=provider.last_test_message,
        last_error_code=provider.last_error_code,
        available_sdks=list(provider.available_sdks),
        available_models=list(provider.available_models),
    )


def provider_has_test_outcome(provider: ProviderCredential) -> bool:
    return (
        provider.last_test_status != "untested"
        or bool(provider.last_test_at)
        or bool(provider.last_test_message)
        or bool(provider.last_error_code)
        or bool(provider.available_sdks)
        or bool(provider.available_models)
    )


def find_provider_test_result(
    test_results: list[ProviderTestResult],
    *,
    api_key: str,
    base_url: str | None,
    provider_type: str | None,
) -> ProviderTestResult | None:
    fingerprint = provider_test_params_fingerprint(
        api_key=api_key,
        base_url=base_url,
        provider_type=provider_type,
    )
    for result in reversed(test_results):
        if result.params_fingerprint == fingerprint:
            return result
    return None


def upsert_provider_test_result(
    test_results: list[ProviderTestResult],
    result: ProviderTestResult | None,
) -> list[ProviderTestResult]:
    if result is None:
        return list(test_results)
    next_results = [
        item for item in test_results if item.params_fingerprint != result.params_fingerprint
    ]
    next_results.append(result)
    return next_results[-MAX_TEST_RESULT_CACHE_SIZE:]


def test_outcome_values_from_result(result: ProviderTestResult) -> dict[str, Any]:
    return {
        "last_test_status": result.last_test_status,
        "last_test_at": result.last_test_at,
        "last_test_message": result.last_test_message,
        "last_error_code": result.last_error_code,
        "available_sdks": list(result.available_sdks),
        "available_models": list(result.available_models),
    }


def _fnv1a_32(value: str) -> str:
    hash_value = 0x811C9DC5
    for char in value:
        hash_value ^= ord(char)
        hash_value = (hash_value * 0x01000193) & 0xFFFFFFFF
    return f"{hash_value:08x}"


def _provider_matches_expected_test_params(
    provider: ProviderCredential,
    *,
    expected_api_key: str | None,
    expected_base_url: str | None,
    expected_provider_type: str | None,
) -> bool:
    if expected_api_key is not None and provider.api_key != expected_api_key:
        return False
    if expected_base_url is not None and (provider.base_url or "") != expected_base_url:
        return False
    if (
        expected_provider_type is not None
        and (provider.provider_type or None) != expected_provider_type
    ):
        return False
    return True


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
    "find_provider_test_result",
    "load_credentials",
    "provider_current_test_result",
    "provider_test_params_fingerprint",
    "save_credentials",
    "serialize_for_response",
    "test_outcome_values_from_result",
    "upsert_provider_test_result",
]
