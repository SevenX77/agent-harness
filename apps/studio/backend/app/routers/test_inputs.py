"""Test input CRUD endpoints (INPUT-3: io-panel-artifacts-test-inputs).

Stores each named test input as one JSON file under the skill's
`.workspace/test_inputs/`. The list endpoint projects file metadata; create
writes a new file; delete removes one. The content is the JSON payload the i/o
panel feeds to Predict/Run.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime

from fastapi import APIRouter, Response, status

from app.core.exceptions import standard_http_exception
from app.models.errors import ErrorResponse
from app.models.test_inputs import TestInputCreateRequest, TestInputMetadata
from app.services.run_manager import test_inputs_dir_for

logger = logging.getLogger(__name__)

# Prevent pytest from treating this router file as a test file during scanning
__test__ = False

router = APIRouter(prefix="/api/skills/{skill_id}/test_inputs", tags=["test-inputs"])

# Filenames must be a safe slug: start alphanumeric, then word/dot/dash. This
# blocks path traversal (no `/`, `\`, leading-dot `..`) and odd shell names.
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_MAX_NAME_LEN = 100


@router.get(
    "",
    response_model=list[TestInputMetadata],
    responses={404: {"model": ErrorResponse}},
)
async def list_test_inputs(skill_id: str) -> list[TestInputMetadata]:
    inputs_dir = test_inputs_dir_for(skill_id)
    if not inputs_dir.exists():
        return []
    items: list[TestInputMetadata] = []
    for path in sorted(inputs_dir.glob("*.json")):
        stat = path.stat()
        items.append(
            TestInputMetadata(
                id=path.stem,
                name=path.stem,
                created_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                size_bytes=stat.st_size,
                content_preview=_preview_json(path.read_text(encoding="utf-8")),
            ),
        )
    return items


@router.post(
    "",
    response_model=TestInputMetadata,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def create_test_input(
    skill_id: str,
    request: TestInputCreateRequest,
) -> TestInputMetadata:
    name = _validated_input_name(request.name)
    logger.info("test_input create: skill=%s name=%s", skill_id, name)
    inputs_dir = test_inputs_dir_for(skill_id)
    inputs_dir.mkdir(parents=True, exist_ok=True)
    path = inputs_dir / f"{name}.json"
    if path.exists():
        logger.warning("test_input create rejected: %s already exists", path)
        raise standard_http_exception(
            "TEST_INPUT_ALREADY_EXISTS",
            f"Test input already exists: {name}",
            {"name": name},
        )
    payload = json.dumps(request.content, ensure_ascii=False, indent=2)
    path.write_text(payload, encoding="utf-8")
    stat = path.stat()
    logger.info("test_input created: %s (%d bytes)", path, stat.st_size)
    return TestInputMetadata(
        id=name,
        name=name,
        created_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
        size_bytes=stat.st_size,
        content_preview=_preview_json(payload),
    )


@router.delete(
    "/{input_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def delete_test_input(skill_id: str, input_id: str) -> Response:
    name = _validated_input_name(input_id)
    logger.info("test_input delete: skill=%s id=%s", skill_id, name)
    path = test_inputs_dir_for(skill_id) / f"{name}.json"
    if not path.exists():
        logger.warning("test_input delete rejected: %s not found", path)
        raise standard_http_exception(
            "TEST_INPUT_NOT_FOUND",
            f"Test input not found: {name}",
            {"name": name},
        )
    path.unlink()
    logger.info("test_input deleted: %s", path)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _validated_input_name(raw: str) -> str:
    # Accept either "case-a" or "case-a.json"; the .json suffix is implicit.
    name = raw.strip()
    if name.lower().endswith(".json"):
        name = name[: -len(".json")]
    if not name or len(name) > _MAX_NAME_LEN or _NAME_RE.fullmatch(name) is None:
        raise standard_http_exception(
            "TEST_INPUT_VALIDATION_FAILED",
            f"Invalid test input name: {raw!r}",
            {"name": raw},
        )
    return name


def _preview_json(raw: str) -> str:
    try:
        loaded = json.loads(raw)
        compact = json.dumps(loaded, ensure_ascii=False, separators=(",", ":"))
    except json.JSONDecodeError:
        compact = raw.replace("\n", " ")
    return compact[:120] + ("..." if len(compact) > 120 else "")
