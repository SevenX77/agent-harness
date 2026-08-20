"""Middleware package: the live chain's classes and its order contract.

Every behaviour the agent loop layers on top of a plain ``create_agent``
call lives here, as single-purpose middleware classes the assembler
wires in a fixed topological order:

1. :class:`TracingMiddleware` — reports every tool call as it starts and
   as it ends. Runs first because it is the only observer on the
   tool-call axis and the middlewares below it answer tool calls
   themselves without calling through: an observer they can skip sees
   only the subset their control flow leaves for it.
2. :class:`ProtocolValidationMiddleware` — state contract guards
   (BusinessData / FrameworkState invariants + SchemaEngine validate
   on the after-model boundary). First of the middlewares that READ the
   state, because every one of them assumes the shape is already valid.
3. :class:`CognitiveFlowMiddleware` — cognitive tool interception:
   finish_task, ask_clarification, and the working-memory / ambiguity /
   context-access tools that read and write ``FrameworkState``.
4. :class:`ExecutionControlMiddleware` — iteration counter, dead-end
   detection, lightweight loop detection, metrics aggregation.
5. :class:`CompactionMiddleware` — summarizes messages out of context
   before the window overflows, writing the removed text to a sidecar.
6. :class:`ToolErrorHandlingMiddleware` · 7.
   :class:`LoopDetectionMiddleware` — tool-error handling and repetition
   detection.
8. :class:`ExitControlMiddleware` — exit governance plus the nudge
   policy adapter; runs last because it decides whether the loop ends.

:data:`MVP0_MIDDLEWARE_ORDER_CONTRACT` is that order as strings, so
callers construct the chain without re-deriving it. The assembler
prepends two more slots outside this contract (RuntimeInput,
ToolHistoryIntegrity) — see ``core/graph_assembler.py``. Order
regression tests (``tests/middleware/test_chain_topology.py``,
``tests/core/test_gamma0_contract_tdd.py``) pin the sequence: silently
re-ordering middleware is precisely the kind of latent bug this
package exists to make impossible.
"""

from __future__ import annotations

from graph_agent.middleware.cognitive_flow import CognitiveFlowMiddleware
from graph_agent.middleware.compaction import CompactionMiddleware
from graph_agent.middleware.execution_control import ExecutionControlMiddleware
from graph_agent.middleware.exit_control import ExitControlMiddleware
from graph_agent.middleware.loop_detection import LoopDetectionMiddleware
from graph_agent.middleware.protocol_validation import ProtocolValidationMiddleware
from graph_agent.middleware.tool_error import ToolErrorHandlingMiddleware
from graph_agent.middleware.tracing import TracingMiddleware

# Tracing is FIRST because it is the only observer on the tool-call axis, and an
# observer a decider can skip is not observing the system — it is observing
# whatever subset another component's control flow leaves for it. Measured
# 2026-08-20: with Tracing at slot 5, `CognitiveFlowMiddleware` answered every
# tool it intercepts without calling `handler(request)`, so `wrap_tool_call`
# never reached Tracing and `ToolCallStartedEvent` — defined, exported, mirrored
# into the frontend and consumed there — was emitted zero times in a real run.
# Borrowed convention: Django's MIDDLEWARE list and Express's `app.use` order,
# where the logging/tracing layer is registered first so it still sees the
# requests an auth layer below it short-circuits.
#
# Moving it costs nothing on the other axes: Tracing implements only the tool
# hooks, so ProtocolValidation still guards state before every middleware that
# reads it, and Compaction still acts through `before_model`.
MVP0_MIDDLEWARE_ORDER_CONTRACT: tuple[str, ...] = (
    "Tracing",
    "ProtocolValidation",
    "CognitiveFlow",
    "ExecutionControl",
    "Compaction",
    "ToolError",
    "LoopDetection",
    "ExitControl",
)

from graph_agent.middleware.factory import (  # noqa: E402
    MIDDLEWARE_ORDER_CONTRACT,
    build_middleware_chain,
    build_middleware_chain_cognitive_flow,
)

__all__ = [
    "MIDDLEWARE_ORDER_CONTRACT",
    "MVP0_MIDDLEWARE_ORDER_CONTRACT",
    "CognitiveFlowMiddleware",
    "CompactionMiddleware",
    "ExecutionControlMiddleware",
    "ExitControlMiddleware",
    "LoopDetectionMiddleware",
    "ProtocolValidationMiddleware",
    "ToolErrorHandlingMiddleware",
    "TracingMiddleware",
    "build_middleware_chain",
    "build_middleware_chain_cognitive_flow",
]
