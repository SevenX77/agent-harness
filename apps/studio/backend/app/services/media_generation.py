"""Media generation provider truth: file-backed store, registry view, probe.

The gateway ``media`` domain owns the schema/catalog/probe logic; this module
is the host-side storage provider (same injection pattern as the LLM registry)
plus the merged view the ``/api/media`` router serves.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.core import config
from app.core.adapters.atomic_file import read_published_text, write_text_atomically
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
    # Read through the same publishing contract the writer uses. On Windows a
    # handle opened without FILE_SHARE_DELETE refuses the publisher's rename, so
    # an ordinary `read_text` here would make a well-timed read fail an unrelated
    # write — the reader must share delete for the pair to hold.
    payload = json.loads(read_published_text(state_path))
    state = MediaFileState.model_validate(payload)
    state.providers.setdefault(MEDIA_PROVIDER_ID, MediaProviderFileState())
    return state


# One writer at a time for this file WITHIN THIS PROCESS, mirroring
# `llm_credentials._WRITE_LOCK`. It guards the whole read-modify-write, because
# that is the unit that has to be atomic: every write here rewrites the WHOLE
# document, so two writers that each read before the other wrote will each save a
# document in which the other's change never happened.
#
# What it does NOT cover: two sidecar processes pointed at the same settings
# directory. They would still interleave, and neither this store nor the
# credentials store guards against that today — closing it needs a cross-process
# lock or a compare-and-swap on file identity, which is a decision for both
# stores at once rather than a thing to invent here for one of them.
_WRITE_LOCK = threading.Lock()


def _save_state_unlocked(state: MediaFileState, path: Path | None = None) -> None:
    """Write the state without taking the lock; the caller must hold it."""
    state_path = path or media_generation_path()
    # Only a directory this call CREATES gets its mode set. The path is
    # caller-supplied (argument or `STUDIO_MEDIA_GENERATION_PATH`), so it can name
    # a directory that already exists and belongs to someone else — re-permissioning
    # that would silently lock unrelated files away from unrelated processes. Same
    # rule `ssh-keygen` follows: it creates `~/.ssh` as 0700 and leaves an existing
    # one alone. The FILE's own confidentiality does not depend on this either way:
    # `write_text_atomically` publishes through `mkstemp`, which creates
    # owner-only, and the rename carries that mode over.
    parent = state_path.parent
    if not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)
        parent.chmod(0o700)
    write_text_atomically(
        state_path,
        json.dumps(state.model_dump(mode="json"), ensure_ascii=False, indent=2),
    )


@contextmanager
def locked_state(path: Path | None = None) -> Iterator[MediaFileState]:
    """Read, let the caller change, and write back — as ONE critical section.

    Every mutation of this file is a read-modify-write, and the three steps are
    only safe together: the document is rewritten whole, so a reader that loads
    before another writer's save will erase that save when it writes its own copy
    back. This is the ONLY way to write the file — there is deliberately no
    "save this state I assembled earlier" entry point, because such a call is
    exactly the stale-snapshot overwrite this exists to prevent.

    An exception from the body propagates and nothing is written, which is what a
    rejected edit needs (validation refuses the change after the state object has
    already been mutated in memory, and that in-memory edit must not reach disk).
    A body that returns normally always publishes, even when it changed nothing —
    there is no dirty tracking, so a no-op edit republishes an identical document.

    The state handed out is the whole mutable document, so cross-field rules
    (retiring a probe when its credential moves, say) live with their callers
    rather than being enforced here. That is the smallest thing that works for
    four call sites in one router; the moment a second module writes this file,
    those rules belong in domain-level mutations instead.

    The lock is not reentrant and is held across the whole body, so the body must
    not perform slow or awaiting work — see `probe_media_provider` for the shape
    that belongs here: do the outside call first, then take the lock only to merge
    its result.
    """
    with _WRITE_LOCK:
        state = load_state(path)
        yield state
        _save_state_unlocked(state, path)


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
