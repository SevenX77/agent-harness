"""Small append-only runtime activity log for Studio truth sources."""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core import config

_LOCK = threading.Lock()
_MAX_LINE_BYTES = 64 * 1024


def runtime_activity_log_path() -> Path:
    """Return the append-only log used by the General settings diagnostics."""
    override = os.environ.get("STUDIO_RUNTIME_ACTIVITY_LOG_PATH")
    if override:
        return Path(override).expanduser()
    return config.app_settings_dir(os.environ) / "logs" / "studio_runtime_activity.jsonl"


def record_runtime_activity(
    *,
    source_id: str,
    action: str,
    message: str,
    changes: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one structured activity event and return the event."""
    now = datetime.now().astimezone()
    entry: dict[str, Any] = {
        "id": str(uuid4()),
        "recorded_at": now.isoformat(timespec="seconds"),
        "source_id": source_id,
        "action": action,
        "message": message,
        "changes": dict(changes or {}),
    }
    line = json.dumps(entry, ensure_ascii=False, sort_keys=True)
    if len(line.encode("utf-8")) > _MAX_LINE_BYTES:
        entry["changes"] = {"truncated": True}
        line = json.dumps(entry, ensure_ascii=False, sort_keys=True)

    path = runtime_activity_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.write("\n")
    return entry


def load_runtime_activity(
    *,
    source_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Load the newest runtime activity events, optionally scoped to one source."""
    path = runtime_activity_log_path()
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        if source_id is not None and entry.get("source_id") != source_id:
            continue
        entries.append(entry)
        if len(entries) >= limit:
            break
    return entries


__all__ = [
    "load_runtime_activity",
    "record_runtime_activity",
    "runtime_activity_log_path",
]
