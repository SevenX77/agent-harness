from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
from app.core.adapters.http_transport import HttpTransport
from tests.support.multi_worker_storage import Worker


class HttpLoopbackHarness:
    def __init__(self, schema_version: str, storage_root: Path | None = None):
        self.schema_version = schema_version
        self.storage_root = storage_root
        self.routes: dict[str, tuple[dict[str, Any], tuple[str, ...]]] = {}
        self.injections: dict[str, str] = {}
        self.client: httpx.Client | None = None

    def __enter__(self) -> HttpLoopbackHarness:
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            error_type = self.injections.get(path)

            if error_type == "timeout":
                raise httpx.TimeoutException("Mocked timeout", request=request)
            elif error_type == "connection_refused":
                raise httpx.ConnectError("Mocked connection refused", request=request)
            elif error_type == "http_5xx":
                return httpx.Response(500, content=b"Mocked Internal Server Error")
            elif error_type == "malformed_json":
                return httpx.Response(200, content=b"Mocked invalid json {")
            elif error_type == "missing_dto_fields":
                return httpx.Response(200, json={"data": {}})
            elif error_type == "schema_mismatch":
                return httpx.Response(
                    200,
                    json={
                        "schema_version": "wrong_schema_version",
                        "ok": True,
                        "data": {},
                    },
                )

            if path in self.routes:
                resp_data, req_fields = self.routes[path]
                try:
                    payload = json.loads(request.read())
                except Exception:
                    payload = {}

                for field in req_fields:
                    if field not in payload:
                        return httpx.Response(
                            200,
                            json={
                                "schema_version": self.schema_version,
                                "ok": False,
                                "error_code": "transport.serialization_failed",
                                "error_payload": {"detail": f"Missing field {field}"},
                            },
                        )

                return httpx.Response(
                    200,
                    json={
                        "schema_version": self.schema_version,
                        "ok": True,
                        "data": resp_data,
                    },
                )

            return httpx.Response(
                404,
                json={
                    "schema_version": self.schema_version,
                    "ok": False,
                    "error_code": "transport.not_found",
                    "error_payload": {"detail": "Not Found"},
                },
            )

        self.client = httpx.Client(transport=httpx.MockTransport(handler))
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.client:
            self.client.close()

    def route(self, path: str, data: dict[str, Any], required_fields: tuple[str, ...] = ()) -> None:
        self.routes[path] = (data, required_fields)

    def inject_timeout(self, path: str) -> None:
        self.injections[path] = "timeout"

    def inject_connection_refused(self, path: str) -> None:
        self.injections[path] = "connection_refused"

    def inject_5xx(self, path: str) -> None:
        self.injections[path] = "http_5xx"

    def inject_malformed_json(self, path: str) -> None:
        self.injections[path] = "malformed_json"

    def inject_missing_dto_fields(self, path: str) -> None:
        self.injections[path] = "missing_dto_fields"

    def inject_schema_mismatch(self, path: str) -> None:
        self.injections[path] = "schema_mismatch"

    def http_transport(self, schema_version: str) -> HttpTransport:
        if not self.client:
            raise ValueError("Harness must be entered first")
        return HttpTransport(
            base_url="http://loopback.harness",
            http_client=self.client,
            schema_version=schema_version,
        )

    def start_workers(self, count: int) -> tuple[Worker, ...]:
        if not self.storage_root:
            raise ValueError("storage_root must be configured to start workers")
        return tuple(Worker(self.storage_root) for _ in range(count))
