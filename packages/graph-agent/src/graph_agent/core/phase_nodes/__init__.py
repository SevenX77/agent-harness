"""Phase 3 M6 polymorphic phase-node architecture.

PHASE3_DESIGN.md §2.2 splits the former ``PhaseExecutor`` god class
into focused ``PhaseNode`` subclasses:

* :class:`LLMPhaseNode` — DeerFlow ``create_agent`` + nudge loop
  (former ``execute_llm_phase``).
* :class:`CodePhaseNode` — synchronous Python tools (former
  ``execute_code_only_phase``) with the Phase 2 A3 reserved-key /
  Pydantic-validate dict-merge contract.
* :class:`ValidationPhaseNode` — standalone validator routing
  (former ``execute_validation_phase``).

The :class:`DependencyContainer` dataclass and :func:`build_phase_node`
factory complete the wiring.
"""

from __future__ import annotations

from graph_agent.core.phase_nodes.base import (
    DependencyContainer,
    HeartbeatProtocol,
    PhaseNode,
    SaveCompactionSidecar,
)
from graph_agent.core.phase_nodes.code_phase_node import CodePhaseNode
from graph_agent.core.phase_nodes.factory import (
    build_code_phase_node,
    build_llm_phase_node,
    build_validation_phase_node,
)
from graph_agent.core.phase_nodes.llm_phase_node import LLMPhaseNode
from graph_agent.core.phase_nodes.validation_phase_node import ValidationPhaseNode

__all__ = [
    "CodePhaseNode",
    "DependencyContainer",
    "HeartbeatProtocol",
    "LLMPhaseNode",
    "PhaseNode",
    "SaveCompactionSidecar",
    "ValidationPhaseNode",
    "build_code_phase_node",
    "build_llm_phase_node",
    "build_validation_phase_node",
]
