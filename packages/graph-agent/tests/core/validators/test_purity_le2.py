"""Compile-path RED tests for mvp1 LOGIC LE2 purity hard bans."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from graph_agent.core.error_registry import ERROR_REGISTRY, ErrorCodeMetadata
from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.loader import SkillLoader

PURITY_CODE = "[F-v3-logic-action-purity-violation]"


def _write_minimal_logic_skill(root: Path, action_body: str) -> None:
    (root / "phases" / "prepare" / "actions").mkdir(parents=True)
    (root / "GRAPH.md").write_text(
        """---
schema_version: "v0.3.0"
name: purity-le2-test
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
phases:
  - prepare
---
<phase depends_on="input" output>prepare</phase>
""",
        encoding="utf-8",
    )
    (root / "phases" / "prepare" / "LOGIC.md").write_text(
        """---
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
---
<action>prepare</action>
""",
        encoding="utf-8",
    )
    (root / "phases" / "prepare" / "actions" / "prepare.py").write_text(
        dedent(action_body).lstrip(),
        encoding="utf-8",
    )


def _compile(root: Path, mock_skill_resolver: object) -> None:
    SkillLoader().compile_skill(root, skill_resolver=mock_skill_resolver)


def _assert_compile_purity_fatal(
    tmp_path: Path,
    mock_skill_resolver: object,
    action_body: str,
    *message_fragments: str,
) -> None:
    _write_minimal_logic_skill(tmp_path, action_body)

    with pytest.raises(SkillLoadError) as exc_info:
        _compile(tmp_path, mock_skill_resolver)

    payload = exc_info.value.payload
    assert payload is not None
    assert payload.code == PURITY_CODE
    assert payload.source_path is not None
    assert payload.source_path.endswith("phases/prepare/actions/prepare.py")
    assert "prepare.py:" in payload.message
    for fragment in message_fragments:
        assert fragment.lower() in payload.message.lower()


@pytest.mark.parametrize(
    ("action_body", "message_fragments"),
    [
        (
            """
            from graph_agent import run_skill

            def prepare(context):
                run_skill("child.skill", workspace_dir="workspace")
                return {}
            """,
            ("run_skill",),
        ),
        (
            """
            def prepare(context):
                open("input.txt").read()
                return {}
            """,
            ("open", "file"),
        ),
        (
            """
            def prepare(context):
                open("out.txt", "w").write("bad")
                return {}
            """,
            ("open", "file"),
        ),
        (
            """
            import sys

            def prepare(context):
                sys.path.append("../outside")
                return {}
            """,
            ("sys.path",),
        ),
        (
            """
            import sys

            def prepare(context):
                sys.path = ["../outside"]
                return {}
            """,
            ("sys.path",),
        ),
        (
            """
            import sys

            def prepare(context):
                sys.path[0] = "../outside"
                return {}
            """,
            ("sys.path",),
        ),
        (
            """
            from pathlib import Path

            def prepare(context):
                Path("input.txt").exists()
                return {}
            """,
            ("exists", "file"),
        ),
        (
            """
            import glob

            def prepare(context):
                glob.glob("*.txt")
                return {}
            """,
            ("glob.glob", "file"),
        ),
        (
            """
            import importlib

            def prepare(context):
                runner = importlib.import_module("graph_agent.core.runner")
                runner.run_skill("child.skill", workspace_dir="workspace")
                return {}
            """,
            ("import",),
        ),
    ],
)
def test_le2_forbidden_action_code_fails_during_compile(
    tmp_path: Path,
    mock_skill_resolver: object,
    action_body: str,
    message_fragments: tuple[str, ...],
) -> None:
    _assert_compile_purity_fatal(
        tmp_path,
        mock_skill_resolver,
        action_body,
        *message_fragments,
    )


def test_pure_action_still_compiles_under_le2_purity(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    _write_minimal_logic_skill(
        tmp_path,
        """
        import json

        def prepare(context):
            payload = json.loads("{}")
            value = str(payload.get("value", "ok")).strip()
            return {}
        """,
    )

    compiled = SkillLoader().compile_skill(tmp_path, skill_resolver=mock_skill_resolver)

    assert "prepare" in compiled.actions.for_phase("prepare")


def test_purity_violation_error_code_remains_compile_fatal() -> None:
    metadata = ERROR_REGISTRY[PURITY_CODE]

    assert isinstance(metadata, ErrorCodeMetadata)
    assert metadata.code == PURITY_CODE
    assert metadata.level == "FATAL"
    assert metadata.stage == ("编译期",)
