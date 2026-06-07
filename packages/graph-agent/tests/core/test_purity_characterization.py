from __future__ import annotations

import ast
from pathlib import Path
from textwrap import dedent

import pytest

from graph_agent.core.purity import _violation_for_call, scan_python_purity


def _first_call(source: str) -> ast.Call:
    tree = ast.parse(source)
    call = next(node for node in ast.walk(tree) if isinstance(node, ast.Call))
    return call


def _write_python(tmp_path: Path, source: str) -> Path:
    path = tmp_path / "action.py"
    path.write_text(dedent(source).lstrip(), encoding="utf-8")
    return path


def _assert_violation_mentions(path: Path, *expected_fragments: str) -> None:
    violations = scan_python_purity(path)
    combined = "\n".join(f"{violation.api} {violation.reason}" for violation in violations).lower()

    assert violations
    for fragment in expected_fragments:
        assert fragment.lower() in combined


@pytest.mark.parametrize(
    ("source", "aliases", "expected_api", "expected_reason"),
    [
        ("open('out.txt', 'w')", {}, "open", "may write local files"),
        ("open('out.txt', mode='rb+')", {}, "open", "may write local files"),
        ("open('out.txt', mode=mode)", {}, "open", "mode must be a literal read-only mode"),
        ("NamedTemporaryFile()", {}, "NamedTemporaryFile", "temporary files are local writes"),
        (
            "tmp.NamedTemporaryFile()",
            {"tmp": "tempfile"},
            "tempfile.NamedTemporaryFile",
            "temporary files are local writes",
        ),
        (
            "Path('x').write_text('x')",
            {"Path": "pathlib.Path"},
            "write_text",
            "path mutation APIs are forbidden",
        ),
        ("os.remove('x')", {"os": "os"}, "os.remove", "os filesystem mutation is forbidden"),
        ("shutil.rmtree('x')", {"shutil": "shutil"}, "shutil.rmtree", "shutil filesystem mutation is forbidden"),
    ],
)
def test_violation_for_call_current_violations(
    source: str,
    aliases: dict[str, str],
    expected_api: str,
    expected_reason: str,
) -> None:
    violation = _violation_for_call(Path("tool.py"), _first_call(source), aliases)

    assert violation is not None
    assert violation.api == expected_api
    assert expected_reason in violation.reason
    assert violation.path == Path("tool.py")


@pytest.mark.parametrize(
    ("source", "aliases"),
    [
        ("print('x')", {}),
        ("os.path.join('a', 'b')", {"os": "os"}),
        ("json.loads('{\"value\": 1}')", {"json": "json"}),
    ],
)
def test_violation_for_call_current_non_violations(source: str, aliases: dict[str, str]) -> None:
    assert _violation_for_call(Path("tool.py"), _first_call(source), aliases) is None


@pytest.mark.parametrize(
    ("source", "expected_fragments"),
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
            from graph_agent.core.runner import run_skill as call_child

            def prepare(context):
                call_child("child.skill", workspace_dir="workspace")
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
            from pathlib import Path

            def prepare(context):
                Path("input.txt").read_text(encoding="utf-8")
                return {}
            """,
            ("read_text", "file"),
        ),
        (
            """
            from pathlib import Path

            def prepare(context):
                Path("input.txt").replace("output.txt")
                return {}
            """,
            ("replace", "path"),
        ),
        (
            """
            from pathlib import Path

            def prepare(context):
                Path("input.txt").unlink()
                return {}
            """,
            ("unlink", "path"),
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
            from pathlib import Path

            def prepare(context):
                path = Path("input.txt")
                path.exists()
                return {}
            """,
            ("exists", "file"),
        ),
        (
            """
            from pathlib import Path

            def prepare(context):
                Path("input.txt").stat()
                return {}
            """,
            ("stat", "file"),
        ),
        (
            """
            from pathlib import Path

            def prepare(context):
                list(Path(".").iterdir())
                return {}
            """,
            ("iterdir", "file"),
        ),
        (
            """
            import os

            def prepare(context):
                os.listdir(".")
                return {}
            """,
            ("os.listdir", "file"),
        ),
        (
            """
            import os

            def prepare(context):
                os.path.exists("input.txt")
                return {}
            """,
            ("os.path.exists", "file"),
        ),
        (
            """
            import os

            def prepare(context):
                os.stat("input.txt")
                return {}
            """,
            ("os.stat", "file"),
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
            import sys

            def prepare(context):
                sys.path.insert(0, "../outside")
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
            import importlib

            def prepare(context):
                importlib.import_module("graph_agent.core.runner")
                return {}
            """,
            ("importlib.import_module", "import"),
        ),
        (
            """
            from importlib import util

            def prepare(context):
                util.spec_from_file_location("escape", "../outside.py")
                return {}
            """,
            ("spec_from_file_location", "import"),
        ),
    ],
)
def test_scan_python_purity_reports_le2_hard_bans(
    tmp_path: Path,
    source: str,
    expected_fragments: tuple[str, ...],
) -> None:
    _assert_violation_mentions(_write_python(tmp_path, source), *expected_fragments)


def test_scan_python_purity_allows_pure_data_transformations(tmp_path: Path) -> None:
    path = _write_python(
        tmp_path,
        """
        import json

        def prepare(context):
            payload = context.get("payload", "{}")
            parsed = json.loads(payload)
            title = str(parsed.get("title", "")).strip().upper()
            return {"title": title}
        """,
    )

    assert scan_python_purity(path) == []


def test_scan_python_purity_allows_string_replace_transformation(tmp_path: Path) -> None:
    path = _write_python(
        tmp_path,
        """
        def prepare(context):
            raw_title = str(context.get("title", ""))
            normalized = raw_title.replace("-", " ").strip().upper()
            return {"title": normalized}
        """,
    )

    assert scan_python_purity(path) == []


def test_scan_python_purity_allows_plain_object_exists_method(tmp_path: Path) -> None:
    path = _write_python(
        tmp_path,
        """
        class Record:
            def exists(self):
                return True

        def prepare(context):
            record = Record()
            return {"exists": record.exists()}
        """,
    )

    assert scan_python_purity(path) == []
