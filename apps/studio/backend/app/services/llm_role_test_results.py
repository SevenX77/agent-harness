"""Durable storage for the LAST role/copilot test result per role.

Role-test and copilot-route-test jobs are otherwise transient (held in
in-memory job dicts in ``app.routers.llm``), so a server restart or a settings
tab remount loses every "last test result / route status". This store writes
the result of the most recently COMPLETED job per role to disk under the LLM
config dir using an atomic temp-file-then-replace write, so the badges can be
re-seeded after restart.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.adapters.atomic_file import read_published_text, write_text_atomically
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
    payload = json.loads(read_published_text(path))
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
    write_text_atomically(path, serialized + "\n")


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


__all__ = [
    "load_all",
    "load_result",
    "results_path",
    "save_result",
]
