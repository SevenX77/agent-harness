"""LOGIC `actions/*.py` may hold private helpers; only DECLARED names are actions.

Observable defect (2026-08-16, compiling `D:/coding/skills/story-deconstruction-v3-lab`)::

    action '_addressable_units' must accept exactly one inputs parameter
    action '_entity_ids' must accept exactly one inputs parameter

Neither name appears in its phase's `LOGIC.md` `actions:` list, and neither is
ever dispatched. The engine still called both "an action" and enforced the
action signature on them.

Cause (`packages/graph-agent/src/graph_agent/core/loader.py`):

- `:1419-1429` `_load_action_dir` iterates `_module_functions(module)` and
  registers/validates EVERY module-level function found in the file.
- `:1494-1499` `_module_functions` returns all functions defined in the module,
  private `_`-prefixed ones included.
- `:1502-1519` `_validate_action_signature` then emits
  `[F-v3-logic-action-entrypoint-missing]` with the message
  ``action '<name>' must accept exactly one inputs parameter``.

Why that is wrong — dispatch is declaration-driven, never file-driven:

- `graph_assembler.py:1560` ``action_names = phase_ast.actions`` and `:1566-1567`
  ``for action_name in action_names: compiled.actions.resolve(phase_id, action_name)``
  is the ONLY execution entry. A function absent from `actions:` can never run.
- `loader.py:2802-2809` `_validate_logic_actions_declared` additionally pins the
  frontmatter list to the body `<action>` order, so the declaration is exact.

Design source — `docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md` §3, the
format SSOT that `docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md:26-30`
defers to:

    | `actions` | yes | list[string] | action 名注册表 |
    LOGIC action 源文件位于 `phases/<phase_id>/actions/<action_name>.py`。
    文件必须导出同名函数，签名严格为 `def <action_name>(inputs) -> dict`。

The signature rule is scoped to `<action_name>` — the declared name. Nothing in
the design says the `actions/` module is a flat namespace holding only actions.

Purity stays file-wide by design:
`docs/engine/mvp1/01-contract/03-compile-rules/mvp1-alignment.md:79` scopes it to
the "action/tool Python 文件" — the FILE, not the function — so a helper's
impurity must still be a compile FATAL.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.graph_assembler import assemble_graph

ENTRYPOINT_CODE = "[F-v3-logic-action-entrypoint-missing]"
PURITY_CODE = "[F-v3-logic-action-purity-violation]"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _logic_skill(root: Path, *, declared: list[str], action_source: str) -> None:
    """Write a one-phase skill whose LOGIC declares `declared` in body order."""
    _write(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: action-private-helpers
io:
  inputs:
    type: object
    properties:
      foo:
        type: integer
  outputs:
    type: object
    properties:
      foo:
        type: integer
phases:
  - logic
---
<phase depends_on="input" output>logic</phase>
""",
    )
    body = "\n".join(f"<action>{name}</action>" for name in declared)
    _write(
        root / "phases" / "logic" / "LOGIC.md",
        f"""---
io:
  inputs:
    type: object
    properties:
      foo:
        type: integer
  outputs:
    type: object
    properties:
      foo:
        type: integer
---
{body}
""",
    )
    _write(root / "phases" / "logic" / "actions" / "compute.py", action_source)


def test_module_level_private_helper_is_not_validated_as_an_action(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    """The exact lab-skill shape: a 2-parameter module-level helper next to the action."""
    _logic_skill(
        tmp_path,
        declared=["compute"],
        action_source=(
            "def _entity_ids(rows, id_key) -> list:\n"
            "    return [row[id_key] for row in rows]\n"
            "\n"
            "\n"
            "def compute(inputs) -> dict:\n"
            "    return {'foo': len(_entity_ids([{'id': 1}], 'id'))}\n"
        ),
    )

    compiled = compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)

    assert sorted(compiled.actions.for_phase("logic")) == ["compute"]


def test_undeclared_helper_never_reaches_the_graph(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    """A helper with a no-arg signature must not be registered, let alone executed."""
    _logic_skill(
        tmp_path,
        declared=["compute"],
        action_source=(
            "def _default_foo():\n"
            "    return 7\n"
            "\n"
            "\n"
            "def compute(inputs) -> dict:\n"
            "    return {'foo': _default_foo()}\n"
        ),
    )

    compiled = compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)
    graph = assemble_graph(compiled, skill_resolver=mock_skill_resolver).graph

    result = graph.invoke(
        {"data": {"inputs": {"foo": 1}}, "flow": {}, "messages": [], "run_id": "r1"}
    )

    assert result["data"]["foo"] == 7


def test_declared_action_with_a_bad_signature_is_still_compile_fatal(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    """Regression guard: filtering by declaration must not weaken the real rule."""
    _logic_skill(
        tmp_path,
        declared=["compute"],
        action_source="def compute(inputs, extra) -> dict:\n    return {'foo': extra}\n",
    )

    with pytest.raises(SkillLoadError) as exc_info:
        compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)

    payload = exc_info.value.payload
    assert payload is not None
    assert payload.code == ENTRYPOINT_CODE
    assert "compute" in payload.message


def test_declared_action_without_a_matching_function_is_compile_fatal(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    """`actions:` is the registry, so a declared name with no implementation must fail
    at compile — not with a runtime KeyError from ActionRegistry.resolve."""
    _logic_skill(
        tmp_path,
        declared=["compute"],
        action_source=(
            "def _compute(inputs) -> dict:\n"
            "    return {'foo': inputs.get('foo', 0)}\n"
        ),
    )

    with pytest.raises(SkillLoadError) as exc_info:
        compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)

    payload = exc_info.value.payload
    assert payload is not None
    assert payload.code == ENTRYPOINT_CODE
    assert "compute" in payload.message


def test_helper_impurity_is_still_a_compile_fatal(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    """Purity is scoped to the FILE, so an impure helper stays fatal even though the
    helper is no longer an action."""
    _logic_skill(
        tmp_path,
        declared=["compute"],
        action_source=(
            "def _persist(value) -> None:\n"
            "    with open('side_effect.txt', 'w', encoding='utf-8') as handle:\n"
            "        handle.write(str(value))\n"
            "\n"
            "\n"
            "def compute(inputs) -> dict:\n"
            "    _persist(1)\n"
            "    return {'foo': 1}\n"
        ),
    )

    with pytest.raises(SkillLoadError) as exc_info:
        compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)

    payload = exc_info.value.payload
    assert payload is not None
    assert payload.code == PURITY_CODE
