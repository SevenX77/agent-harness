from __future__ import annotations

from pathlib import Path

from graph_agent import compile_skill

REPO_ROOT = Path(__file__).resolve().parents[4]
GUIDE = REPO_ROOT / "docs" / "graph_agent_docs" / "SKILL_AUTHORING_GUIDE.md"
HELLO_WORLD = REPO_ROOT / "skills" / "hello-world"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_guide_synced_minimal_example(root: Path) -> None:
    """Parser-compatible equivalent of SKILL_AUTHORING_GUIDE.md section 8."""

    _write(
        root / "GRAPH.md",
        """---
schema_version: "2.1"
name: hello-world
description: "Minimal V2.1 smoke fixture for parser, tools, and finish_task."
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />
<phase id="greet" src="phases/greet" depends_on="" />
""",
    )
    _write(
        root / "io" / "inputs.json",
        """{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "user_name": {"type": "string"}
  },
  "required": ["user_name"]
}
""",
    )
    _write(
        root / "io" / "outputs.json",
        """{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "greeting": {"type": "string"}
  },
  "required": ["greeting"]
}
""",
    )
    _write(
        root / "phases" / "greet" / "SKILL.md",
        """---
mode: skill
name: greet
tools:
  - generate_greeting
---
<system_prompt>
你是一个友善的助手。请调用 generate_greeting 工具生成问候语，然后调用 finish_task 结束。
</system_prompt>
<user_prompt>
请为 {user_name} 生成问候语。
</user_prompt>
<exit_contract>
调用 generate_greeting 后，用 finish_task 提交 `## greeting`。
</exit_contract>
""",
    )
    _write(
        root / "phases" / "greet" / "tools" / "generate_greeting.py",
        "def generate_greeting(user_name: str) -> str:\n"
        '    """Generate a deterministic greeting."""\n'
        '    return f"Hello, {user_name}!"\n',
    )


def test_skill_authoring_guide_minimal_example_matches_hello_world(tmp_path: Path) -> None:
    guide_text = GUIDE.read_text(encoding="utf-8")
    assert "## 8. 完整 hello-world 示例" in guide_text
    assert "skills/hello-world/GRAPH.md" in guide_text

    _write_guide_synced_minimal_example(tmp_path)
    guide_compiled = compile_skill(tmp_path, cache=False)
    live_compiled = compile_skill(HELLO_WORLD, cache=False)

    assert guide_compiled.manifest.name == live_compiled.manifest.name == "hello-world"
    assert (
        [phase.id for phase in guide_compiled.manifest.phases]
        == [phase.id for phase in live_compiled.manifest.phases]
        == ["greet"]
    )
    assert (
        [phase.src for phase in guide_compiled.manifest.phases]
        == [phase.src for phase in live_compiled.manifest.phases]
        == ["phases/greet"]
    )
    assert guide_compiled.nodes[0].mode == live_compiled.nodes[0].mode == "skill"
    assert (
        set(guide_compiled.raw["io"]["inputs"]["properties"])
        == set(live_compiled.raw["io"]["inputs"]["properties"])
        == {"user_name"}
    )
    assert (
        set(guide_compiled.raw["io"]["outputs"]["properties"])
        == set(live_compiled.raw["io"]["outputs"]["properties"])
        == {"greeting"}
    )
