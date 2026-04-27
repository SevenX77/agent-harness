"""Loader tests for schema-only phase modes."""
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import TypeAdapter

from graph_agent.core.loader import _phase_from_graph_phase
from graph_agent.core.manifest import ParallelDelegatePhase, PhaseDef


def test_loader_raises_not_implemented_for_parallel_delegate(tmp_path: Path) -> None:
    phase = TypeAdapter(PhaseDef).validate_python({
        "mode": "parallel_delegate",
        "name": "parallel_review",
        "subgraphs": ["./a/SKILL.md", "./b/SKILL.md"],
        "context_bridge": {"inputs": {}, "outputs": {}},
        "tolerance": 0.2,
        "reducer": "script.merge.reduce_outputs",
    })
    assert isinstance(phase, ParallelDelegatePhase)

    with pytest.raises(NotImplementedError) as exc:
        _phase_from_graph_phase(
            phase,
            tmp_path,
            callbacks=None,
            loading_stack=set(),
        )

    msg = str(exc.value)
    assert "parallel_delegate" in msg
    assert "runtime implementation is pending" in msg
