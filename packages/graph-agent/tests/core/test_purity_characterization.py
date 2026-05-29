from __future__ import annotations

import ast
from pathlib import Path

import pytest

from graph_agent.core.purity import _violation_for_call


def _first_call(source: str) -> ast.Call:
    tree = ast.parse(source)
    call = next(node for node in ast.walk(tree) if isinstance(node, ast.Call))
    return call


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
        ("path.write_text('x')", {}, "write_text", "path mutation APIs are forbidden"),
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
        ("open('in.txt')", {}),
        ("open('in.txt', 'r')", {}),
        ("open('in.txt', mode='rb')", {}),
        ("print('x')", {}),
        ("path.read_text()", {}),
        ("os.path.join('a', 'b')", {"os": "os"}),
    ],
)
def test_violation_for_call_current_non_violations(source: str, aliases: dict[str, str]) -> None:
    assert _violation_for_call(Path("tool.py"), _first_call(source), aliases) is None
