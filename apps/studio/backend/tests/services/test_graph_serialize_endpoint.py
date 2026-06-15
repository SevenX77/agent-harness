"""End-to-end coverage for the canvas topology-save (/graph/serialize) path.

This path had NO end-to-end test, which is how the regression slipped through:
the service crammed GraphPhaseRef into GraphManifest.phases (list[str]) and
re-validated, raising ValidationError -> 500 -> the canvas left orphan phase
dirs because GRAPH.md was never updated. These tests pin the fixed behavior.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

_LOGIC_MD = (
    "---\nname: extra\nio:\n  inputs:\n    type: object\n    properties: {}\n"
    "  outputs:\n    type: object\n    properties: {}\nactions: [x]\nvalidator: false\n---\n<action>x</action>\n"
)


def test_serialize_adds_a_disconnected_phase_without_500(client: TestClient) -> None:
    # Mirrors "+ Add phase": the existing `setup` plus a freshly-added, not-yet-
    # connected `logic` phase (depends_on=[]). Must return 200 (not the old 500)
    # and register `logic` in BOTH the phases: list and the body.
    response = client.post(
        "/api/skills/text-segmentation/graph/serialize",
        json={
            "phases": [
                {"id": "setup", "src": "phases/setup", "mode": "logic", "depends_on": []},
                {"id": "logic", "src": "phases/logic", "mode": "logic", "depends_on": []},
            ],
            "expected_hash": None,
        },
    )

    assert response.status_code == 200, response.text
    markdown = response.json()["markdown_content"]
    assert "  - logic" in markdown
    assert '<phase depends_on="input" output>logic</phase>' in markdown
    # The existing phase survives.
    assert "  - setup" in markdown


def test_serialize_preserves_fan_in_depends_on(client: TestClient) -> None:
    # The regression the old linear-stub serializer corrupted: a phase that
    # depends on TWO upstreams must keep both, not be linearised into a chain.
    response = client.post(
        "/api/skills/text-segmentation/graph/serialize",
        json={
            "phases": [
                {"id": "setup", "src": "phases/setup", "mode": "logic", "depends_on": []},
                {"id": "left", "src": "phases/left", "mode": "logic", "depends_on": ["setup"]},
                {"id": "right", "src": "phases/right", "mode": "logic", "depends_on": ["setup"]},
                {"id": "join", "src": "phases/join", "mode": "logic", "depends_on": ["left", "right"]},
            ],
            "expected_hash": None,
        },
    )

    assert response.status_code == 200, response.text
    markdown = response.json()["markdown_content"]
    assert '<phase depends_on="left, right" output>join</phase>' in markdown
    # left/right both depend only on setup (not linearised).
    assert '<phase depends_on="setup">left</phase>' in markdown
    assert '<phase depends_on="setup">right</phase>' in markdown


def test_serialize_tolerates_a_phase_dir_not_yet_in_graph(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    # The exact canvas mid-add state: the new phase DIR exists on disk but GRAPH.md
    # doesn't list it yet. A full compile FATALs on the dir/frontmatter-must-match
    # rule; serialize must tolerate it (it is about to write the matching GRAPH.md)
    # and return the new topology, not 422/500.
    skills_dir, _ = studio_roots
    extra = skills_dir / "text-segmentation" / "phases" / "extra"
    extra.mkdir(parents=True)
    (extra / "LOGIC.md").write_text(_LOGIC_MD, encoding="utf-8")

    response = client.post(
        "/api/skills/text-segmentation/graph/serialize",
        json={
            "phases": [
                {"id": "setup", "src": "phases/setup", "mode": "logic", "depends_on": []},
                {"id": "extra", "src": "phases/extra", "mode": "logic", "depends_on": []},
            ],
            "expected_hash": None,
        },
    )

    assert response.status_code == 200, response.text
    assert "  - extra" in response.json()["markdown_content"]
