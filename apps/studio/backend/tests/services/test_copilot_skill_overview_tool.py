"""MoirAI 第一步就能认识一个 skill 的结构,而不是去磁盘上摸文件。

P4-G(决议 2026-08-03 PR-G):`get_skill_overview(skill_id)` 返回 manifest 摘要 +
phase 列表 + 每 phase 的 io 字段名与类型 + validator 有无 + llm_role。**只给结构
不给正文**(D6 只读工具一律有界)——正文归 Read 工具,正确性归 compile_skill。
数据源与前端 `GET /api/skills/{id}` 同一条编译路径,不自建第二份读取逻辑。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

GRAPH_MD = """---
schema_version: "v0.3.0"
name: overview-skill
description: structure probe fixture
llm_role: graph-default-role
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
    additionalProperties: true
phases:
  - segment
---
<phase depends_on="input" output>segment</phase>
"""

SKILL_MD = """---
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
      headline:
        type: string
llm_role: segment-role
validator: true
tools: []
max_iterations: 5
---
<role>seg editor SECRET_BODY_MARKER</role>
<goal>segment the chapter</goal>
<step id="S1" name="segment">do it</step>
"""


def _write_skill(skill_dir: Path) -> None:
    (skill_dir / "phases" / "segment").mkdir(parents=True)
    (skill_dir / "GRAPH.md").write_text(GRAPH_MD, encoding="utf-8")
    (skill_dir / "phases" / "segment" / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")


def _overview(monkeypatch: pytest.MonkeyPatch, skill_dir: Path, skill_id: str = "overview-skill") -> dict[str, Any]:
    from app.services import copilot_tools, skills

    monkeypatch.setattr(skills, "ensure_workspace_skill_dir", lambda _skill_id: skill_dir)
    result = asyncio.run(copilot_tools.get_skill_overview_tool.handler({"skill_id": skill_id}))
    return result


def _payload(result: dict[str, Any]) -> Any:
    return json.loads(result["content"][0]["text"])


def test_overview_projects_structure_for_every_phase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skill_dir = tmp_path / "overview-skill"
    _write_skill(skill_dir)

    payload = _payload(_overview(monkeypatch, skill_dir))

    assert payload["name"] == "overview-skill"
    assert payload["graph_llm_role"] == "graph-default-role"
    assert payload["phase_count"] == 1

    # graph 边界:字段名 + 类型 + 是否必填,不是整份 JSON Schema 转储。
    assert payload["graph_io"]["inputs"] == [
        {"name": "chapter_content", "type": "string", "required": True}
    ]
    assert {"name": "segments", "type": "array", "required": True} in payload["graph_io"]["outputs"]

    [phase] = payload["phases"]
    assert phase["id"] == "segment"
    assert phase["mode"] == "agent"
    assert phase["validator"] is True
    assert phase["llm_role"] == "segment-role"
    assert phase["depends_on"] == ["input"]
    assert phase["is_graph_output"] is True
    assert {"name": "headline", "type": "string", "required": False} in phase["outputs"]


def test_overview_gives_structure_never_body_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # D6:只读工具一律有界。正文(role/goal/step 文本)一个字都不得出现——
    # 要看正文用 Read 工具,这里只回答"这个 skill 长什么形状"。
    skill_dir = tmp_path / "overview-skill"
    _write_skill(skill_dir)

    raw_text = _overview(monkeypatch, skill_dir)["content"][0]["text"]

    assert "SECRET_BODY_MARKER" not in raw_text
    assert "segment the chapter" not in raw_text


def test_overview_fails_closed_on_missing_skill_id(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import copilot_tools

    result = asyncio.run(copilot_tools.get_skill_overview_tool.handler({"skill_id": "  "}))
    assert result.get("is_error") is True


def test_overview_points_at_compile_when_the_skill_does_not_parse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 结构总览不复述完整诊断(那是 compile_skill 的职责,诊断 SSOT),但必须
    # fail-fast 并把会话指向正确的下一步,而不是回一份半真半假的结构。
    skill_dir = tmp_path / "broken-skill"
    skill_dir.mkdir()
    (skill_dir / "GRAPH.md").write_text("---\nnot: [valid\n---\n", encoding="utf-8")

    result = _overview(monkeypatch, skill_dir, skill_id="broken-skill")

    assert result.get("is_error") is True
    assert "compile_skill" in result["content"][0]["text"]


def test_overview_is_pre_allowed_read_tool() -> None:
    # 免审批读工具:进 _DECLARATIVE_ALLOWED_TOOLS(D6 读免审批),
    # 且在 CLI 工具面(cli_mcp_surface 不排除它)。
    from app.services import copilot
    from app.services.cli_mcp_surface import cli_tool_names

    assert "mcp__studio__get_skill_overview" in copilot._ZERO_APPROVAL_TOOLS
    assert "get_skill_overview" in cli_tool_names()
