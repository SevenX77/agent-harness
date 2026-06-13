from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class CredentialResolveRequest(BaseModel):
    user_id: str
    role: str
    credential_ref: str
    source: Literal["local_input", "remote_vault"]

    model_config = ConfigDict(extra="forbid")


class CredentialResolveResponse(BaseModel):
    secret_handle: str
    expires_at: datetime | None = None
    redacted_label: str | None = None

    model_config = ConfigDict(extra="forbid")


class CredentialResolveError(Exception):
    def __init__(self, error_code: str, error_payload: dict[str, Any]) -> None:
        super().__init__(f"CredentialResolveError: {error_code} - {error_payload}")
        self.error_code = error_code
        self.error_payload = error_payload
