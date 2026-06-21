"""N4 atom #33 endpoints: GET golden template + POST manual golden plan.

GET /api/skills/{id}/golden/template?node_id= returns a schema-valid empty stub.
POST /api/skills/{id}/golden/manual/plan returns the GoldenBaselinePlan (file set) the
Rust native-fs sole writer writes per file on desktop (D12). Plan-only, no disk write —
there is no Python HTTP disk-write endpoint for the manual golden (no browser fallback).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

if TYPE_CHECKING:
    from pathlib import Path

AGENT_SKILL = "agent-golden-skill"


@pytest.fixture
def agent_skill_dir(studio_roots: tuple[Path, Path]) -> str:
    skills_dir, _workspaces = studio_roots
    skill_dir = skills_dir / AGENT_SKILL
    (skill_dir / "phases" / "segment").mkdir(parents=True)
    (skill_dir / "GRAPH.md").write_text(
        """---
schema_version: "v0.3.0"
name: agent-golden-skill
description: Agent node with output schema
io:
  inputs:
    type: object
    required: [chapter_content]
    properties:
      chapter_content:
        type: string
    additionalProperties: false
  outputs:
    type: object
    required: [segments]
    properties:
      segments:
        type: array
        items:
          type: object
    additionalProperties: false
phases:
  - segment
---
<phase depends_on="input" output>segment</phase>
""",
        encoding="utf-8",
    )
    (skill_dir / "phases" / "segment" / "SKILL.md").write_text(
        """---
llm_role: analyst
phase_config:
  io:
    inputs:
      type: object
      required: [chapter_content]
      properties:
        chapter_content:
          type: string
    outputs:
      type: object
      required: [segments]
      properties:
        segments:
          type: array
          items:
            type: object
  tools: []
  max_iterations: 5
---
<role>seg editor</role>
<goal>segment</goal>
<step id="S1" name="segment">do it</step>
""",
        encoding="utf-8",
    )
    return AGENT_SKILL


def test_get_golden_template_endpoint(agent_skill_dir: str, client: TestClient) -> None:
    response = client.get(
        f"/api/skills/{agent_skill_dir}/golden/template",
        params={"node_id": "segment"},
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"skill_id", "node_id", "schema", "template"}
    assert body["node_id"] == "segment"
    assert "segments" in body["schema"]["properties"]
    assert body["template"]["segments"] == []


def test_manual_golden_disk_write_endpoint_is_removed(
    agent_skill_dir: str,
    client: TestClient,
) -> None:
    """There is no Python HTTP disk-write endpoint for the manual golden (D12).

    The manual golden write goes through the Rust native-fs sole writer via the
    plan endpoint; the old browser-fallback POST /golden/manual disk-write route is
    gone, so it must 404/405 rather than persist anything.
    """
    response = client.post(
        f"/api/skills/{agent_skill_dir}/golden/manual",
        json={"node_id": "segment", "expected_output": {"segments": []}},
        headers={"X-Studio-Write-Fallback": "browser"},
    )

    assert response.status_code in (404, 405)

    # Nothing was persisted by hitting the removed endpoint.
    listing = client.get(f"/api/skills/{agent_skill_dir}/golden")
    assert listing.json() == []


def test_post_manual_golden_plan_returns_plan_without_writing(
    agent_skill_dir: str,
    client: TestClient,
) -> None:
    """The /manual/plan endpoint returns a GoldenBaselinePlan and is plan-only.

    Parity with the promote /golden/plan endpoint: plan-only, no write guard (the
    native-fs Rust writer performs the actual write per plan file on desktop), and it
    must NOT persist the golden to disk.
    """
    response = client.post(
        f"/api/skills/{agent_skill_dir}/golden/manual/plan",
        json={"node_id": "segment", "expected_output": {"segments": [{"start": 0}]}},
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"baseline", "files"}
    assert body["baseline"]["source_run_id"] is None
    file_paths = [f["path"] for f in body["files"]]
    assert file_paths == [
        ".workspace/golden/segment/baseline.json",
        ".workspace/golden/segment/report.json",
        ".workspace/golden/segment/cases/segment.json",
    ]

    # Plan-only: no golden was written to disk by planning.
    listing = client.get(f"/api/skills/{agent_skill_dir}/golden")
    assert listing.json() == []
