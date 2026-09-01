from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import copy_skill


def test_validate_input_accepts_a_submitted_payload(client: TestClient) -> None:
    response = client.post(
        "/api/skills/text-segmentation/validate_input",
        json={"input_data": {"input_text": "hello from the playground"}},
    )

    assert response.status_code == 200
    assert response.json() == {"validated_data": {"input_text": "hello from the playground"}}


def test_validate_input_rejects_a_payload_outside_the_envelope(client: TestClient) -> None:
    """The inputs travel in ``input_data``, so a bare object is a shape error.

    Asserted because the envelope is what lets this model forbid extras: a
    top-level passthrough dict cannot tell a skill input apart from a control
    field, and the previous contract mismatch (frontend posting the bare object,
    backend declaring ``input_file_path``) is exactly what an unasserted shape
    lets happen again.
    """
    response = client.post(
        "/api/skills/text-segmentation/validate_input",
        json={"input_text": "hello"},
    )

    assert response.status_code == 422


def test_validate_input_reports_type_mismatch(client: TestClient) -> None:
    response = client.post(
        "/api/skills/text-segmentation/validate_input",
        json={"input_data": {"input_text": 123}},
    )

    assert response.status_code == 422
    error = response.json()["errors"][0]
    assert error["loc"] == ["input_text"]
    assert error["type"] == "string_type"


def test_validate_input_reports_missing_required_field(client: TestClient) -> None:
    response = client.post(
        "/api/skills/text-segmentation/validate_input",
        json={"input_data": {}},
    )

    assert response.status_code == 422
    error = response.json()["errors"][0]
    assert error["loc"] == ["input_text"]
    assert error["type"] == "missing"


def test_validate_input_reports_extra_field(client: TestClient) -> None:
    response = client.post(
        "/api/skills/text-segmentation/validate_input",
        json={"input_data": {"input_text": "hello", "extra": True}},
    )

    assert response.status_code == 422
    errors = response.json()["errors"]
    assert any(error["loc"] == ["extra"] and error["type"] == "extra_forbidden" for error in errors)


def test_validate_input_missing_skill_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/skills/nope/validate_input",
        json={"input_data": {"input_text": "hello"}},
    )

    assert response.status_code == 404
    assert response.json()["error_code"] == "SKILL_NOT_FOUND"


def test_validate_input_compile_failure_returns_gate_error(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, workspaces_dir = studio_roots
    skill_dir = copy_skill(skills_dir, workspaces_dir, "text-segmentation")
    skill_path = skill_dir / "phases" / "setup" / "LOGIC.md"
    skill_path.write_text(
        skill_path.read_text(encoding="utf-8").replace("---\n", "---\nmode: bogus\n", 1),
        encoding="utf-8",
    )

    response = client.post(
        "/api/skills/text-segmentation/validate_input",
        json={"input_data": {"input_text": "hello"}},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "skill itself failed to compile, fix it first"}
