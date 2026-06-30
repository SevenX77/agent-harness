from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path

import pytest
from app.core import native_fs_write_boundary
from app.main import create_app
from fastapi import HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_SOURCE_WRITER_CALLS = {"update_skill_file", "update_skill_files"}
_REQUIRED_ALLOWLIST_FIELDS = {
    "owner",
    "reason",
    "risk",
    "expiry",
    "gate",
    "fallback_header",
    "fallback_value",
}


def test_skill_file_write_requires_explicit_browser_fallback_header(
    client: TestClient,
) -> None:
    skill_id = "writer-probe"
    create_response = client.post(
        "/api/skills",
        json={"skill_id": skill_id, "files": _agent_skill_files(skill_id)},
    )
    assert create_response.status_code == 201, create_response.text
    skill_dir = Path(create_response.json()["directory_path"])
    graph_path = skill_dir / "GRAPH.md"
    before = graph_path.read_text(encoding="utf-8")

    response = client.post(
        f"/api/skills/{skill_id}/files/GRAPH.md",
        json={"content": f"{before}\n# bypass\n", "expected_hash": None},
    )

    assert response.status_code == 409
    assert response.json()["error_code"] == "NATIVE_FS_REQUIRED"
    assert graph_path.read_text(encoding="utf-8") == before


def test_full_skill_update_requires_explicit_browser_fallback_header(
    client: TestClient,
) -> None:
    skill_id = "full-writer-probe"
    create_response = client.post(
        "/api/skills",
        json={"skill_id": skill_id, "files": _agent_skill_files(skill_id)},
    )
    assert create_response.status_code == 201, create_response.text
    skill_dir = Path(create_response.json()["directory_path"])
    graph_path = skill_dir / "GRAPH.md"
    before = graph_path.read_text(encoding="utf-8")
    files = _agent_skill_files(skill_id)
    files["GRAPH.md"] = before.replace("Native writer guard probe", "Bypass attempt")

    response = client.put(f"/api/skills/{skill_id}", json={"files": files})

    assert response.status_code == 409
    assert response.json()["error_code"] == "NATIVE_FS_REQUIRED"
    assert graph_path.read_text(encoding="utf-8") == before


def test_fastapi_source_writer_routes_are_discovered_and_allowlisted_with_owner_metadata() -> None:
    discovered = sorted(_discover_source_writer_routes())

    assert discovered
    allowlist = getattr(native_fs_write_boundary, "NATIVE_FS_SOURCE_WRITE_ROUTE_ALLOWLIST", {})
    violations: list[str] = []
    for route_key in discovered:
        metadata = allowlist.get(route_key)
        if metadata is None:
            violations.append(f"{route_key[0]} {route_key[1]} missing allowlist metadata")
            continue
        missing = sorted(field for field in _REQUIRED_ALLOWLIST_FIELDS if not metadata.get(field))
        if missing:
            violations.append(f"{route_key[0]} {route_key[1]} missing fields: {', '.join(missing)}")
        if metadata.get("fallback_header") != "X-Studio-Write-Fallback":
            violations.append(f"{route_key[0]} {route_key[1]} uses wrong fallback header")
        if metadata.get("fallback_value") != "browser":
            violations.append(f"{route_key[0]} {route_key[1]} uses wrong fallback value")

    assert violations == []


def test_source_writer_guard_uses_allowlist_fallback_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.routers.skills as skills_router

    route_key = ("POST", "/api/skills/{skill_id}/files/{file_path:path}")
    allowlist = native_fs_write_boundary.NATIVE_FS_SOURCE_WRITE_ROUTE_ALLOWLIST
    patched_metadata = dict(allowlist[route_key])
    patched_metadata["fallback_value"] = "desktop"
    monkeypatch.setitem(allowlist, route_key, patched_metadata)

    with pytest.raises(HTTPException) as exc_info:
        skills_router._require_browser_write_fallback("browser", route_key=route_key)

    assert exc_info.value.detail["details"]["required_value"] == "desktop"
    skills_router._require_browser_write_fallback("desktop", route_key=route_key)


def _discover_source_writer_routes() -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    for route in create_app().routes:
        if not isinstance(route, APIRoute):
            continue
        methods = set(route.methods or set()) & _MUTATING_METHODS
        if not methods or not _route_calls_source_writer(route):
            continue
        for method in methods:
            routes.add((method, route.path))
    return routes


def _route_calls_source_writer(route: APIRoute) -> bool:
    source = textwrap.dedent(inspect.getsource(route.endpoint))
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id in _SOURCE_WRITER_CALLS:
            return True
    return False


def _agent_skill_files(skill_id: str) -> dict[str, str]:
    return {
        "GRAPH.md": f"""---
schema_version: "v0.3.0"
name: {skill_id}
description: Native writer guard probe
io:
  inputs:
    type: object
    properties:
      input_text:
        type: string
    additionalProperties: true
  outputs:
    type: object
    properties:
      prepared:
        type: boolean
    additionalProperties: true
phases:
  - setup
---
<phase depends_on="input" output>setup</phase>
""",
        "phases/setup/LOGIC.md": """---
io:
  inputs:
    type: object
    properties:
      input_text:
        type: string
  outputs:
    type: object
    properties:
      prepared:
        type: boolean
---
<action>prepare</action>
""",
        "phases/setup/actions/prepare.py": """def prepare(inputs):
    return {"prepared": True}
""",
    }
