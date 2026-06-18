"""Loopback endpoints for Studio adapter transports."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

from app.core.adapters.http_transport import SCHEMA_VERSION
from app.core.adapters.loopback_host import (
    LOOPBACK_TOKEN_HEADER,
    invoke_engine,
    invoke_gateway,
    is_loopback_token_valid,
)
from app.core.backends import get_backend_config


def _require_internal_loopback(
    loopback_token: str | None = Header(default=None, alias=LOOPBACK_TOKEN_HEADER),
) -> None:
    expected = get_backend_config().loopback_token
    if is_loopback_token_valid(loopback_token, expected):
        return
    raise HTTPException(
        status_code=403,
        detail={
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "error_code": "LOOPBACK_FORBIDDEN",
            "error_payload": {
                "http_status": 403,
                "message": "Loopback endpoints require an internal loopback token",
                "retry_strategy": "not_retryable",
            },
        },
    )


router = APIRouter(tags=["loopback"], dependencies=[Depends(_require_internal_loopback)])


@router.post("/engine/compile")
def engine_compile(payload: dict[str, Any]) -> dict[str, Any]:
    return invoke_engine("compile", payload)


@router.post("/engine/run_artifact")
def engine_run_artifact(payload: dict[str, Any]) -> dict[str, Any]:
    return invoke_engine("run_artifact", payload)


@router.post("/engine/predict_artifact")
def engine_predict_artifact(payload: dict[str, Any]) -> dict[str, Any]:
    return invoke_engine("predict_artifact", payload)


@router.post("/engine/resume")
def engine_resume(payload: dict[str, Any]) -> dict[str, Any]:
    return invoke_engine("resume", payload)


@router.post("/gateway/resolve_routes")
def gateway_resolve_routes(payload: dict[str, Any]) -> dict[str, Any]:
    return invoke_gateway("resolve_routes", payload)


@router.post("/gateway/materialize_role")
def gateway_materialize_role(payload: dict[str, Any]) -> dict[str, Any]:
    return invoke_gateway("materialize_role", payload)


@router.post("/gateway/materialize_model_bundle")
def gateway_materialize_model_bundle(payload: dict[str, Any]) -> dict[str, Any]:
    return invoke_gateway("materialize_model_bundle", payload)


@router.post("/gateway/project_route_state")
def gateway_project_route_state(payload: dict[str, Any]) -> dict[str, Any]:
    return invoke_gateway("project_route_state", payload)


@router.post("/gateway/decide_fallback")
def gateway_decide_fallback(payload: dict[str, Any]) -> dict[str, Any]:
    return invoke_gateway("decide_fallback", payload)


@router.post("/gateway/resolve_credential")
def gateway_resolve_credential(payload: dict[str, Any]) -> dict[str, Any]:
    return invoke_gateway("resolve_credential", payload)
