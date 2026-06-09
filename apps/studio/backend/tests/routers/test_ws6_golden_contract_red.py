from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient


def test_ws6_manual_per_agent_golden_can_be_saved_without_run_promotion(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/skills/text-segmentation/golden",
        json={
            "node_id": "setup",
            "expected_output": {"prepared": True},
            "source": "manual",
            "lock": False,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["node_id"] == "setup"
    assert body["source"] == "manual"
    assert body["locked"] is False
    assert ".workspace/golden" in body["content_path"]
    assert ".workspace/runs" not in body["content_path"]


def test_ws6_whole_run_final_state_promotion_is_rejected(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _workspaces_dir = studio_roots
    run_dir = skills_dir / "text-segmentation" / ".workspace" / "runs" / "real-run"
    run_dir.mkdir(parents=True)
    (run_dir / "final_state.json").write_text(
        json.dumps({"setup": {"prepared": True}}),
        encoding="utf-8",
    )

    response = client.post(
        "/api/skills/text-segmentation/golden",
        json={"run_id": "real-run", "lock": False},
    )

    assert response.status_code == 409
    assert response.json()["error_code"] == "WHOLE_RUN_GOLDEN_PROMOTION_NOT_ALLOWED"


def test_ws6_predict_source_golden_save_is_rejected(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/skills/text-segmentation/golden",
        json={
            "node_id": "setup",
            "expected_output": {"prepared": True},
            "source": "predict",
            "lock": False,
        },
    )

    assert response.status_code == 409
    assert response.json()["error_code"] == "PREDICT_TRACE_CANNOT_BE_GOLDEN"
