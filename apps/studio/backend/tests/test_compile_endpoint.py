from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import copy_skill


def test_compile_success_returns_manifest_summary(client: TestClient) -> None:
    response = client.post("/api/skills/text-segmentation/compile")

    assert response.status_code == 200
    body = response.json()
    assert body["skill_id"] == "text-segmentation"
    assert body["status"] == "ok"
    assert body["phase_count"] == 1
    assert body["manifest_name"] == "text-segmentation"
    assert body["artifact_ref"]["artifact_id"] == "text-segmentation"
    assert body["artifact_ref"]["content_hash"].startswith("sha256:")
    assert body["artifact_ref"]["source_map_ref"] == body["source_map_ref"]
    assert body["artifact_ref"]["execution_fingerprint"] == body["execution_fingerprint"]


def test_compile_failure_returns_structured_errors(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, workspaces_dir = studio_roots
    skill_dir = copy_skill(skills_dir, workspaces_dir, "text-segmentation")
    phase_path = skill_dir / "phases" / "setup" / "LOGIC.md"
    phase_path.write_text(
        phase_path.read_text(encoding="utf-8").replace("---\n", "---\nmode: bogus\n", 1),
        encoding="utf-8",
    )

    response = client.post("/api/skills/text-segmentation/compile")

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "compile_failed"
    assert body["detail"].startswith("Skill compilation failed with 1 error")
    assert body["errors"]
    error = body["errors"][0]
    assert set(error) == {"file", "line", "field", "severity", "message", "error_code"}
    assert error["file"] in {"phases/setup/LOGIC.md", None}
    assert error["line"] is None or isinstance(error["line"], int)
    assert error["field"] is None or isinstance(error["field"], str)
    assert error["severity"] == "fatal"
    assert error["error_code"] is None or isinstance(error["error_code"], str)
    assert "mode" in error["message"]


def test_compile_unresolved_subgraph_returns_structured_compile_error(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, workspaces_dir = studio_roots
    skill_dir = copy_skill(skills_dir, workspaces_dir, "text-segmentation")
    phase_dir = skill_dir / "phases" / "setup"
    (phase_dir / "LOGIC.md").unlink()
    (phase_dir / "SUBGRAPH.md").write_text(
        """---
target_skill: missing.child
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
---
""",
        encoding="utf-8",
    )

    response = client.post("/api/skills/text-segmentation/compile")

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "compile_failed"
    assert body["detail"] == "Skill compilation failed with 1 error"
    assert len(body["errors"]) == 1
    error = body["errors"][0]
    assert error["severity"] == "fatal"
    assert "missing.child" in error["message"]


def test_compile_missing_skill_returns_404(client: TestClient) -> None:
    response = client.post("/api/skills/nope/compile")

    assert response.status_code == 404
    assert response.json()["error_code"] == "SKILL_NOT_FOUND"
