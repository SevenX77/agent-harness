from __future__ import annotations

from pathlib import Path

import pytest

from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.loader import SkillLoader
from graph_agent.core.runner import run_skill
from graph_agent.core.skill_resolver_protocol import (
    SkillResolutionError,
    validate_skill_id,
)


class DictSkillResolver:
    def __init__(self, roots: dict[str, Path]) -> None:
        self.roots = roots

    def resolve_skill(self, skill_id: str) -> Path:
        try:
            return self.roots[skill_id]
        except KeyError as exc:
            raise SkillResolutionError(skill_id, "not registered") from exc


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _base(root: Path, *, name: str = "resolver-test", phase: str = "main") -> None:
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: {name}
io:
  inputs:
    type: object
    properties:
      text:
        type: string
  outputs:
    type: object
    properties: {{}}
phases:
  - {phase}
---
<phase depends_on="input" output>{phase}</phase>
""",
    )


def _child_skill(root: Path) -> None:
    _base(root, name="child", phase="child")
    _write(
        root / "phases" / "child" / "SKILL.md",
        """---
io:
  inputs:
    type: object
    properties:
      text:
        type: string
    required: [text]
  outputs:
    type: object
    properties: {}
---
<role>Child</role>
<goal>Do child work.</goal>
""",
    )


def _parent_skill(root: Path, target_skill: str) -> None:
    _base(root)
    _write(
        root / "phases" / "main" / "SKILL.md",
        f"""---
phase_config:
  subagents:
    - name: child_expert
      target_skill: {target_skill}
      description: Resolve child by skill id.
io:
  inputs:
    type: object
    properties: {{}}
  outputs:
    type: object
    properties: {{}}
---
<role>Parent</role>
<goal>Parent work.</goal>
""",
    )


def test_target_skill_subagent_resolves_through_protocol(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    child = tmp_path / "registered-child"
    _parent_skill(parent, "demo.child")
    _child_skill(child)
    resolver = DictSkillResolver({"demo.child": child})

    compiled = SkillLoader().compile_skill(parent, skill_resolver=resolver)
    subagent = compiled.subagents_by_phase["main"][0]
    tools = {tool.name: tool for tool in compiled.tools.for_phase("main")}

    assert subagent.target_skill == "demo.child"
    assert subagent.root == child
    assert subagent.input_model.model_validate({"text": "hello"}).text == "hello"
    assert tools["call_subagent_child_expert"].metadata["target_skill"] == "demo.child"


def test_compile_skill_facade_passes_skill_resolver(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    child = tmp_path / "registered-child"
    _parent_skill(parent, "demo.child")
    _child_skill(child)

    compiled = compile_skill(
        parent,
        cache=False,
        skill_resolver=DictSkillResolver({"demo.child": child}),
    )

    assert compiled.subagents_by_phase["main"][0].target_skill == "demo.child"


def test_target_skill_requires_resolver(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    _parent_skill(parent, "demo.child")

    with pytest.raises(SkillResolutionError) as exc_info:
        SkillLoader().compile_skill(parent, skill_resolver=None)
    assert exc_info.value.payload.code == "[F-v3-resolver-missing]"


def test_compile_skill_facade_requires_resolver_v3_code(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    _parent_skill(parent, "demo.child")

    with pytest.raises(SkillResolutionError) as exc_info:
        compile_skill(parent, cache=False, skill_resolver=None)
    assert exc_info.value.payload.code == "[F-v3-resolver-missing]"


def test_run_skill_requires_resolver_v3_code(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    _parent_skill(parent, "demo.child")

    with pytest.raises(SkillResolutionError) as exc_info:
        run_skill(parent, skill_resolver=None)
    assert exc_info.value.payload.code == "[F-v3-resolver-missing]"


def test_invalid_skill_id_raises_v3_code() -> None:
    with pytest.raises(SkillResolutionError) as exc_info:
        validate_skill_id("../escape")
    assert exc_info.value.payload.code == "[F-v3-resolver-skill-id-invalid]"


def test_resolver_returning_invalid_path_raises_v3_code(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    missing_root = tmp_path / "missing-child"
    _parent_skill(parent, "demo.child")

    with pytest.raises(SkillResolutionError) as exc_info:
        SkillLoader().compile_skill(
            parent,
            skill_resolver=DictSkillResolver({"demo.child": missing_root}),
        )
    assert exc_info.value.payload.code == "[F-v3-resolver-path-invalid]"


def test_unregistered_skill_id_raises_v3_code(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    _parent_skill(parent, "demo.missing")

    with pytest.raises(SkillResolutionError) as exc_info:
        SkillLoader().compile_skill(parent, skill_resolver=DictSkillResolver({}))
    assert exc_info.value.payload.code == "[F-v3-skill-not-registered]"


# TODO: PR delta src impl: add an active test for
# [F-v3-resolver-interface-invalid] when the runtime interface-validation trigger is defined.
