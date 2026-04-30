"""Hidden smoke endpoints for validating exception formatting."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/_debug", tags=["debug"], include_in_schema=False)


@router.get("/value-error")
async def raise_value_error() -> None:
    raise ValueError("Studio debug ValueError")
