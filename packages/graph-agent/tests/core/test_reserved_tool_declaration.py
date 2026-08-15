"""声明内置工具 = 编译诊断(决议 2026-08-13 D9)。

四个内置框架工具(finish_task / read_reference / read_example / log_ambiguity)
由引擎无条件挂载,skill 文件里声明它们从来不是必要的 —— 但声明会让 Studio 把
它们渲染成「用户管理的工具」,连 finish_task 都长出删除按钮(用户 2026-08-13:
「finish task这个tool还能删掉?这不是搞笑吗?」)。声明不再静默通过:
`[F-v3-agent-tool-reserved]` 让删除按钮的语义翻转为「修复诊断的手段」。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.loader import SkillLoader


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _skill(root: Path, *, tools: list[str]) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: reserved-tool-probe
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
    required: [topic]
  outputs:
    type: object
    properties:
      answer:
        type: string
    required: [answer]
phases:
  - main
---
<phase depends_on="input" output>main</phase>
""",
    )
    tools_block = "tools:\n" + "".join(f"  - {name}\n" for name in tools) if tools else ""
    _write(
        root / "phases" / "main" / "SKILL.md",
        f"""---
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
    required: [topic]
  outputs:
    type: object
    properties:
      answer:
        type: string
    required: [answer]
{tools_block}---
<role>
Assistant.
</role>
<goal>
Produce the declared output.
</goal>
""",
    )


@pytest.mark.parametrize(
    "builtin",
    [
        "finish_task",
        "read_reference",
        "read_example",
        "log_ambiguity",
        # Migration decision 2026-08-15 §3.1/§3.2/§3.4: the revived cognitive
        # tools are framework-owned names too — unconditionally mounted
        # (ask_clarification / update_working_memory) or opt-in mounted via
        # context_access (query_working_memory / read_artifact). Either way a
        # SKILL must not claim the name for a business tool.
        "ask_clarification",
        "update_working_memory",
        "query_working_memory",
        "read_artifact",
    ],
)
def test_declaring_a_builtin_tool_is_a_compile_diagnostic(
    tmp_path: Path, mock_skill_resolver: object, builtin: str
) -> None:
    _skill(tmp_path, tools=[builtin])

    with pytest.raises(SkillLoadError) as exc_info:
        SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    assert exc_info.value.payload.code == "[F-v3-agent-tool-reserved]"
    assert builtin in str(exc_info.value)


def test_a_skill_without_builtin_declarations_compiles_clean(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _skill(tmp_path, tools=[])

    SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)
