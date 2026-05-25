"""Isolated builtin reference reader runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from graph_agent.runtime.state import BlackboardState
from graph_agent.runtime.state_mapper import ReaderSandboxState


@dataclass(frozen=True)
class ReferenceReaderRuntime:
    """Run reference reading in an isolated sandbox state."""

    skill_id: str
    phase_id: str
    root: Path
    timeout_s: int = 60

    def initial_state(self) -> BlackboardState:
        return ReaderSandboxState(
            skill_id=self.skill_id,
            phase_id=self.phase_id,
            root=self.root,
            timeout_s=self.timeout_s,
        ).to_blackboard()


__all__ = ["ReferenceReaderRuntime"]
