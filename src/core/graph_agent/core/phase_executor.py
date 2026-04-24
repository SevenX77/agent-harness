"""PhaseExecutor — executes a single phase (LLM / code-only / subgraph) once.

Skeleton for D-step-1 (refactor/harness-split). Implementation is migrated
from ``GraphAgentHarness._build_phase_node`` / ``_build_code_only_node`` /
``_build_validation_node`` during D-7.2.

Per context.md §12.2, this class will *also* take ownership of the active
``_HeartbeatPulser`` handle (currently ``GraphAgentHarness._active_heartbeat``)
and the active ``RunContext`` read target, so subgraph child harnesses stop
racing on shared instance state.

Per context.md §11-3 (Gemini's note): ``AgentLoopIterationMiddleware`` stays
in ``..cognitive.middlewares`` — PhaseExecutor only *uses* it at invoke time,
it does not move.
"""

from __future__ import annotations

from .nudge_injector import NudgeInjector
from .run_context import RunContext
from .state import WorkflowState
from .types import Phase


class PhaseExecutor:
    """Execute a phase exactly once; retry is orchestrated by ``RetryRouter``."""

    def __init__(self, run_context: RunContext, *, nudge_injector: NudgeInjector) -> None:
        self._run_context = run_context
        self._nudge_injector = nudge_injector

    def execute_llm_phase(self, phase: Phase, state: WorkflowState) -> WorkflowState:
        """Run an LLM-driven phase (DeerFlow create_agent + nudge-loop)."""
        raise NotImplementedError("D-7.2: migrate LLM execution body from _build_phase_node")

    def execute_code_only_phase(self, phase: Phase, state: WorkflowState) -> WorkflowState:
        """Run a pure-code phase (no LLM; tools called as plain functions)."""
        raise NotImplementedError("D-7.2: migrate from _build_code_only_node")

    def execute_subgraph_phase(self, phase: Phase, state: WorkflowState) -> WorkflowState:
        """Invoke a child harness for a subgraph phase."""
        raise NotImplementedError("D-7.2: migrate from _build_subgraph_node body")
