"""P2 写工具收口(决议 2026-08-03 PR-K):

- `write_skill_file(skill_id, path, content, expected_hash?)`:与
  POST /api/skills/{id}/files/{path} 同一条 service(update_skill_file)——路径校验、
  冲突哈希、record_api_write 全套;CLI 会话不再裸 Write 绕过写边界。
- `bind_test_input(skill_id, name, content)`:测试输入落 .workspace/import_files/<name>/<name>.json
  (import = 运行时工作区数据,同 I/O 面板 import 链),随后 refresh_runtime_config 物化绑定——绑定是从 import 文件
  派生的,这是 I/O 面板同一条链,不另造第二种绑定写法。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from app.services import copilot_tools

GRAPH_MD = """---
schema_version: "v0.3.0"
name: write-skill
description: write tools fixture
io:
  inputs:
    type: object
    required: [chapters]
    properties:
      chapters:
        type: array
  outputs:
    type: object
    properties:
      result:
        type: object
phases:
  - work
---
<phase depends_on="input" output>work</phase>
"""


def _payload(result: dict) -> dict:
    return json.loads(result["content"][0]["text"])


@pytest.fixture()
def seeded_skill(studio_roots: tuple[Path, Path]) -> Path:
    skills_dir, _ = studio_roots
    result = asyncio.run(copilot_tools.create_skill_tool.handler({"skill_id": "write-skill"}))
    assert "is_error" not in result
    return skills_dir / "write-skill"


def test_write_skill_file_persists_and_returns_hash(seeded_skill: Path) -> None:
    result = asyncio.run(
        copilot_tools.write_skill_file_tool.handler(
            {"skill_id": "write-skill", "path": "GRAPH.md", "content": GRAPH_MD}
        )
    )
    assert "is_error" not in result
    payload = _payload(result)
    assert payload["path"] == "GRAPH.md"
    assert payload["hash"]
    assert (seeded_skill / "GRAPH.md").read_text(encoding="utf-8") == GRAPH_MD


def test_write_skill_file_rejects_escape_paths(seeded_skill: Path) -> None:
    del seeded_skill
    result = asyncio.run(
        copilot_tools.write_skill_file_tool.handler(
            {"skill_id": "write-skill", "path": "../outside.md", "content": "x"}
        )
    )
    assert result.get("is_error") is True


def test_write_skill_file_surfaces_hash_conflict(seeded_skill: Path) -> None:
    del seeded_skill
    ok = asyncio.run(
        copilot_tools.write_skill_file_tool.handler(
            {"skill_id": "write-skill", "path": "tools/helper.py", "content": "v1"}
        )
    )
    stale_hash = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    conflict = asyncio.run(
        copilot_tools.write_skill_file_tool.handler(
            {
                "skill_id": "write-skill",
                "path": "tools/helper.py",
                "content": "v2",
                "expected_hash": stale_hash,
            }
        )
    )
    assert "is_error" not in ok
    assert conflict.get("is_error") is True
    assert "conflict" in conflict["content"][0]["text"].lower() or "冲突" in conflict["content"][0]["text"]


def test_bind_test_input_writes_import_file_and_materializes_bindings(
    seeded_skill: Path,
) -> None:
    write = asyncio.run(
        copilot_tools.write_skill_file_tool.handler(
            {"skill_id": "write-skill", "path": "GRAPH.md", "content": GRAPH_MD}
        )
    )
    assert "is_error" not in write

    result = asyncio.run(
        copilot_tools.bind_test_input_tool.handler(
            {
                "skill_id": "write-skill",
                "name": "case-a",
                "content": {"chapters": [{"title": "one"}]},
            }
        )
    )
    assert "is_error" not in result
    payload = _payload(result)
    assert (seeded_skill / ".workspace" / "import_files" / "case-a" / "case-a.json").is_file()
    # 绑定由 import 扫描派生:chapters 是声明的图输入,应当被绑到 import 文件。
    assert "chapters" in payload["bindings"]["root"]
    assert payload["bindings"]["root"]["chapters"]["path"].startswith("import_files/case-a")


def test_bind_test_input_rejects_bad_names_and_non_object_content(
    seeded_skill: Path,
) -> None:
    del seeded_skill
    bad_name = asyncio.run(
        copilot_tools.bind_test_input_tool.handler(
            {"skill_id": "write-skill", "name": "../evil", "content": {}}
        )
    )
    assert bad_name.get("is_error") is True

    bad_content = asyncio.run(
        copilot_tools.bind_test_input_tool.handler(
            {"skill_id": "write-skill", "name": "case-b", "content": "not-a-dict"}
        )
    )
    assert bad_content.get("is_error") is True


def test_write_tools_are_registered_and_approval_gated() -> None:
    from app.services.copilot import _DECLARATIVE_ALLOWED_TOOLS, _MCP_APPROVAL_WRITE_TOOLS
    from app.services.copilot_tools import _copilot_mcp_tools

    tool_names = {tool.name for tool in _copilot_mcp_tools()}
    for name in ("write_skill_file", "bind_test_input"):
        assert name in tool_names
        assert f"mcp__studio__{name}" in _MCP_APPROVAL_WRITE_TOOLS
        assert f"mcp__studio__{name}" not in _DECLARATIVE_ALLOWED_TOOLS
