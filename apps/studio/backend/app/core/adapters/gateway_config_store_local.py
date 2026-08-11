from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from graph_agent_gateway.registry import ConfigRecord as GatewayConfigRecord

from app.core.adapters.http_transport import StudioAdapterError


class ConfigRecord(GatewayConfigRecord):
    user_id: str
    key: str


class LocalGatewayConfigStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def get_config(self, user_id: str, key: str) -> ConfigRecord:
        if not user_id or not key:
            raise ValueError("user_id and key cannot be empty")

        file_path = self.root / user_id / f"{key}.json"
        if not file_path.exists():
            raise StudioAdapterError("config.not_found", {"detail": "Config not found"})

        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        return ConfigRecord(
            user_id=data["user_id"],
            key=data["key"],
            value=data["value"],
            etag=data["etag"],
        )

    def put_config(
        self,
        user_id: str,
        key: str,
        value: dict[str, Any],
        *,
        if_match: str | None = None,
        if_none_match: str | None = None,
    ) -> str:
        if not user_id or not key:
            raise ValueError("user_id and key cannot be empty")

        user_dir = self.root / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        file_path = user_dir / f"{key}.json"

        existing_etag = None
        if file_path.exists():
            try:
                with open(file_path, encoding="utf-8") as f:
                    data = json.load(f)
                    existing_etag = data.get("etag")
            except Exception:
                pass

        if if_match is not None:
            if existing_etag != if_match:
                raise StudioAdapterError("config.etag_conflict", {"detail": "etag mismatch"})

        if if_none_match == "*":
            if file_path.exists():
                raise StudioAdapterError("config.etag_conflict", {"detail": "record already exists"})

        new_etag = str(uuid.uuid4())
        record_data = {
            "user_id": user_id,
            "key": key,
            "value": value,
            "etag": new_etag,
        }

        # 原子写入
        temp_file_path = file_path.with_suffix(".tmp")
        try:
            with open(temp_file_path, "w", encoding="utf-8") as f:
                json.dump(record_data, f, ensure_ascii=False, indent=2)
            temp_file_path.replace(file_path)
        except Exception as e:
            if temp_file_path.exists():
                try:
                    temp_file_path.unlink()
                except Exception:
                    pass
            raise e

        return new_etag
