"""N4 atom #33 endpoints: GET golden template + POST manual golden write.

GET /api/skills/{id}/golden/template?node_id= returns a schema-valid empty stub.
POST /api/skills/{id}/golden/manual writes an author-defined golden keyed by node_id,
behind the same browser-write-fallback guard as the run-promote write (atom #36 ②).
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


def test_post_manual_golden_requires_browser_write_fallback(
    agent_skill_dir: str,
    client: TestClient,
) -> None:
    """Without the browser-write-fallback header the manual write is 409 (atom #36 ②)."""
    response = client.post(
        f"/api/skills/{agent_skill_dir}/golden/manual",
        json={"node_id": "segment", "expected_output": {"segments": []}},
    )

    assert response.status_code == 409
    assert response.json()["error_code"] == "NATIVE_FS_REQUIRED"


def test_post_manual_golden_writes_node_golden(
    agent_skill_dir: str,
    client: TestClient,
) -> None:
    response = client.post(
        f"/api/skills/{agent_skill_dir}/golden/manual",
        json={"node_id": "segment", "expected_output": {"segments": [{"start": 0}]}},
        headers={"X-Studio-Write-Fallback": "browser"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source_run_id"] is None
    assert [case["node_id"] for case in body["cases"]] == ["segment"]

    listing = client.get(f"/api/skills/{agent_skill_dir}/golden")
    node_ids = {
        case["node_id"]
        for baseline in listing.json()
        for case in baseline.get("cases", [])
    }
    assert "segment" in node_ids
