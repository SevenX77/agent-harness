"""End-to-end coverage for the canvas topology-save (/graph/serialize) path.

This path had NO end-to-end test, which is how the regression slipped through:
the service crammed GraphPhaseRef into GraphManifest.phases (list[str]) and
re-validated, raising ValidationError -> 500 -> the canvas left orphan phase
dirs because GRAPH.md was never updated. These tests pin the fixed behavior.
"""

from __future__ import annotations

from pathlib import Path

from app.services.skills import _graph_content_hash
from fastapi.testclient import TestClient

_LOGIC_MD = (
    "---\nname: extra\nio:\n  inputs:\n    type: object\n    properties: {}\n"
    "  outputs:\n    type: object\n    properties: {}\nactions: [x]\nvalidator: false\n---\n<action>x</action>\n"
)

# A drilled subgraph GRAPH.md that shares the bare name "text-segmentation" with
# the conftest public skill of the same name, but has DIFFERENT content (so a
# different content hash). Resolving the bare id alone finds the public skill.
_SUBGRAPH_GRAPH_MD = (
    '---\n'
    'schema_version: "v0.3.0"\n'
    "name: text-segmentation\n"
    "description: drilled subgraph copy\n"
    "io:\n"
    "  inputs:\n"
    "    type: object\n"
    "    properties:\n"
    "      input_text:\n"
    "        type: string\n"
    "    required: [input_text]\n"
    "    additionalProperties: false\n"
    "  outputs:\n"
    "    type: object\n"
    "    properties:\n"
    "      prepared:\n"
    "        type: boolean\n"
    "    required: [prepared]\n"
    "    additionalProperties: true\n"
    "phases:\n"
    "  - setup\n"
    "---\n"
    '<phase depends_on="input" output>setup</phase>\n'
)


def _make_colliding_subgraph(skills_dir: Path) -> Path:
    subgraph_dir = skills_dir / "story-deconstruction" / "subgraph" / "text-segmentation"
    subgraph_dir.mkdir(parents=True)
    (subgraph_dir / "GRAPH.md").write_text(_SUBGRAPH_GRAPH_MD, encoding="utf-8")
    return subgraph_dir


def test_serialize_uses_workspace_root_for_drilled_subgraph(
    client: TestClient, studio_roots: tuple[Path, Path]
) -> None:
    # The drilled-subgraph fix: the canvas passes the subgraph's absolute path as
    # workspace_root, so the serializer reads THAT GRAPH.md instead of the
    # name-colliding public skill the bare id would resolve to.
    skills_dir, _ = studio_roots
    subgraph_dir = _make_colliding_subgraph(skills_dir)
    expected_hash = _graph_content_hash(_SUBGRAPH_GRAPH_MD)

    response = client.post(
        "/api/skills/text-segmentation/graph/serialize",
        json={
            "phases": [
                {"id": "setup", "src": "phases/setup", "depends_on": []},
                {"id": "logic", "src": "phases/logic", "depends_on": []},
            ],
            "expected_hash": expected_hash,
            "workspace_root": str(subgraph_dir),
        },
    )

    assert response.status_code == 200, response.text
    # current_hash matches the SUBGRAPH file, proving the serializer read that
    # GRAPH.md (the colliding public skill has different content -> different hash).
    assert response.json()["current_hash"] == expected_hash
    assert "  - logic" in response.json()["markdown_content"]


def test_serialize_bare_id_cannot_disambiguate_colliding_subgraph(
    client: TestClient, studio_roots: tuple[Path, Path]
) -> None:
    # Documents the drilled-subgraph 409 the workspace_root path fixes: without a
    # path the bare id resolves the PUBLIC text-segmentation skill, whose content
    # (and hash) differ from the subgraph the canvas is editing -> snapshot_conflict.
    skills_dir, _ = studio_roots
    _make_colliding_subgraph(skills_dir)
    subgraph_hash = _graph_content_hash(_SUBGRAPH_GRAPH_MD)

    response = client.post(
        "/api/skills/text-segmentation/graph/serialize",
        json={
            "phases": [{"id": "setup", "src": "phases/setup", "depends_on": []}],
            "expected_hash": subgraph_hash,
        },
    )

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "snapshot_conflict"


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
    assert "<phase>logic</phase>" in markdown
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
    assert '<phase depends_on="left, right">join</phase>' in markdown
    # left/right both depend only on setup (not linearised).
    assert '<phase depends_on="setup">left</phase>' in markdown
    assert '<phase depends_on="setup">right</phase>' in markdown


