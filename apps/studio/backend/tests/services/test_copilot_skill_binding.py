"""缺陷复现:Copilot 的 MCP 工具把 `skill_id` 当成模型可填参数,模型只能猜,
于是写操作静默落到**另一个** skill 目录里。

可观察表现(2026-08-15 实证,两次触发,都只被人工审批卡拦下):Studio Copilot
打开工作区 `D:\\coding\\skills\\story-deconstruction-v3-lab`,读该工作区的
`GRAPH.md` 看到 `name: story-deconstruction-v3`,于是拿这个值当 `skill_id` 调
`write_skill_file`,实测参数
``{"skill_id": "story-deconstruction-v3", "path": "subgraph/global-synthesis/...",
"expected_hash": "skip", "content": "..."}``;该 skill_id 在
`%APPDATA%\\AgentStudio\\skill_index.json` 里解析到的是另一个目录
`D:\\coding\\skills\\story-deconstruction-v3`。

证据(路径 + 行号,均为修复前的 main = 4443e95c):

- `apps/studio/backend/app/services/copilot_tools.py:256-266` —— `write_skill_file`
  的 input_schema 把 ``"skill_id"`` 列进 ``required``,即这个值由模型填写。
- `apps/studio/backend/app/services/copilot_tools.py:272` ——
  ``skill_id = str(args.get("skill_id", "")).strip()``:处理器直接取模型给的值,
  与会话打开的工作区没有任何关系。
- `apps/studio/backend/app/services/copilot.py:1100-1136` —— 会话本身早就持有权威
  skill_id(``stream_query(skill_id, ...)`` 的入参),并据它解析出唯一的
  ``resolved_workspace``;也就是说这个事实有唯一 owner,却仍然去问模型。
- `apps/studio/tauri/src/native_fs.rs:1455-1461` —— 同一类缺陷在 CLI 会话侧已被判定
  并修复过,注释原文:「A CLI session used to be told nothing about which skill it
  was bound to, so the model guessed one from the manifest ``name:`` — and once
  guessed the id of a DIFFERENT, protected skill and edited that instead (exp-B R0,
  2026-07-31). The index is the registry that answers this, so the id is read from
  there rather than accepted from whoever opened the session.」

验收判据(本文件的两组用例):副本 `<skill>-lab` 的 `GRAPH.md` 仍写着源 skill 的
`name:`,模型照着它填 `skill_id` 也不可能写到源 skill 的目录里。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from app.core import config
from app.services import copilot_tools
from app.services.copilot_skill_binding import (
    CopilotSkillBinding,
    bind_tools_to_open_skill,
)

_GRAPH_MD = """---
schema_version: "v0.3.0"
name: {name}
description: "copy under test"
io:
  inputs:
    type: object
    properties: {{}}
  outputs:
    type: object
    properties: {{}}
phases:
  - init
---
<phase depends_on="input" output>init</phase>
"""

_SKILL_MD = """---
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
tools: []
max_iterations: 10
---
<role>r</role>
<goal>g</goal>

<step id="S1" name="s">s</step>

