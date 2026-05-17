from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import copy_skill


def test_validate_input_accepts_json_file(client: TestClient, tmp_path: Path) -> None:
    input_file = _write_json(
        tmp_path / "input.json",
        {"input_text": "hello from json"},
    )

    response = client.post(
        "/api/skills/text-segmentation/validate_input",
        json={"input_file_path": str(input_file)},
    )

    assert response.status_code == 200
    assert response.json() == {"validated_data": {"input_text": "hello from json"}}


def test_validate_input_accepts_yaml_file(client: TestClient, tmp_path: Path) -> None:
    input_file = tmp_path / "input.yaml"
    input_file.write_text("input_text: hello from yaml\n", encoding="utf-8")

    response = client.post(
        "/api/skills/text-segmentation/validate_input",
        json={"input_file_path": str(input_file)},
    )

    assert response.status_code == 200
    assert response.json() == {"validated_data": {"input_text": "hello from yaml"}}


def test_validate_input_file_not_found_returns_404(
    client: TestClient,
    tmp_path: Path,
) -> None:
    response = client.post(
        "/api/skills/text-segmentation/validate_input",
        json={"input_file_path": str(tmp_path / "missing.json")},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "input file not found"}


def test_validate_input_json_parse_error_returns_file_error(
    client: TestClient,
    tmp_path: Path,
) -> None:
    input_file = tmp_path / "bad.json"
    input_file.write_text('{"input_text":', encoding="utf-8")

    response = client.post(
        "/api/skills/text-segmentation/validate_input",
        json={"input_file_path": str(input_file)},
    )

    assert response.status_code == 422
    error = response.json()["errors"][0]
    assert error["loc"] == ["__file__"]
    assert error["msg"].startswith("JSON/YAML parse error:")


def test_validate_input_yaml_parse_error_returns_file_error(
    client: TestClient,
    tmp_path: Path,
) -> None:
    input_file = tmp_path / "bad.yaml"
    input_file.write_text("input_text: [unterminated\n", encoding="utf-8")

    response = client.post(
        "/api/skills/text-segmentation/validate_input",
        json={"input_file_path": str(input_file)},
    )

    assert response.status_code == 422
    error = response.json()["errors"][0]
    assert error["loc"] == ["__file__"]
    assert error["msg"].startswith("JSON/YAML parse error:")


def test_validate_input_reports_type_mismatch(client: TestClient, tmp_path: Path) -> None:
    input_file = _write_json(tmp_path / "wrong-type.json", {"input_text": 123})

    response = client.post(
        "/api/skills/text-segmentation/validate_input",
        json={"input_file_path": str(input_file)},
    )

    assert response.status_code == 422
    error = response.json()["errors"][0]
    assert error["loc"] == ["input_text"]
    assert error["type"] == "string_type"


def test_validate_input_reports_missing_required_field(
    client: TestClient,
    tmp_path: Path,
) -> None:
    input_file = _write_json(tmp_path / "missing-field.json", {})

    response = client.post(
        "/api/skills/text-segmentation/validate_input",
        json={"input_file_path": str(input_file)},
    )

    assert response.status_code == 422
    error = response.json()["errors"][0]
    assert error["loc"] == ["input_text"]
    assert error["type"] == "missing"


def test_validate_input_reports_extra_field(client: TestClient, tmp_path: Path) -> None:
    input_file = _write_json(
        tmp_path / "extra-field.json",
        {"input_text": "hello", "extra": True},
    )

    response = client.post(
        "/api/skills/text-segmentation/validate_input",
        json={"input_file_path": str(input_file)},
    )

    assert response.status_code == 422
    errors = response.json()["errors"]
    assert any(error["loc"] == ["extra"] and error["type"] == "extra_forbidden" for error in errors)


def test_validate_input_missing_skill_returns_404(client: TestClient, tmp_path: Path) -> None:
    input_file = _write_json(tmp_path / "input.json", {"input_text": "hello"})

    response = client.post(
        "/api/skills/nope/validate_input",
        json={"input_file_path": str(input_file)},
    )

    assert response.status_code == 404
    assert response.json()["error_code"] == "SKILL_NOT_FOUND"


def test_validate_input_compile_failure_returns_gate_error(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    skills_dir, workspaces_dir = studio_roots
    skill_dir = copy_skill(skills_dir, workspaces_dir, "text-segmentation")
    skill_path = skill_dir / "phases" / "setup" / "LOGIC.md"
    skill_path.write_text(
        skill_path.read_text(encoding="utf-8").replace("mode: logic\n", "mode: bogus\n"),
        encoding="utf-8",
    )
    input_file = _write_json(tmp_path / "input.json", {"input_text": "hello"})

    response = client.post(
        "/api/skills/text-segmentation/validate_input",
        json={"input_file_path": str(input_file)},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "skill itself failed to compile, fix it first"}


def _write_json(path: Path, data: dict[str, Any]) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path
