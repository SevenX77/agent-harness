"""Error-handling tests for `_parse_broken_graph_topology_and_phases`.

This is the parser used to populate the repair-state view when a skill's
GRAPH.md is broken/missing. Degradation to ``([], [])`` must stay graceful
(the repair view depends on it) but must be *observable*: a genuine parse
failure has to surface a WARNING so an operator can tell a parse crash apart
from a legitimately-empty graph.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from app.services import skills as skill_service


def _write_graph(skill_dir: Path, content: str) -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "GRAPH.md").write_text(content, encoding="utf-8")


def test_parse_broken_graph_logs_warning_and_degrades_on_malformed_yaml(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    skill_dir = tmp_path / "broken-skill"
    # Valid `---` fences (so it passes the structural length check) but the
    # frontmatter is an unterminated flow sequence -> yaml.YAMLError.
    _write_graph(
        skill_dir,
        "---\nphases: [a, b, c\n---\n<phase>setup</phase>\n",
    )

    with caplog.at_level(logging.WARNING):
        phases, topology = skill_service._parse_broken_graph_topology_and_phases(skill_dir)

    # Graceful degradation is preserved: repair view still renders.
    assert phases == []
    assert topology == []

    # ...but the failure is now observable.
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1, "expected exactly one WARNING for the parse failure"
    message = warnings[0].getMessage()
    assert str(skill_dir) in message, "warning should name the failing skill_dir/file"
    assert "GRAPH.md" in message


def test_parse_broken_graph_silent_when_legitimately_absent(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # No GRAPH.md at all is a legitimately-empty graph, not a parse crash:
    # it must degrade to ([], []) WITHOUT emitting a warning.
    skill_dir = tmp_path / "no-graph-skill"
    skill_dir.mkdir(parents=True)

    with caplog.at_level(logging.WARNING):
        phases, topology = skill_service._parse_broken_graph_topology_and_phases(skill_dir)

    assert phases == []
    assert topology == []
    assert [r for r in caplog.records if r.levelno == logging.WARNING] == []
