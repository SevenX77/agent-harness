"""Removal locks for the never-wired golden create paths (PM decision 2026-07-15).

The manual golden template (``GET /golden/template``) and the manual golden plan
(``POST /golden/manual/plan``) never had a UI caller; per the golden-eval design the
live create entries are editor diff Promote, Copilot analysis-bar auto-write, and
TracePanel run/per-node promote. Both dead endpoints are removed outright (no
backward compat) and must stay gone.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from tests.conftest import register_skill_index_entry

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
    register_skill_index_entry(AGENT_SKILL, skill_dir)
    return AGENT_SKILL


def test_golden_template_endpoint_is_removed(agent_skill_dir: str, client: TestClient) -> None:
    response = client.get(
        f"/api/skills/{agent_skill_dir}/golden/template",
        params={"node_id": "segment"},
    )

    # 404 when no route matches; 405 when the bare path only matches another
    # method's route template (e.g. DELETE /{golden_id}). Both mean "gone".
    assert response.status_code in (404, 405)


def test_manual_golden_plan_endpoint_is_removed(agent_skill_dir: str, client: TestClient) -> None:
    response = client.post(
        f"/api/skills/{agent_skill_dir}/golden/manual/plan",
        json={"node_id": "segment", "expected_output": {"segments": []}},
    )

    assert response.status_code in (404, 405)

    # Hitting the removed route persisted nothing.
    listing = client.get(f"/api/skills/{agent_skill_dir}/golden")
    assert listing.json() == []
