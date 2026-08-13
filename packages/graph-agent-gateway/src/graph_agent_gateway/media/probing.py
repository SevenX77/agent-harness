"""Zero-cost connectivity probe for media generation providers.

RunningHub's account-status endpoint validates the API key and returns the
account balance without creating any billable generation task — that is what
makes it safe to call automatically (L1 in the three-layer test design).
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import httpx

from graph_agent_gateway.media.schema import MediaProbeResult, MediaProviderCredential

_ACCOUNT_STATUS_PATH = "/uc/openapi/accountStatus"
_DEFAULT_TIMEOUT_SECONDS = 8.0


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


async def probe_runninghub_account(
    credential: MediaProviderCredential,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
) -> MediaProbeResult:
    url = credential.base_url.rstrip("/") + _ACCOUNT_STATUS_PATH
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(
            transport=transport, timeout=timeout_seconds
        ) as client:
            response = await client.post(
                url,
                json={"apikey": credential.api_key.get_secret_value()},
                headers={"Content-Type": "application/json"},
            )
        latency_ms = int((time.monotonic() - started) * 1000)
        payload: Any = response.json()
    except httpx.HTTPError as exc:
        return MediaProbeResult(
            status="network_error",
            checked_at=_now_iso(),
            message=f"{type(exc).__name__}: {exc}",
        )
    except ValueError:
        return MediaProbeResult(
            status="network_error",
            checked_at=_now_iso(),
            latency_ms=int((time.monotonic() - started) * 1000),
            message=f"non-JSON response (HTTP {response.status_code})",
        )

    if not isinstance(payload, dict) or "code" not in payload:
        return MediaProbeResult(
            status="network_error",
            checked_at=_now_iso(),
            latency_ms=latency_ms,
            message="unexpected response shape: missing code",
        )

    if payload.get("code") == 0:
        data = payload.get("data")
        data_map: dict[str, Any] = data if isinstance(data, dict) else {}
        coins = data_map.get("remainCoins")
        money = data_map.get("remainMoney")
        return MediaProbeResult(
            status="ok",
            checked_at=_now_iso(),
            latency_ms=latency_ms,
            remain_coins=str(coins) if coins is not None else None,
            remain_money=str(money) if money is not None else None,
        )

    return MediaProbeResult(
        status="auth_failed",
        checked_at=_now_iso(),
        latency_ms=latency_ms,
        message=f"code={payload.get('code')}: {payload.get('msg')}",
    )
