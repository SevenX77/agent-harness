"""Test input endpoint scaffold."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.exceptions import raise_not_implemented
from app.models.errors import ErrorResponse
from app.models.test_inputs import TestInputMetadata

router = APIRouter(prefix="/api/skills/{skill_id}/test_inputs", tags=["test-inputs"])


@router.get(
    "",
    response_model=list[TestInputMetadata],
    responses={501: {"model": ErrorResponse}},
)
async def list_test_inputs(skill_id: str) -> list[TestInputMetadata]:
    raise_not_implemented(f"list test inputs for skill {skill_id}")


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
