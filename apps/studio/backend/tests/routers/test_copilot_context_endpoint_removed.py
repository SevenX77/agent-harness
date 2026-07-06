from __future__ import annotations

from fastapi.testclient import TestClient


def test_copilot_context_endpoint_is_not_exposed(client: TestClient) -> None:
    response = client.post(
        "/api/skills/text-segmentation/copilot/context",
        json={"view": "Edit", "context": {"selected_node_id": "setup"}, "timestamp": 1},
    )

    assert response.status_code == 404
