from __future__ import annotations

import uuid
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict


class ConfigRecord(BaseModel):
    value: dict[str, Any]
    etag: str

    model_config = ConfigDict(extra="forbid")


class ConfigConflictError(Exception):
    def __init__(self, error_code: str, error_payload: dict[str, Any]) -> None:
        super().__init__(f"ConfigConflictError: {error_code} - {error_payload}")
        self.error_code = error_code
        self.error_payload = error_payload


class ConfigTruthStore(Protocol):
    def get_config(self, user_id: str, key: str) -> ConfigRecord:
        ...

    def put_config(
        self,
        user_id: str,
        key: str,
        value: dict[str, Any],
        *,
        if_match: str | None = None,
        if_none_match: str | None = None,
    ) -> str:
        ...


class InMemoryConfigTruthStore:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], ConfigRecord] = {}

    def get_config(self, user_id: str, key: str) -> ConfigRecord:
        record = self._store.get((user_id, key))
        if record is None:
            raise KeyError(f"Config for user {user_id} with key {key} not found")
        return record

    def put_config(
        self,
        user_id: str,
        key: str,
        value: dict[str, Any],
        *,
        if_match: str | None = None,
        if_none_match: str | None = None,
    ) -> str:
        record = self._store.get((user_id, key))

        if if_none_match == "*":
            if record is not None:
                raise ConfigConflictError(
                    error_code="config.etag_conflict",
                    error_payload={
                        "user_id": user_id,
                        "key": key,
                    },
                )

        if if_match is not None:
            if record is None or record.etag != if_match:
                raise ConfigConflictError(
                    error_code="config.etag_conflict",
                    error_payload={
                        "user_id": user_id,
                        "key": key,
                        "expected_etag": record.etag if record else None,
                        "actual_if_match": if_match,
                    },
                )

        new_etag = f"etag-{uuid.uuid4().hex}"
        self._store[(user_id, key)] = ConfigRecord(value=value, etag=new_etag)
        return new_etag
