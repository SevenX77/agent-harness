from __future__ import annotations

from pathlib import Path

from app.core.adapters.gateway_config_store_local import LocalGatewayConfigStore


class Worker:
    def __init__(self, storage_root: Path):
        self.gateway_config_store = LocalGatewayConfigStore(root=storage_root)
