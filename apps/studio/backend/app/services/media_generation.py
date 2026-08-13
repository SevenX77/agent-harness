"""Media generation provider truth: file-backed store, registry view, probe.

The gateway ``media`` domain owns the schema/catalog/probe logic; this module
is the host-side storage provider (same injection pattern as the LLM registry)
plus the merged view the ``/api/media`` router serves.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.core import config
from app.core.adapters.media_gateway import (
    MediaModelSettings,
    MediaProbeResult,
    MediaProviderCredential,
    probe_runninghub_account,
    runninghub_catalog,
)

MEDIA_PROVIDER_ID = "runninghub"
_MEDIA_SETTINGS_DIR = "media"
_DEFAULT_BASE_URL = "https://www.runninghub.cn"


def media_generation_path() -> Path:
    override = os.environ.get("STUDIO_MEDIA_GENERATION_PATH")
    if override:
        return Path(override).expanduser()
    return config.APP_SETTINGS_DIR / _MEDIA_SETTINGS_DIR / "media_generation.json"


class MediaProviderFileState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: str = ""
    base_url: str = _DEFAULT_BASE_URL
    last_probe: MediaProbeResult | None = None
    model_settings: dict[str, MediaModelSettings] = Field(default_factory=dict)


class MediaFileState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    providers: dict[str, MediaProviderFileState] = Field(default_factory=dict)


def load_state(path: Path | None = None) -> MediaFileState:
    state_path = path or media_generation_path()
    if not state_path.exists():
        return MediaFileState(providers={MEDIA_PROVIDER_ID: MediaProviderFileState()})
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    state = MediaFileState.model_validate(payload)
    state.providers.setdefault(MEDIA_PROVIDER_ID, MediaProviderFileState())
    return state


def save_state(state: MediaFileState, path: Path | None = None) -> None:
    state_path = path or media_generation_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = state_path.with_suffix(".tmp")
    temp_path.write_text(
        json.dumps(state.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(state_path)


def gateway_credential(provider: MediaProviderFileState) -> MediaProviderCredential:
    return MediaProviderCredential(
        api_key=SecretStr(provider.api_key), base_url=provider.base_url
    )


async def run_account_probe(provider: MediaProviderFileState) -> MediaProbeResult:
    return await probe_runninghub_account(gateway_credential(provider))


def registry_view(state: MediaFileState) -> dict[str, Any]:
    provider = state.providers[MEDIA_PROVIDER_ID]
    models: list[dict[str, Any]] = []
    for spec in runninghub_catalog():
        settings = provider.model_settings.get(spec.id, MediaModelSettings())
        entry = spec.model_dump(mode="json")
        entry["settings"] = settings.model_dump(mode="json")
        models.append(entry)
    return {
        "providers": [
            {
                "id": MEDIA_PROVIDER_ID,
                "base_url": provider.base_url,
                "api_key_set": bool(provider.api_key),
                "last_probe": (
                    provider.last_probe.model_dump(mode="json")
                    if provider.last_probe
                    else None
                ),
            }
        ],
        "models": models,
    }