def test_serialize_accepts_canonical_topology_without_node_mode(client: TestClient) -> None:
    # GRAPH.md owns only topology facts. The phase type is derived from the
    # phase file (LOGIC.md/SUBGRAPH.md/SKILL.md), so the serialize endpoint must
    # not require a UI/editor `mode` field to write depends_on/output.
    response = client.post(
        "/api/skills/text-segmentation/graph/serialize",
        json={
            "phases": [
                {"id": "setup", "src": "phases/setup", "depends_on": ["input"], "output": True},
            ],
            "expected_hash": None,
        },
    )

    assert response.status_code == 200, response.text
    markdown = response.json()["markdown_content"]
    assert '<phase depends_on="input" output>setup</phase>' in markdown


def test_serialize_ignores_legacy_node_mode(client: TestClient) -> None:
    response = client.post(
        "/api/skills/text-segmentation/graph/serialize",
        json={
            "phases": [
                {
                    "id": "setup",
                    "src": "phases/setup",
                    "depends_on": ["input"],
                    "output": True,
                    "mode": "agent",
                },
            ],
            "expected_hash": None,
        },
    )

    assert response.status_code == 200, response.text
    assert '<phase depends_on="input" output>setup</phase>' in response.json()["markdown_content"]


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


def test_serialize_preserves_unknown_graph_markdown_sections(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _ = studio_roots
    graph_md = skills_dir / "text-segmentation" / "GRAPH.md"
    graph_md.write_text(
        """---
schema_version: "v0.3.0"
name: text-segmentation
description: Text segments
x-ui-state:
  nodes:
    setup:
      x: 10
      y: 20
metadata:
  owner: studio
iterate:
  max: 3
io:
  inputs:
    type: object
    properties:
      input_text:
        type: string
    required: [input_text]
  outputs:
    type: object
    properties:
      prepared:
        type: boolean
    required: [prepared]
phases:
  - setup
---
<!-- keep: intro comment -->
<note>Preserve this unknown body block.</note>

<phase depends_on="input" output>setup</phase>

<!-- keep: trailing comment -->
""",
        encoding="utf-8",
    )

    response = client.post(
        "/api/skills/text-segmentation/graph/serialize",
        json={
            "phases": [
                {"id": "setup", "src": "phases/setup", "mode": "logic", "depends_on": []},
                {"id": "review", "src": "phases/review", "mode": "logic", "depends_on": ["setup"]},
            ],
            "expected_hash": None,
        },
    )

    assert response.status_code == 200, response.text
    markdown = response.json()["markdown_content"]
    assert "x-ui-state:" in markdown
    assert "metadata:" in markdown
    assert "iterate:" in markdown
    assert "<!-- keep: intro comment -->" in markdown
    assert "<note>Preserve this unknown body block.</note>" in markdown
    assert "<!-- keep: trailing comment -->" in markdown
    assert "  - review" in markdown
    assert '<phase depends_on="setup">review</phase>' in markdown


def test_serialize_conflict_reports_current_disk_phase_count(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _ = studio_roots
    graph_md = skills_dir / "text-segmentation" / "GRAPH.md"
    stale_content = graph_md.read_text(encoding="utf-8")
    graph_md.write_text(
        """---
schema_version: "v0.3.0"
name: text-segmentation
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
phases:
  - setup
  - review
---
<phase depends_on="input">setup</phase>
<phase depends_on="setup" output>review</phase>
""",
        encoding="utf-8",
    )

    response = client.post(
        "/api/skills/text-segmentation/graph/serialize",
        json={
            "phases": [
                {"id": "setup", "src": "phases/setup", "mode": "logic", "depends_on": []},
            ],
            "expected_hash": _graph_content_hash(stale_content),
        },
    )

    assert response.status_code == 409, response.text
    assert response.json()["current_phase_count"] == 2
