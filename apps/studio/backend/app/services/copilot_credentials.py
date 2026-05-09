"""Local credential storage for Studio Copilot backends."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

CopilotBackend = Literal["claude", "deepseek", "gemini", "openai"]

_WRITE_LOCK = threading.Lock()


class BackendCredentials(BaseModel):
    """Credential payload for one Copilot backend."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    api_key: str = ""
    v1_5_placeholder: bool = Field(
        False,
        validation_alias=AliasChoices("v1_5_placeholder", "V1_5_PLACEHOLDER"),
        serialization_alias="V1_5_PLACEHOLDER",
    )


class CredentialsData(BaseModel):
    """Credential file schema stored at ``~/.studio/copilot.json``."""

    model_config = ConfigDict(extra="forbid")

    backends: dict[CopilotBackend, BackendCredentials]
    active_backend: CopilotBackend


def credentials_path() -> Path:
    """Return the local Studio Copilot credentials path."""

    return Path.home() / ".studio" / "copilot.json"


def default_credentials() -> CredentialsData:
    """Return the safe default credential config."""

    return CredentialsData(
        backends={
            "claude": BackendCredentials(api_key="", v1_5_placeholder=False),
            "deepseek": BackendCredentials(api_key="", v1_5_placeholder=False),
            "gemini": BackendCredentials(api_key="", v1_5_placeholder=True),
            "openai": BackendCredentials(api_key="", v1_5_placeholder=True),
        },
        active_backend="claude",
    )


def read_credentials() -> CredentialsData:
    """Read credentials from disk, returning defaults if the file is absent."""

    path = credentials_path()
    if not path.exists():
        return default_credentials()
    return CredentialsData.model_validate_json(path.read_text(encoding="utf-8"))


def write_credentials(data: CredentialsData) -> None:
    """Atomically write credentials and force file permissions to ``0600``."""

    path = credentials_path()
    payload = data.model_dump(mode="json", by_alias=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)

    with _WRITE_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.parent.chmod(0o700)
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                tmp_file.write(serialized)
                tmp_file.write("\n")
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
            tmp_path.chmod(0o600)
            os.replace(tmp_path, path)
            path.chmod(0o600)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()


__all__ = [
    "BackendCredentials",
    "CopilotBackend",
    "CredentialsData",
    "credentials_path",
    "default_credentials",
    "read_credentials",
    "write_credentials",
]
