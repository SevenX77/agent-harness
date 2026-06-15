"""Durable storage for the LAST role/copilot test result per role.

Role-test and copilot-route-test jobs are otherwise transient (held in
in-memory job dicts in ``app.routers.llm``), so a server restart or a settings
tab remount loses every "last test result / route status". This store writes
the result of the most recently COMPLETED job per role to disk under the LLM
config dir, reusing the same atomic-write idiom as ``llm_import_drafts``, so the
badges can be re-seeded after restart.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.llm_paths import role_test_results_path

_WRITE_LOCK = threading.Lock()
logger = logging.getLogger(__name__)


def results_path() -> Path:
    """Return the durable role/copilot test-result store path."""
    return role_test_results_path()


def load_all(*, path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load every persisted role test result; missing store is empty."""
    return _load_all(path or results_path())


def load_result(role_name: str, *, path: Path | None = None) -> dict[str, Any] | None:
    """Return one persisted role test result or ``None``."""
    return _load_all(path or results_path()).get(role_name)


def save_result(
    role_name: str,
    result: dict[str, Any],
    *,
    status: str,
    message: str | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    """Persist the LAST completed test result for one role, keyed by name."""
    store_path = path or results_path()
    entry: dict[str, Any] = {
        "role_name": role_name,
        "status": status,
        "message": message,
        "result": result,
        "updated_at": _now_iso(),
    }
    with _WRITE_LOCK:
        results = _load_all(store_path)
        results[role_name] = entry
        _save_all(store_path, results)
    logger.info(
        "role_test_results action=persist role=%s status=%s", role_name, status
    )
    return entry


def _load_all(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"role test result store must contain an object: {path}")
    raw_results = payload.get("results", payload)
    if not isinstance(raw_results, dict):
        raise ValueError(f"role test result store results must be an object: {path}")
    return {
        str(role_name): entry
        for role_name, entry in raw_results.items()
        if isinstance(entry, dict)
    }


def _save_all(path: Path, results: dict[str, dict[str, Any]]) -> None:
    payload = {"results": dict(sorted(results.items()))}
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
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


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


__all__ = [
    "load_all",
    "load_result",
    "results_path",
    "save_result",
]
