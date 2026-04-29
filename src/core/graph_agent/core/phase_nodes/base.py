"""Base class + dependency container for the polymorphic PhaseNode hierarchy.

PHASE3_DESIGN.md §2.2 introduces a multi-class architecture so each
``Phase`` mode (LLM / code-only / validation) lives in its own
focused class. The :class:`PhaseNode` ABC pins the runtime contract
the LangGraph node closures invoke; the :class:`DependencyContainer`
``@dataclass(frozen=True)`` carries the harness-lifetime services
(callbacks list, model resolver, sidecar writer) so subclasses don't
each duplicate a long ``__init__`` parameter list.

Per design §2.6, *per-invocation* state (``run_context`` and
``heartbeat``) is passed to the node constructor as keyword args
rather than packaged inside the container, keeping the container
stateless across the whole harness lifetime.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from langchain_core.language_models.chat_models import BaseChatModel

from ...callbacks.base import Callback
from ..run_context import RunContext
from ..state import StateManager, WorkflowState
from ..types import Phase

SaveCompactionSidecar = Callable[..., str | None]


class ModelResolverProtocol(Protocol):
    """Minimal resolver surface consumed by ``LLMPhaseNode``."""

    def resolve(
        self,
        role_name: str | None = None,
        *,
        model_override: str | None = None,
        callbacks: tuple[Callback, ...] = (),
        phase_name: str | None = None,
    ) -> BaseChatModel:
        """Return a LangChain-compatible model object for one phase."""


class HeartbeatProtocol(Protocol):
    """Mutable heartbeat handle updated with the active phase name."""

    current_phase: str | None


@dataclass(frozen=True)
class DependencyContainer:
    """Harness-lifetime services every PhaseNode subclass needs.

    Construction happens once per ``GraphAgentHarness.run()`` /
    ``.resume()`` invocation in the thin ``PhaseExecutor`` shell, and
    the same container is handed to whichever PhaseNode subclass the
    factory selects for that phase.
    """

    callbacks: list[Callback]
    resolver: ModelResolverProtocol | None = None
    save_compaction_sidecar: SaveCompactionSidecar | None = None


class PhaseNode(ABC):
    """Abstract base for the polymorphic phase-execution hierarchy.

    Subclasses (``LLMPhaseNode`` / ``CodePhaseNode`` /
    ``ValidationPhaseNode``) implement :meth:`execute` for the specific
    ``Phase`` mode they own. The base class also provides the shared
    declarative IO hoist that every mode runs at phase exit.
    """

    def __init__(
        self,
        dependencies: DependencyContainer,
        *,
        run_context: RunContext | None = None,
        heartbeat: HeartbeatProtocol | None = None,
    ) -> None:
        # Mirror the original ``PhaseExecutor`` attribute names so the
        # method bodies move from the executor verbatim — keeps the M6
        # refactor a textual lift-and-shift instead of a rewrite, which
        # in turn keeps the existing 28+ phase-executor tests green.
        self._callbacks = dependencies.callbacks
        self._resolver = dependencies.resolver
        self._save_compaction_sidecar = dependencies.save_compaction_sidecar
        self._run_context = run_context
        self._heartbeat = heartbeat

    @abstractmethod
    def execute(self, phase: Phase, state: WorkflowState) -> WorkflowState:
        """Run the phase against the inbound state and return the next state."""
        raise NotImplementedError

    def _apply_io_hoist(
        self,
        state: WorkflowState,
        phase: Phase,
        *,
        source_data: dict[str, object] | None = None,
    ) -> WorkflowState:
        """MVP-2 T7-bis: route declarative io.outputs into BusinessData.

        Called at phase exit from each of the three executor entry
        points (LLM phase end, code-only phase end, validation phase
        pass). When ``phase.io_specs`` is empty the call is a no-op,
        which keeps phases without declarative io routing on the
        legacy path.

        ``source_data`` defaults to ``state['flow'].finish_task_result``
        (the LLM phase exit case after ``StateManager.route_finish_task``
        has populated it). Code-only phases pass the live BusinessData
        dump so tool-returned dict keys can hoist directly. The IOManager
        is constructed per-call from the phase's specs — re-construction
        is cheap and lets the caller stay stateless.
        """
        if not phase.io_specs:
            return state

        from ..io_manager import IOManager

        if source_data is None:
            ftr = state["flow"].finish_task_result
            source_data = dict(ftr) if isinstance(ftr, dict) else {}

        manager = IOManager(list(phase.io_specs))
        result = manager.resolve_hoist(source_data, state["data"])

        next_state = state
        new_dump = result.new_business_data.model_dump()
        # Only push BusinessData updates when the hoist produced new
        # fields. Comparing against the live dump avoids a redundant
        # ``model_copy`` round-trip when every spec was missing.
        if new_dump != next_state["data"].model_dump():
            next_state = StateManager.update_business(next_state, **new_dump)

        if result.io_errors:
            existing = list(next_state["flow"].io_errors)
            next_state = StateManager.update_framework(
                next_state, io_errors=existing + list(result.io_errors)
            )
        return next_state


__all__ = ["DependencyContainer", "PhaseNode"]
