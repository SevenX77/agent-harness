"""Server-side predict-pass record that gates the Run prerequisite.

Per MVP1 run-and-verify workflow, ``predict-pass`` unlocks Run. The UI used to
enforce this only client-side, so any non-UI caller could spawn a run without a
passing Predict. This module persists a lightweight last-predict status under a
skill's ``.workspace`` so the run-spawn path can enforce the prerequisite
server-side.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn

from app.core.exceptions import error_response, raise_error_response
from app.services.skills import resolve_skill_dir, workspace_dir_for

logger = logging.getLogger(__name__)

_LAST_PREDICT_FILENAME = "last_predict.json"


def last_predict_path_for(skill_dir: Path) -> Path:
    """Return the .workspace path of the per-skill last-predict status file."""
    return workspace_dir_for(skill_dir) / _LAST_PREDICT_FILENAME


def record_predict_pass(skill_dir: Path, skill_id: str, run_id: str, *, content_hash: str) -> Path:
    """Persist a passing predict for one skill so the run gate can consume it.

    Called only when a Predict run reports success; overwrites any prior record
    so the gate always reflects the latest predict outcome. ``content_hash`` is
    the compiled-artifact hash the predict ran against — the run gate matches it
    against the freshly-compiled hash so an edit after a pass forces a re-predict
    (predict certifies the *current* graph, not whatever last passed).
    """
    workspace_dir_for(skill_dir).mkdir(parents=True, exist_ok=True)
    record_path = last_predict_path_for(skill_dir)
    payload = {
        "skill_id": skill_id,
        "run_id": run_id,
        "success": True,
        "content_hash": content_hash,
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    record_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    logger.info(
        "predict_gate action=record skill_id=%s run_id=%s content_hash=%s path=%s",
        skill_id,
        run_id,
        content_hash,
        record_path,
    )
    return record_path


def has_passing_predict(skill_id: str, *, content_hash: str) -> bool:
    """Whether the latest recorded predict passed *for the current graph*.

    Returns ``True`` only when a success record exists AND its recorded
    ``content_hash`` equals ``content_hash`` (the freshly-compiled hash). A
    hash mismatch means the graph was edited since the last pass, so the record
    is stale and the gate must re-require predict. Records written before this
    field existed (no ``content_hash``) are treated as stale → no pass.
    """
    skill_dir = resolve_skill_dir(skill_id)
    record_path = last_predict_path_for(skill_dir)
    if not record_path.exists():
        return False
    try:
        loaded = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "predict_gate action=read_failed skill_id=%s path=%s error=%s degrading=treat_as_no_pass",
            skill_id,
            record_path,
            exc,
        )
        return False
    if not (isinstance(loaded, dict) and loaded.get("success") is True):
        return False
    recorded_hash = loaded.get("content_hash")
    if recorded_hash != content_hash:
        logger.warning(
            "predict_gate action=hash_check skill_id=%s recorded=%s current=%s verdict=stale",
            skill_id,
            recorded_hash,
            content_hash,
        )
        return False
    return True


def require_passing_predict(skill_id: str, *, content_hash: str) -> None:
    """Raise RUN_REQUIRES_PREDICT unless a passing predict for the current graph is on record."""
    if has_passing_predict(skill_id, content_hash=content_hash):
        logger.info(
            "predict_gate decision=allow_run skill_id=%s content_hash=%s reason=passing_predict_on_record",
            skill_id,
            content_hash,
        )
        return
    logger.warning(
        "predict_gate decision=block_run skill_id=%s content_hash=%s reason=no_matching_passing_predict",
        skill_id,
        content_hash,
    )
    _raise_run_requires_predict(skill_id)


def _raise_run_requires_predict(skill_id: str) -> NoReturn:
    response = error_response(
        error_code="RUN_REQUIRES_PREDICT",
        http_status=409,
        message=f"Run requires a passing Predict for skill {skill_id}; predict the skill before running it",
        details={"skill_id": skill_id},
        retry_strategy="not_retryable",
    )
    raise_error_response(response)
