"""In-process host used by Studio HTTP loopback endpoints."""

from __future__ import annotations

import hmac
from collections.abc import Callable
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from typing import Any

from fastapi.responses import JSONResponse
from pydantic import SecretStr, ValidationError

from app.core.adapters.engine import EngineAdapter
from app.core.adapters.gateway import GatewayAdapter
from app.core.adapters.http_transport import SCHEMA_VERSION, StudioAdapterError

LOOPBACK_TOKEN_HEADER = "X-Studio-Loopback-Token"


def invoke_engine(method_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    return _invoke(lambda: getattr(EngineAdapter(transport="in_process"), method_name)(payload))


def invoke_gateway(method_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    return _invoke(lambda: getattr(GatewayAdapter(transport="in_process"), method_name)(payload))


def _invoke(call_owner: Callable[[], Any]) -> dict[str, Any]:
    try:
        return _success(call_owner())
    except StudioAdapterError as exc:
        return _failure(exc.error_code, exc.error_payload)
    except KeyError as exc:
        return _failure("loopback.owner_key_error", {"missing_key": str(exc.args[0]) if exc.args else ""})
    except (ValueError, ValidationError) as exc:
        return _failure("loopback.validation_failed", _validation_payload(exc))
    except Exception:
        return JSONResponse(
            status_code=500,
            content=_failure("loopback.internal_error", {"detail": "Loopback owner failed"}),
        )


def is_loopback_token_valid(actual: str | None, expected: str) -> bool:
    if not actual or not expected:
        return False
    return hmac.compare_digest(actual.encode(), expected.encode())


def _success(data: Any) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "data": _json_compatible(data),
    }


def _failure(error_code: str, error_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": False,
        "error_code": error_code,
        "error_payload": _json_compatible(error_payload),
    }


def _validation_payload(exc: ValueError | ValidationError) -> dict[str, Any]:
    if isinstance(exc, ValidationError):
        return {"errors": _json_compatible(exc.errors())}
    return {"detail": str(exc)}


def _json_compatible(value: Any) -> Any:
    if isinstance(value, SecretStr):
        return "**********"
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "model_dump"):
        return _json_compatible(value.model_dump(mode="json"))
    if is_dataclass(value) and not isinstance(value, type):
        return _json_compatible(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_compatible(item) for item in value]
    return value
