"""缺陷复现:skill 的**两个身份**互相矛盾时,Studio 一声不吭。

`%APPDATA%\\AgentStudio\\skill_index.json` 的 key(注册 id)由**目录名**派生,而
`GRAPH.md` 的 frontmatter 里另有一个 `name:` 字段;两者之间**没有任何一致性校验**。
复制一个 skill 目录做副本时,副本的 `GRAPH.md` `name:` 仍写着源 skill 的名字,于是
同一棵树上"我叫什么"有两个互相打架的答案,而界面上什么都不显示。

2026-08-15 实测索引内容(真实机器):

    story-deconstruction-v3       -> D:\\coding\\skills\\story-deconstruction-v3
    story-deconstruction-v3-lab   -> D:\\coding\\skills\\story-deconstruction-v3-lab

而 `story-deconstruction-v3-lab/GRAPH.md` 里写的是 `name: story-deconstruction-v3`。
Copilot 读到这个 `name:` 就拿它当 skill_id 用,写到了另一棵树上。

证据(路径 + 行号,均为修复前的 main = 4443e95c):

- `apps/studio/tauri/src/native_fs.rs:1272-1290` —— `skill_id_from_workspace_root`:
  注册 id 完全由路径最后一段派生,不读 `GRAPH.md`。
- `apps/studio/backend/app/services/skills.py:341-351` ——
  `_studio_preflight_lint_errors` 是 Studio 自有 preflight 的唯一落点,当时只有
  runtime inputs 与 golden 两项,没有任何身份一致性检查。
- `AGENTS.md`「Compile/lint 单出口 + 全量聚合 + 同一份诊断」—— 索引的存在是 Studio
  的私有事实,engine 不知道,因此这条诊断只能是 Studio-owned preflight,不得进 engine。

验收判据:副本目录的 `name:` 与它的注册 id 不一致时,首屏/实时 lint 必须给出一条
指向 `GRAPH.md` 的 `name` 字段的告警;一致时保持安静;未注册的临时目录
(实时 lint 的沙箱副本)也必须保持安静,否则每敲一个键都会多出一条假诊断。
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core import config
from app.services.skills import lint_skill_path

_GRAPH_MD = """---
schema_version: "v0.3.0"
name: {name}
description: "identity fixture"
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

_IDENTITY_CODE = "STUDIO_MANIFEST_NAME_NOT_REGISTERED_ID"


def _write_skill(root: Path, *, manifest_name: str) -> Path:
    (root / "phases" / "init").mkdir(parents=True, exist_ok=True)
    (root / "GRAPH.md").write_text(_GRAPH_MD.format(name=manifest_name), encoding="utf-8")
    (root / "phases" / "init" / "SKILL.md").write_text(_SKILL_MD, encoding="utf-8")
    return root


def _register(skill_id: str, skill_dir: Path) -> None:
    index = json.loads(config.SKILL_INDEX_PATH.read_text(encoding="utf-8"))
    index[skill_id] = {"absolute_path": str(skill_dir), "l2_remote_url": ""}
    config.SKILL_INDEX_PATH.write_text(json.dumps(index), encoding="utf-8")


def _identity_diagnostics(result: object) -> list[object]:
    errors = getattr(result, "errors", [])
    return [error for error in errors if error.error_code == _IDENTITY_CODE]


def test_manifest_name_that_is_not_the_registered_id_is_reported(
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _ = studio_roots
    copy = _write_skill(skills_dir / "story-deconstruction-v3-lab", manifest_name="story-deconstruction-v3")
    _register("story-deconstruction-v3-lab", copy)

    diagnostics = _identity_diagnostics(lint_skill_path(copy))

    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic.severity == "warning"
    assert diagnostic.file == "GRAPH.md"
    assert diagnostic.field_path == "name"
    assert diagnostic.line == 3
    assert "story-deconstruction-v3-lab" in diagnostic.message
    assert "story-deconstruction-v3" in diagnostic.message


def test_matching_manifest_name_is_silent(studio_roots: tuple[Path, Path]) -> None:
    skills_dir, _ = studio_roots
    skill = _write_skill(skills_dir / "story-deconstruction-v3", manifest_name="story-deconstruction-v3")
    _register("story-deconstruction-v3", skill)

    assert _identity_diagnostics(lint_skill_path(skill)) == []


def test_unregistered_directory_is_silent(studio_roots: tuple[Path, Path], tmp_path: Path) -> None:
    """实时 lint 在 OS 临时目录里编译一份沙箱副本,那份树本就不在索引里。"""

    del studio_roots
    sandbox = _write_skill(tmp_path / "studio-lint-sandbox" / "skill", manifest_name="whatever")

    assert _identity_diagnostics(lint_skill_path(sandbox)) == []


def test_identity_warning_does_not_fail_the_lint(studio_roots: tuple[Path, Path]) -> None:
    """注册表卫生问题不是图缺陷:它不许把编译判失败。"""

    skills_dir, _ = studio_roots
    copy = _write_skill(skills_dir / "another-copy", manifest_name="story-deconstruction-v3")
    _register("another-copy", copy)

    result = lint_skill_path(copy)

    assert result.status == "passed"
    assert _identity_diagnostics(result)
