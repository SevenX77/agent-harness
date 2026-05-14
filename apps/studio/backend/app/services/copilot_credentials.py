"""Local credential storage for Studio Copilot providers."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from pathlib import Path

from pydantic import ValidationError

from app.models.copilot import CopilotCredentials, ProviderConfig, ProviderKind

_WRITE_LOCK = threading.Lock()
logger = logging.getLogger(__name__)


def credentials_path() -> Path:
    """Return the local Studio Copilot credentials path."""

    return Path.home() / ".studio" / "copilot.json"


def default_credentials() -> CopilotCredentials:
    """Return the default v2 provider config."""

    return CopilotCredentials(
        active_provider_id="default-claude",
        providers=[
            ProviderConfig(
                id="default-claude",
                name="Claude",
                kind="anthropic",
                api_key="",
                base_url="",
                active_model_id=None,
            ),
            ProviderConfig(
                id="default-openai",
                name="OpenAI",
                kind="openai-compat",
                api_key="",
                base_url="",
                active_model_id=None,
            ),
            ProviderConfig(
                id="default-deepseek",
                name="DeepSeek",
                kind="openai-compat",
                api_key="",
                base_url="",
                active_model_id=None,
            ),
            ProviderConfig(
                id="default-gemini",
                name="Gemini",
                kind="google",
                api_key="",
                base_url="",
                active_model_id=None,
            ),
        ],
    )


def read_credentials() -> CopilotCredentials:
    """Read credentials from disk, replacing legacy files with v2 defaults."""

    path = credentials_path()
    if not path.exists():
        return default_credentials()

    raw_text = path.read_text(encoding="utf-8")
    try:
        raw_data = json.loads(raw_text)
    except json.JSONDecodeError:
        return _overwrite_legacy_defaults()

    if isinstance(raw_data, dict) and "backends" in raw_data:
        return _overwrite_legacy_defaults()

    try:
        return CopilotCredentials.model_validate(raw_data)
    except ValidationError:
        return _overwrite_legacy_defaults()


def write_credentials(data: CopilotCredentials) -> None:
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


def _overwrite_legacy_defaults() -> CopilotCredentials:
    logger.warning("legacy format detected, overwriting with v2 defaults")
    credentials = default_credentials()
    write_credentials(credentials)
    return credentials


CredentialsData = CopilotCredentials
BackendCredentials = ProviderConfig

__all__ = [
    "BackendCredentials",
    "CopilotCredentials",
    "CredentialsData",
    "ProviderConfig",
    "ProviderKind",
    "credentials_path",
    "default_credentials",
    "read_credentials",
    "write_credentials",
]
