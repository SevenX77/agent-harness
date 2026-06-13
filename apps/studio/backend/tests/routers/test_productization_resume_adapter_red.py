from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_ROOT = next(
    parent for parent in Path(__file__).resolve().parents if (parent / "app").is_dir() and (parent / "tests").is_dir()
)


def test_resume_endpoint_is_no_longer_not_implemented(client: TestClient) -> None:
    response = client.post(
        "/api/skills/text-segmentation/runs/run-123/resume",
        json={"human_input": "continue from checkpoint"},
    )

    assert response.status_code != 501


def test_resume_endpoint_delegates_to_engine_adapter_resume() -> None:
    source = (BACKEND_ROOT / "app" / "routers" / "runs.py").read_text(encoding="utf-8")

    assert "EngineAdapter" in source
    assert ".resume(" in source
    assert "raise_not_implemented" not in source
