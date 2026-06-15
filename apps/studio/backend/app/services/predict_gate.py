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


def record_predict_pass(skill_dir: Path, skill_id: str, run_id: str) -> Path:
    """Persist a passing predict for one skill so the run gate can consume it.

    Called only when a Predict run reports success; overwrites any prior record
    so the gate always reflects the latest predict outcome.
    """
    workspace_dir_for(skill_dir).mkdir(parents=True, exist_ok=True)
    record_path = last_predict_path_for(skill_dir)
    payload = {
        "skill_id": skill_id,
        "run_id": run_id,
        "success": True,
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    record_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    logger.info(
        "predict_gate action=record skill_id=%s run_id=%s path=%s",
        skill_id,
        run_id,
        record_path,
    )
    return record_path


def has_passing_predict(skill_id: str) -> bool:
    """Whether the latest recorded predict for this skill passed."""
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
    return isinstance(loaded, dict) and loaded.get("success") is True


def require_passing_predict(skill_id: str) -> None:
    """Raise RUN_REQUIRES_PREDICT when no passing predict is on record for the skill."""
    if has_passing_predict(skill_id):
        logger.info("predict_gate decision=allow_run skill_id=%s reason=passing_predict_on_record", skill_id)
        return
    logger.warning("predict_gate decision=block_run skill_id=%s reason=no_passing_predict", skill_id)
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
