"""PhaseExecutor — per-run dispatcher to polymorphic PhaseNode subclasses.

Per-run collaborator: one instance is built inside each call to
``GraphAgentHarness.run()`` / ``.resume()`` and passed into the compiled
LangGraph via ``RunnableConfig["configurable"]["_phase_executor"]``.
The graph-node closures built by ``GraphBuilder`` extract it from the
config on each invocation and delegate to the appropriate ``execute_*``
method.

After Phase 3 M6 (PHASE3_DESIGN.md §2) the heavy execution logic now
lives on the polymorphic :class:`PhaseNode` hierarchy under
``graph_agent.core.phase_nodes``; this file is the thin shell that:

* holds the harness-lifetime services (``callbacks``, ``resolver``,
  ``save_compaction_sidecar``) plus per-invocation state
  (``run_context``, ``heartbeat``);
* exposes ``execute_llm_phase`` / ``execute_code_only_phase`` /
  ``execute_validation_phase`` as 3 thin facades so existing
  ``GraphBuilder`` and test fixtures keep their call sites unchanged;
* assembles a fresh :class:`DependencyContainer` per call and dispatches
  through :func:`build_llm_phase_node` /
  :func:`build_code_phase_node` / :func:`build_validation_phase_node`.

Design notes (carried forward from the pre-M6 implementation):

  - ``callbacks`` is kept explicit (not pulled from
    ``RunContext.callbacks``) to preserve the pre-refactor nudge-callback
    scope; see ``NudgeInjector``'s module docstring for the same
    reasoning.
  - ``resolver`` and ``save_compaction_sidecar`` are harness-lifetime
    objects; ``run()`` injects them at construction so PhaseExecutor no
    longer needs any harness reference.
  - ``run_context`` and ``heartbeat`` are per-invocation; only
    ``LLMPhaseNode`` reads them today (the code-only and validation
    nodes are oblivious).
"""

from __future__ import annotations

import logging

from graph_agent.callbacks.base import Callback
from graph_agent.core.llm_provider import LLMProvider
from graph_agent.core.phase_nodes import (
    DependencyContainer,
    HeartbeatProtocol,
    SaveCompactionSidecar,
    build_code_phase_node,
    build_llm_phase_node,
    build_validation_phase_node,
)
from graph_agent.core.run_context import RunContext
from graph_agent.core.state import WorkflowState
from graph_agent.core.types import Phase

logger = logging.getLogger(__name__)


class PhaseExecutor:
    """Per-run dispatcher to the polymorphic PhaseNode hierarchy.

    Build one per ``harness.run()`` invocation. Pass it to
    ``graph.invoke`` via ``config["configurable"]["_phase_executor"]``;
    the graph-node closures extract it from the config on each call.
    """

    def __init__(
        self,
        callbacks: list[Callback],
        *,
        run_context: RunContext | None = None,
        heartbeat: HeartbeatProtocol | None = None,
        llm_provider: LLMProvider | None = None,
        resolver: object | None = None,
        save_compaction_sidecar: SaveCompactionSidecar | None = None,
    ) -> None:
        self._callbacks = callbacks
        self._run_context = run_context
        self._heartbeat = heartbeat
        self._llm_provider = llm_provider
        self._legacy_model_resolver = resolver
        self._save_compaction_sidecar = save_compaction_sidecar

    def __getstate__(self) -> object:
        # Fail-fast guard for the LangGraph checkpointer (and any other
        # path that tries to pickle RunnableConfig). ``PhaseExecutor``
        # deliberately holds live per-run references (heartbeat thread,
        # bound method to the harness's sidecar writer, callback list
        # with open trace files); these are not serialisable and even if
        # they were, a resumed run would be wrong to reuse stale
        # instances. We thread the executor through
        # ``config["configurable"]`` for in-memory access only. If the
        # checkpointer tries to persist the config, raising here surfaces
        # the design violation immediately rather than letting a silent
        # data-corruption bug reach production.
        raise TypeError(
            "PhaseExecutor is a per-run runtime object and must not be "
            "pickled. Its presence in RunnableConfig['configurable'] is "
            "for in-memory propagation only — ensure your checkpointer "
            "excludes '_phase_executor' or do not persist the config that "
            "carries it."
        )

    # Read-only accessors for callers that need the fields (e.g. subgraph).
    @property
    def run_context(self) -> RunContext | None:
        return self._run_context

    @property
    def heartbeat(self) -> HeartbeatProtocol | None:
        return self._heartbeat

    @property
    def callbacks(self) -> list[Callback]:
        return self._callbacks

    def _make_dependencies(self) -> DependencyContainer:
        """Snapshot the harness-lifetime services into the immutable container."""
        return DependencyContainer(
            callbacks=self._callbacks,
            llm_provider=self._llm_provider,
            legacy_model_resolver=self._legacy_model_resolver,
            save_compaction_sidecar=self._save_compaction_sidecar,
        )

    def execute_llm_phase(self, phase: Phase, state: WorkflowState) -> WorkflowState:
        """Dispatch an LLM-driven phase to :class:`LLMPhaseNode`."""
        node = build_llm_phase_node(
            phase,
            self._make_dependencies(),
            run_context=self._run_context,
            heartbeat=self._heartbeat,
        )
        return node.execute(phase, state)

    def execute_code_only_phase(self, phase: Phase, state: WorkflowState) -> WorkflowState:
        """Dispatch a code-only (``requires_llm=False``) phase to :class:`CodePhaseNode`."""
        node = build_code_phase_node(
            phase,
            self._make_dependencies(),
            run_context=self._run_context,
            heartbeat=self._heartbeat,
        )
        return node.execute(phase, state)

    def execute_validation_phase(self, phase: Phase, state: WorkflowState) -> WorkflowState:
        """Dispatch the standalone validation graph node to :class:`ValidationPhaseNode`."""
        node = build_validation_phase_node(
            phase,
            self._make_dependencies(),
            run_context=self._run_context,
            heartbeat=self._heartbeat,
        )
        return node.execute(phase, state)


__all__ = ["PhaseExecutor"]
