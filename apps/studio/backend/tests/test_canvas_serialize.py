from __future__ import annotations

import difflib
import statistics
import time
from pathlib import Path

from fastapi.testclient import TestClient


def _phase_payload(depends_on: list[str] | None = None) -> dict[str, list[dict[str, object]]]:
    return {
        "phases": [
            {"id": "setup", "src": "phases/setup", "depends_on": [], "mode": "logic"},
            {
                "id": "final",
                "src": "phases/final",
                "depends_on": ["setup"] if depends_on is None else depends_on,
                "mode": "logic",
            },
        ]
    }


def _add_final_phase(skill_dir: Path) -> None:
    (skill_dir / "GRAPH.md").write_text(
        (skill_dir / "GRAPH.md").read_text(encoding="utf-8")
        + '<phase id="final" src="phases/final" depends_on="setup" />\n',
        encoding="utf-8",
    )
    phase_dir = skill_dir / "phases" / "final"
    phase_dir.mkdir(parents=True)
    (phase_dir / "LOGIC.md").write_text(
        """---
mode: logic
name: final
---
<python_callable>
finalize
</python_callable>
""",
        encoding="utf-8",
    )


def _changed_lines(before: str, after: str) -> tuple[int, int]:
    removed = 0
    added = 0
    for line in difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm=""):
        if line.startswith(("---", "+++", "@@")):
            continue
        if line.startswith("-"):
            removed += 1
        elif line.startswith("+"):
            added += 1
    return removed, added


def test_canvas_graph_serialize_returns_markdown_and_stays_fast(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _workspaces_dir = studio_roots
    _add_final_phase(skills_dir / "text-segmentation")

    elapsed_ms: list[float] = []
    response = None
    for _ in range(5):
        started = time.perf_counter()
        response = client.post("/api/skills/text-segmentation/graph/serialize", json=_phase_payload())
        elapsed_ms.append((time.perf_counter() - started) * 1000)

    assert response is not None
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["markdown_content"], str)
    assert body["phase_count"] == 2
    assert body["elapsed_ms"] >= 0
    assert '<phase id="final" src="phases/final" depends_on="setup" />' in body["markdown_content"]
    assert statistics.quantiles(elapsed_ms, n=100, method="inclusive")[94] < 500


def test_canvas_graph_serialize_depends_on_change_diffs_one_line(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _workspaces_dir = studio_roots
    skill_dir = skills_dir / "text-segmentation"
    _add_final_phase(skill_dir)
    original = (skill_dir / "GRAPH.md").read_text(encoding="utf-8")

    response = client.post(
        "/api/skills/text-segmentation/graph/serialize",
        json=_phase_payload(depends_on=[]),
    )

    assert response.status_code == 200
    markdown = response.json()["markdown_content"]
    assert _changed_lines(original, markdown) == (1, 1)
    assert '<phase id="final" src="phases/final" depends_on="" />' in markdown


def test_canvas_graph_serialize_missing_skill_returns_404(client: TestClient) -> None:
    response = client.post("/api/skills/nope/graph/serialize", json=_phase_payload())

    assert response.status_code == 404
    assert response.json()["error_code"] == "SKILL_NOT_FOUND"


def test_canvas_graph_serialize_rejects_missing_required_field(client: TestClient) -> None:
    payload = _phase_payload()
    del payload["phases"][0]["src"]

    response = client.post("/api/skills/text-segmentation/graph/serialize", json=payload)

    assert response.status_code == 422


def test_canvas_graph_serialize_rejects_invalid_mode(client: TestClient) -> None:
    payload = _phase_payload()
    payload["phases"][0]["mode"] = "bogus"

    response = client.post("/api/skills/text-segmentation/graph/serialize", json=payload)

    assert response.status_code == 422


def test_canvas_graph_serialize_rejects_duplicate_phase_id(client: TestClient) -> None:
    payload = _phase_payload()
    payload["phases"][1]["id"] = "setup"

    response = client.post("/api/skills/text-segmentation/graph/serialize", json=payload)

    assert response.status_code == 422


def test_canvas_graph_serialize_accepts_fan_in_depends_on(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _workspaces_dir = studio_roots
    _add_final_phase(skills_dir / "text-segmentation")

    response = client.post(
        "/api/skills/text-segmentation/graph/serialize",
        json=_phase_payload(depends_on=["setup", "branch-a", "branch-b"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["phase_count"] == 2
    assert '<phase id="final" src="phases/final" depends_on="setup,branch-a,branch-b" />' in body[
        "markdown_content"
    ]


def test_canvas_graph_serialize_openapi_schema_is_generated(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/api/skills/{skill_id}/graph/serialize"]["post"]

    assert (
        operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/SerializeGraphReq"
    )
    assert "PhaseRef" in schema["components"]["schemas"]
    assert "SerializeGraphRes" in schema["components"]["schemas"]
