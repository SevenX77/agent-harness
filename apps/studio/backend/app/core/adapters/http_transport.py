from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx

SCHEMA_VERSION = "studio.mvp1.v1"


class StudioAdapterError(Exception):
    def __init__(self, error_code: str, error_payload: dict[str, Any] | None = None):
        super().__init__(f"StudioAdapterError: {error_code} - {error_payload}")
        self.error_code = error_code
        self.error_payload = error_payload or {}


class HttpTransport:
    def __init__(
        self,
        base_url: str,
        http_client: httpx.Client | None = None,
        schema_version: str = SCHEMA_VERSION,
    ):
        self.base_url = base_url
        self.http_client = http_client or httpx.Client()
        self.schema_version = schema_version

    def post(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> Any:
        headers = {}
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key

        url = f"{self.base_url.rstrip('/')}{path}"
        max_attempts = 2 if idempotency_key else 1
        last_exc = None

        for attempt in range(max_attempts):
            try:
                response = self.http_client.post(url, json=payload, headers=headers)
                break
            except httpx.TimeoutException as exc:
                last_exc = exc
                if attempt < max_attempts - 1:
                    continue
                raise StudioAdapterError("transport.timeout", {"detail": str(exc)}) from exc
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                raise StudioAdapterError("transport.connection_refused", {"detail": str(exc)}) from exc
            except httpx.RequestError as exc:
                raise StudioAdapterError("transport.connection_refused", {"detail": str(exc)}) from exc
        else:
            if last_exc:
                raise StudioAdapterError("transport.timeout", {"detail": str(last_exc)}) from last_exc

        if response.status_code >= 500:
            try:
                data = response.json()
                if isinstance(data, dict) and "schema_version" in data and "ok" in data and not data["ok"]:
                    err_code = data.get("error_code", "unknown")
                    err_payload = data.get("error_payload")
                    if not isinstance(err_payload, dict):
                        err_payload = {"detail": err_payload} if err_payload is not None else {}
                    raise StudioAdapterError(err_code, err_payload)
            except StudioAdapterError:
                raise
            except Exception:
                pass
            raise StudioAdapterError("transport.http_5xx", {"status_code": response.status_code})

        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise StudioAdapterError("transport.serialization_failed", {"detail": "Malformed JSON"}) from exc

        if not isinstance(data, dict):
            raise StudioAdapterError("transport.serialization_failed", {"detail": "Envelope is not a dict"})

        if "schema_version" not in data or "ok" not in data:
            raise StudioAdapterError("transport.serialization_failed", {"detail": "Missing DTO fields"})

        if data["schema_version"] != self.schema_version:
            raise StudioAdapterError(
                "transport.schema_mismatch",
                {
                    "expected": self.schema_version,
                    "actual": data["schema_version"],
                },
            )

        if not data["ok"]:
            err_code = data.get("error_code", "unknown")
            err_payload = data.get("error_payload")
            if not isinstance(err_payload, dict):
                err_payload = {"detail": err_payload} if err_payload is not None else {}
            raise StudioAdapterError(err_code, err_payload)

        if "data" not in data:
            raise StudioAdapterError(
                "transport.serialization_failed",
                {"detail": "Missing data field in successful response"},
            )

        return data["data"]

    def stream_events(
        self,
        path: str,
        *,
        cursor: int | None = None,
        idempotency_key: str | None = None,
    ) -> Iterator[Any]:
        headers = {}
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key

        params = {}
        if cursor is not None:
            params["cursor"] = str(cursor)

        url = f"{self.base_url.rstrip('/')}{path}"
        try:
            response = self.http_client.get(url, params=params, headers=headers)
        except httpx.TimeoutException as exc:
            raise StudioAdapterError("transport.timeout", {"detail": str(exc)}) from exc
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise StudioAdapterError("transport.connection_refused", {"detail": str(exc)}) from exc
        except httpx.RequestError as exc:
            raise StudioAdapterError("transport.connection_refused", {"detail": str(exc)}) from exc

        if response.status_code >= 500:
            raise StudioAdapterError("transport.http_5xx", {"status_code": response.status_code})

        seen_seqs = set()
        lines = response.text.splitlines() if response.text else []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except (json.JSONDecodeError, ValueError) as exc:
                raise StudioAdapterError("transport.serialization_failed", {"detail": "Malformed JSON"}) from exc

            if not isinstance(data, dict):
                raise StudioAdapterError("transport.serialization_failed", {"detail": "Envelope is not a dict"})

            if "schema_version" not in data or "ok" not in data:
                raise StudioAdapterError("transport.serialization_failed", {"detail": "Missing DTO fields"})

            if data["schema_version"] != self.schema_version:
                raise StudioAdapterError(
                    "transport.schema_mismatch",
                    {
                        "expected": self.schema_version,
                        "actual": data["schema_version"],
                    },
                )

            if not data["ok"]:
                err_code = data.get("error_code", "unknown")
                err_payload = data.get("error_payload") or {}
                raise StudioAdapterError(err_code, err_payload)

            event_data = data.get("data")
            if not isinstance(event_data, dict) or "seq" not in event_data:
                raise StudioAdapterError("transport.serialization_failed", {"detail": "Missing seq in event data"})

            seq = event_data["seq"]
            if seq in seen_seqs:
                continue
            seen_seqs.add(seq)

            if cursor is not None and seq <= cursor:
                continue

            yield event_data
