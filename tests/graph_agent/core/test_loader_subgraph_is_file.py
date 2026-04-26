"""Cohesion plan 方针 4.4 (2026-04-26): a delegate phase whose
``subgraph:`` reference points at a *directory* (or other non-file)
on disk used to slip past the loader's ``Path.exists()`` check and
then crash with ``IsADirectoryError`` inside ``read_text`` —
miles away from the author's typo.

The compile pass usually catches this first via context_bridge's
``F-context-bridge-child-missing``, but defence-in-depth at the loader
matters because (a) callers can bypass the compiler when they trust
the input, and (b) the resulting error message is part of the public
contract for in-process Studio reloads.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import TypeAdapter

from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.loader import _phase_from_graph_phase
from graph_agent.core.manifest import DelegatePhase, PhaseDef


def test_phase_from_graph_phase_rejects_directory_subgraph(tmp_path: Path) -> None:
    """A directory at the subgraph path must surface as
    ``SkillLoadError`` with a clear message — not as
    ``IsADirectoryError`` from a downstream ``read_text``."""
    fake_subgraph_dir = tmp_path / "child" / "SKILL.md"
    fake_subgraph_dir.mkdir(parents=True)  # a directory NAMED SKILL.md

    delegate = TypeAdapter(PhaseDef).validate_python({
        "mode": "delegate",
        "name": "dispatch",
        "subgraph": "child/SKILL.md",
        "context_bridge": {"inputs": {}, "outputs": {}},
    })
    assert isinstance(delegate, DelegatePhase)

    with pytest.raises(SkillLoadError) as excinfo:
        _phase_from_graph_phase(
            delegate, tmp_path, callbacks=None, loading_stack=set()
        )
    msg = str(excinfo.value).lower()
    assert "subgraph" in msg
    assert "not a file" in msg or "not found" in msg, (
        f"Loader must say 'not a file' or 'not found' so the author "
        f"can locate the typo; got: {excinfo.value}"
    )