<protocol id="P1">p</protocol>
"""


def _write_copy(root: Path, *, manifest_name: str) -> Path:
    """A skill tree whose GRAPH.md `name:` may differ from its directory name."""

    (root / "phases" / "init").mkdir(parents=True, exist_ok=True)
    (root / "GRAPH.md").write_text(_GRAPH_MD.format(name=manifest_name), encoding="utf-8")
    (root / "phases" / "init" / "SKILL.md").write_text(_SKILL_MD, encoding="utf-8")
    return root


@pytest.fixture
def two_copies(studio_roots: tuple[Path, Path]) -> tuple[Path, Path]:
    """Source skill + a copy whose manifest `name:` still points at the source.

    This is exactly the shape that produced the incident: copying a skill
    directory does not rewrite `GRAPH.md`'s `name:`, so the copy's manifest
    advertises the SOURCE skill's id.
    """

    skills_dir, _ = studio_roots
    source = _write_copy(skills_dir / "story-deconstruction-v3", manifest_name="story-deconstruction-v3")
    copy = _write_copy(skills_dir / "story-deconstruction-v3-lab", manifest_name="story-deconstruction-v3")

    index = json.loads(config.SKILL_INDEX_PATH.read_text(encoding="utf-8"))
    index["story-deconstruction-v3"] = {"absolute_path": str(source), "l2_remote_url": ""}
    index["story-deconstruction-v3-lab"] = {"absolute_path": str(copy), "l2_remote_url": ""}
    config.SKILL_INDEX_PATH.write_text(json.dumps(index), encoding="utf-8")
    return source, copy


def _bound_tool(name: str, binding: CopilotSkillBinding):  # type: ignore[no-untyped-def]
    for bound in bind_tools_to_open_skill(copilot_tools.copilot_mcp_tools(), binding):
        if bound.name == name:
            return bound
    raise AssertionError(f"tool {name!r} is not on the Copilot MCP surface")


def test_bound_tools_do_not_offer_skill_id_to_the_model(two_copies: tuple[Path, Path]) -> None:
    """让非法状态不可表示:模型面前根本没有 skill_id 这个参数可填。"""

    _source, copy = two_copies
    binding = CopilotSkillBinding(skill_id="story-deconstruction-v3-lab", workspace_root=copy)

    bound = bind_tools_to_open_skill(copilot_tools.copilot_mcp_tools(), binding)

    assert bound, "binding must not drop the tool surface"
    for tool in bound:
        schema = tool.input_schema
        assert isinstance(schema, dict)
        properties = schema.get("properties") if schema.get("type") == "object" else schema
        assert isinstance(properties, dict)
        assert "skill_id" not in properties, f"{tool.name} still asks the model for skill_id"


def test_write_lands_in_the_bound_workspace_when_the_model_names_another_skill(
    two_copies: tuple[Path, Path],
) -> None:
    """本缺陷的验收判据:模型填源 skill 的 id,写入仍只能落在打开的副本里。"""

    source, copy = two_copies
    binding = CopilotSkillBinding(skill_id="story-deconstruction-v3-lab", workspace_root=copy)
    write_tool = _bound_tool("write_skill_file", binding)

    result = asyncio.run(
        write_tool.handler(
            {
                # 模型从副本的 GRAPH.md `name:` 猜来的源 skill id — 必须无效。
                "skill_id": "story-deconstruction-v3",
                "path": "phases/init/SKILL.md",
                "content": _SKILL_MD.replace("<role>r</role>", "<role>edited</role>"),
            }
        )
    )

    assert "is_error" not in result, result
    assert "edited" in (copy / "phases" / "init" / "SKILL.md").read_text(encoding="utf-8")
    assert "edited" not in (source / "phases" / "init" / "SKILL.md").read_text(encoding="utf-8")
    assert json.loads(result["content"][0]["text"])["skill_id"] == "story-deconstruction-v3-lab"


def test_read_is_bound_to_the_open_workspace_too(two_copies: tuple[Path, Path]) -> None:
    """读也绑定:否则模型会拿另一份树的内容当成打开的这份来推理。"""

    source, copy = two_copies
    (source / "MARKER.md").write_text("source-only", encoding="utf-8")
    (copy / "MARKER.md").write_text("copy-only", encoding="utf-8")
    binding = CopilotSkillBinding(skill_id="story-deconstruction-v3-lab", workspace_root=copy)

    result = asyncio.run(
        _bound_tool("read_skill_file", binding).handler(
            {"skill_id": "story-deconstruction-v3", "path": "MARKER.md"}
        )
    )

    assert "is_error" not in result, result
    assert json.loads(result["content"][0]["text"])["content"] == "copy-only"


def test_bound_tool_refuses_when_the_index_repoints_the_bound_id(
    two_copies: tuple[Path, Path],
) -> None:
    """索引 key = 裸目录名,可被后开的同名目录顶掉;此时会话 id 解析到别处。

    绑定记的是 (id, 打开的目录) 两件事,所以这种顶替是可观察的:工具在跑之前
    自己发现 id 已不再解析到本会话的工作区,拒绝执行,而不是写到顶替者那里。
    """

    source, copy = two_copies
    binding = CopilotSkillBinding(skill_id="story-deconstruction-v3-lab", workspace_root=copy)
    write_tool = _bound_tool("write_skill_file", binding)

    index = json.loads(config.SKILL_INDEX_PATH.read_text(encoding="utf-8"))
    index["story-deconstruction-v3-lab"] = {"absolute_path": str(source), "l2_remote_url": ""}
    config.SKILL_INDEX_PATH.write_text(json.dumps(index), encoding="utf-8")

    result = asyncio.run(
        write_tool.handler({"path": "phases/init/SKILL.md", "content": "hijacked"})
    )

    assert result["is_error"] is True
    message = result["content"][0]["text"]
    assert "story-deconstruction-v3-lab" in message
    assert str(copy) in message
    assert "hijacked" not in (source / "phases" / "init" / "SKILL.md").read_text(encoding="utf-8")


def test_create_skill_still_mints_a_new_id(two_copies: tuple[Path, Path]) -> None:
    """建新 skill 不是对"打开的这个 skill"的操作:它的 id 是新铸的,保留为参数。

    分界线因此是可陈述的:`skill_id` 在整个 MCP 面上永不由模型给出;要铸一个新
    skill 的工具用 `new_skill_id`。
    """

    _source, copy = two_copies
    binding = CopilotSkillBinding(skill_id="story-deconstruction-v3-lab", workspace_root=copy)

    create = _bound_tool("create_skill", binding)
    schema = create.input_schema
    assert isinstance(schema, dict)
    assert "new_skill_id" in schema
    assert "skill_id" not in schema

    result = asyncio.run(create.handler({"new_skill_id": "freshly-minted"}))

    assert "is_error" not in result, result
    assert json.loads(result["content"][0]["text"])["skill_id"] == "freshly-minted"


def test_mcp_server_requires_a_binding() -> None:
    """会话的 MCP server 不存在"未绑定"这种状态,不能靠调用方记得传。"""

    with pytest.raises(TypeError):
        copilot_tools.build_copilot_mcp_servers()  # type: ignore[call-arg]
