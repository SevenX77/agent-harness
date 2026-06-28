from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from graph_agent_gateway.registry.contracts import CredentialProviderProtocol

_CREDENTIAL_NOW_DRIFT_TOLERANCE = timedelta(seconds=5)


class CredentialResolveRequest(BaseModel):
    user_id: str
    role: str
    credential_ref: str
    source: Literal["local_input", "remote_vault"]
    ttl_seconds: int = 300
    now: datetime | None = None

    model_config = ConfigDict(extra="forbid")


class CredentialResolveResponse(BaseModel):
    credential_ref: str | None = None
    secret_handle: str
    expires_at: datetime | None = None
    redacted_label: str | None = None
    fingerprint: str | None = None
    scope: str | None = None

    model_config = ConfigDict(extra="forbid")


class CredentialResolveError(Exception):
    def __init__(self, error_code: str, error_payload: dict[str, Any]) -> None:
        super().__init__(f"CredentialResolveError: {error_code} - {error_payload}")
        self.error_code = error_code
        self.error_payload = error_payload


def resolve_credential(
    request: CredentialResolveRequest,
    *,
    credential_provider: CredentialProviderProtocol,
) -> CredentialResolveResponse:
    """Resolve a credential reference into a short-lived opaque secret handle."""
    ttl_seconds = int(request.ttl_seconds)
    if ttl_seconds <= 0:
        raise CredentialResolveError("credential.invalid_ttl", {"ttl_seconds": ttl_seconds})

    now = _trusted_credential_now(request.now)
    descriptor = credential_provider.describe(request.credential_ref)
    if not descriptor.exists:
        raise CredentialResolveError(
            "credential.missing",
            {
                "credential_ref": request.credential_ref,
                "status": descriptor.status,
            },
        )

    expires_at = now + timedelta(seconds=ttl_seconds)
    return CredentialResolveResponse(
        credential_ref=request.credential_ref,
        secret_handle=_opaque_secret_handle(
            credential_ref=request.credential_ref,
            fingerprint=descriptor.fingerprint,
            scope=descriptor.scope,
            expires_at=expires_at,
        ),
        expires_at=expires_at,
        fingerprint=descriptor.fingerprint,
        scope=descriptor.scope,
    )


def _trusted_credential_now(supplied_now: datetime | None) -> datetime:
    trusted_now = datetime.now(UTC)
    if supplied_now is None:
        return trusted_now
    if supplied_now.tzinfo is None:
        supplied_now = supplied_now.replace(tzinfo=UTC)
    if abs(trusted_now - supplied_now) <= _CREDENTIAL_NOW_DRIFT_TOLERANCE:
        return supplied_now
    return trusted_now


def _opaque_secret_handle(
    *,
    credential_ref: str,
    fingerprint: str | None,
    scope: str | None,
    expires_at: datetime,
) -> str:
    seed = "|".join(
        [
            credential_ref,
            fingerprint or "",
            scope or "",
            expires_at.isoformat(),
        ]
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]
    return f"secret-handle://studio-local/{digest}"
