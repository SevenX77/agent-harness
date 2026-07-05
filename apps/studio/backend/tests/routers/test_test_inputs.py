"""Router tests for test-input CRUD (INPUT-3: io-panel-artifacts-test-inputs).

The list endpoint already worked; these cover the create/delete behaviour that
the design (`03_regions/input/mvp1-alignment.md` test point 3 — "增删测试输入
live，错误就近显示") requires the i/o panel to drive.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

# Prevent pytest from collecting this module's helpers as test cases.
__test__ = True

SKILL_ID = "text-segmentation"
BASE = f"/api/skills/{SKILL_ID}/test_inputs"
FALLBACK_HEADERS = {"X-Studio-Write-Fallback": "browser"}


def _create(client: TestClient, name: str, content: dict[str, object]):
    return client.post(BASE, json={"name": name, "content": content}, headers=FALLBACK_HEADERS)


def test_create_requires_explicit_browser_fallback_header(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _workspaces_dir = studio_roots
    response = client.post(BASE, json={"name": "case-a", "content": {"input_text": "hello"}})

    assert response.status_code == 409
    assert response.json()["error_code"] == "NATIVE_FS_REQUIRED"
    assert not (skills_dir / SKILL_ID / ".workspace" / "import_files" / "case-a.json").exists()


def test_create_writes_input_and_returns_metadata(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    response = _create(client, "case-a", {"input_text": "hello"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == "case-a"
    assert body["name"] == "case-a"
    assert body["size_bytes"] > 0
    assert "input_text" in body["content_preview"]
    skills_dir, _workspaces_dir = studio_roots
    assert (skills_dir / SKILL_ID / ".workspace" / "import_files" / "case-a.json").exists()
    assert not (skills_dir / SKILL_ID / ".workspace" / "test_inputs" / "case-a.json").exists()


def test_created_input_appears_in_list(client: TestClient) -> None:
    _create(client, "case-a", {"input_text": "hello"})
    _create(client, "case-b", {"input_text": "world"})

    listing = client.get(BASE)
    assert listing.status_code == 200, listing.text
    ids = {item["id"] for item in listing.json()}
    assert {"case-a", "case-b"} <= ids


def test_create_rejects_duplicate_name(client: TestClient) -> None:
    assert _create(client, "case-a", {"input_text": "hello"}).status_code == 200

    dup = _create(client, "case-a", {"input_text": "other"})
    assert dup.status_code == 409
    assert dup.json()["error_code"] == "TEST_INPUT_ALREADY_EXISTS"


def test_create_rejects_unsafe_name(client: TestClient) -> None:
    response = _create(client, "../evil", {"input_text": "hello"})
    assert response.status_code == 422
    assert response.json()["error_code"] == "TEST_INPUT_VALIDATION_FAILED"


def test_create_persists_content_roundtrip(client: TestClient) -> None:
    payload = {"input_text": "ünïcode", "nested": {"n": 1}}
    assert _create(client, "case-a", payload).status_code == 200

    listing = client.get(BASE).json()
    item = next(entry for entry in listing if entry["id"] == "case-a")
    # The preview is compact JSON; the stored bytes must round-trip the content.
    assert "ünïcode" in item["content_preview"]
    assert json.loads(json.dumps(payload))  # sanity: payload is JSON-serialisable


def test_get_returns_full_content(client: TestClient) -> None:
    payload = {"input_text": "hello", "nested": {"n": 1}}
    assert _create(client, "case-a", payload).status_code == 200

    response = client.get(f"{BASE}/case-a")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == "case-a"
    assert body["name"] == "case-a"
    assert body["content"] == payload


def test_get_missing_input_returns_not_found(client: TestClient) -> None:
    response = client.get(f"{BASE}/missing")
    assert response.status_code == 404
    assert response.json()["error_code"] == "TEST_INPUT_NOT_FOUND"


def test_delete_removes_input(client: TestClient) -> None:
    assert _create(client, "case-a", {"input_text": "hello"}).status_code == 200

    deleted = client.delete(f"{BASE}/case-a", headers=FALLBACK_HEADERS)
    assert deleted.status_code == 204, deleted.text

    listing = client.get(BASE).json()
    assert all(item["id"] != "case-a" for item in listing)


def test_delete_missing_input_returns_not_found(client: TestClient) -> None:
    response = client.delete(f"{BASE}/does-not-exist", headers=FALLBACK_HEADERS)
    assert response.status_code == 404
    assert response.json()["error_code"] == "TEST_INPUT_NOT_FOUND"


def test_delete_requires_explicit_browser_fallback_header(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _workspaces_dir = studio_roots
    input_path = skills_dir / SKILL_ID / ".workspace" / "import_files" / "case-a.json"
    input_path.parent.mkdir(parents=True, exist_ok=True)
    input_path.write_text('{"input_text":"keep me"}', encoding="utf-8")

    response = client.delete(f"{BASE}/case-a")

    assert response.status_code == 409
    assert response.json()["error_code"] == "NATIVE_FS_REQUIRED"
    assert input_path.exists()


def test_delete_then_recreate_same_name(client: TestClient) -> None:
    assert _create(client, "case-a", {"input_text": "v1"}).status_code == 200
    assert client.delete(f"{BASE}/case-a", headers=FALLBACK_HEADERS).status_code == 204
    # Name is free again after delete.
    assert _create(client, "case-a", {"input_text": "v2"}).status_code == 200


def test_create_for_unknown_skill_is_skill_not_found(client: TestClient) -> None:
    response = client.post(
        "/api/skills/no-such-skill/test_inputs",
        json={"name": "case-a", "content": {"input_text": "hi"}},
        headers=FALLBACK_HEADERS,
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "SKILL_NOT_FOUND"
