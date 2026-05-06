"""Test input endpoint scaffold."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Request

from app.core.exceptions import raise_not_implemented
from app.models.errors import ErrorResponse
from app.models.test_inputs import TestInputMetadata
from app.services.run_manager import test_inputs_dir_for

router = APIRouter(prefix="/api/skills/{skill_id}/test_inputs", tags=["test-inputs"])


@router.get(
    "",
    response_model=list[TestInputMetadata],
    responses={501: {"model": ErrorResponse}},
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
    responses={501: {"model": ErrorResponse}},
)
async def create_test_input(skill_id: str, request: Request) -> TestInputMetadata:
    raise_not_implemented(f"create test input for skill {skill_id}")


@router.delete(
    "/{input_id}",
    response_model=ErrorResponse,
    responses={501: {"model": ErrorResponse}},
)
async def delete_test_input(skill_id: str, input_id: str) -> ErrorResponse:
    raise_not_implemented(f"delete test input {input_id} for skill {skill_id}")


def _preview_json(raw: str) -> str:
    try:
        loaded = json.loads(raw)
        compact = json.dumps(loaded, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        compact = raw.replace("\n", " ")
    return compact[:120] + ("..." if len(compact) > 120 else "")
