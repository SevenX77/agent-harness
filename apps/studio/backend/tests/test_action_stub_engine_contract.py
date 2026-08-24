"""Cross-layer contract test: the Studio "Add action" scaffold must compile.

Studio's LOGIC action scaffold (`actionStubContent` in
apps/studio/frontend/src/components/studio/panels/phase-actions.ts) writes a
Python file to disk the instant a user clicks "Add action". The engine loader
enforces a strict entrypoint contract on that file (ground truth
docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md:234 + `_validate_action_signature`
in packages/graph-agent/src/graph_agent/core/loader.py): the action's sole
parameter must be named `inputs` — never `context`/`ctx` — and it must be
dict-compatible. A template using the wrong parameter name fails to compile
the instant it is scaffolded ([F-v3-logic-action-entrypoint-missing]); that is
exactly what happened for real on 2026-08-24 (PROBLEM_LEDGER J-03.A) because
the frontend template and the engine contract had drifted apart.

TypeScript strings cannot be imported into a Python test, so
`_studio_action_stub_content` below is a hand-copied mirror of
`actionStubContent`. The two copies are the two halves of this contract test
and must be kept in sync by hand — each carries a comment pointing at the
other. If you change the shape of one, change the other in the same commit.
"""

from __future__ import annotations

from pathlib import Path

from graph_agent.core.compiler import compile_skill


def _studio_action_stub_content(name: str) -> str:
    """Byte-for-byte mirror of `actionStubContent` in
    apps/studio/frontend/src/components/studio/panels/phase-actions.ts.

    Keep this in sync with that function by hand — there is no automated way
    to detect the two drifting apart, only this comment pair (and this test,
    which fails the moment this copy stops satisfying the engine's contract).
    """

    return (
        "from __future__ import annotations\n"
        "\n"
        "\n"
        f"def {name}(inputs) -> dict:\n"
        f'    """TODO: describe what {name} does."""\n'
        "    # Read this phase's inputs via inputs[\"field\"] (inputs is read-only).\n"
        "    # Return only keys declared in this phase's io.outputs.properties.\n"
        "    return {}\n"
    )


def _write_skill_with_action(root: Path, action_name: str, action_body: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "GRAPH.md").write_text(
        """---
schema_version: "v0.3.0"
name: action-stub-contract
io:
  inputs:
    type: object
    properties:
      seed:
        type: integer
  outputs:
    type: object
    properties:
      seed:
        type: integer
phases:
  - demo
---
<phase depends_on="input" output>demo</phase>
""",
        encoding="utf-8",
    )
    phase_dir = root / "phases" / "demo"
    phase_dir.mkdir(parents=True, exist_ok=True)
    (phase_dir / "LOGIC.md").write_text(
        f"""---
io:
  inputs:
    type: object
    properties:
      seed:
        type: integer
  outputs:
    type: object
    properties:
      seed:
        type: integer
---
<action>{action_name}</action>
""",
        encoding="utf-8",
    )
    actions_dir = phase_dir / "actions"
    actions_dir.mkdir(parents=True, exist_ok=True)
    (actions_dir / f"{action_name}.py").write_text(action_body, encoding="utf-8")


def test_add_action_scaffold_compiles_cleanly(tmp_path: Path) -> None:
    """The stub Studio writes the moment "Add action" is clicked must, with
    nothing filled in by the author yet, pass the engine's compile gate."""
    action_name = "compose_text"
    _write_skill_with_action(tmp_path, action_name, _studio_action_stub_content(action_name))

    compiled = compile_skill(tmp_path, cache=False)

    assert [node.phase_name for node in compiled.nodes] == ["demo"]
