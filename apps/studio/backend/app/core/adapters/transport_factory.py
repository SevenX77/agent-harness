"""Factories for configured Studio adapter transports."""

from __future__ import annotations

import os

from app.core.adapters.engine import EngineAdapter
from app.core.adapters.gateway import GatewayAdapter
from app.core.adapters.http_transport import HttpTransport
from app.core.adapters.loopback_host import LOOPBACK_TOKEN_HEADER
from app.core.backends import get_backend_config


def build_engine_adapter() -> EngineAdapter:
    """Return an EngineAdapter configured from BackendConfig."""
    cfg = get_backend_config()
    if cfg.engine_transport == "in_process":
        return EngineAdapter(transport="in_process")
    if cfg.engine_transport == "http_loopback":
        return EngineAdapter(
            transport="http_loopback",
            http_transport=HttpTransport(
                base_url=cfg.engine_loopback_base_url,
                headers=_loopback_headers(cfg.loopback_token),
            ),
        )
    raise ValueError(f"Unsupported engine transport: {cfg.engine_transport}")


def build_gateway_adapter() -> GatewayAdapter:
    """Return a GatewayAdapter configured from BackendConfig."""
    cfg = get_backend_config()
    if cfg.gateway_transport == "in_process":
        return GatewayAdapter(transport="in_process")
    if cfg.gateway_transport == "http_loopback":
        return GatewayAdapter(
            transport="http_loopback",
            http_transport=HttpTransport(
                base_url=cfg.gateway_loopback_base_url,
                headers=_loopback_headers(cfg.loopback_token),
            ),
        )
    raise ValueError(f"Unsupported gateway transport: {cfg.gateway_transport}")


def _loopback_headers(loopback_token: str) -> dict[str, str]:
    headers = {LOOPBACK_TOKEN_HEADER: loopback_token}
    auth_token = (os.environ.get("STUDIO_API_TOKEN") or os.environ.get("STUDIO_DEV_TUNNEL_TOKEN") or "").strip()
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    return headers
