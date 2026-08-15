"""Middleware package: the live chain's classes and its order contract.

Every behaviour the agent loop layers on top of a plain ``create_agent``
call lives here, as single-purpose middleware classes the assembler
wires in a fixed topological order:

1. :class:`ProtocolValidationMiddleware` — state contract guards
   (BusinessData / FrameworkState invariants + SchemaEngine validate
   on the after-model boundary). Runs first because every later
   middleware assumes the state shape is already valid.
2. :class:`CognitiveFlowMiddleware` — cognitive tool interception:
   finish_task, ask_clarification, and the working-memory / ambiguity /
   context-access tools that read and write ``FrameworkState``.
3. :class:`ExecutionControlMiddleware` — iteration counter, dead-end
   detection, lightweight loop detection, metrics aggregation.
4. :class:`CompactionMiddleware` — summarizes messages out of context
   before the window overflows, writing the removed text to a sidecar.
5. :class:`TracingMiddleware` · 6. :class:`ToolErrorHandlingMiddleware`
   · 7. :class:`LoopDetectionMiddleware` — observation and tool-error
   handling.
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

# Fixed topological order for the MVP-3 middleware chain.
#
# Slot 1: ProtocolValidation — runs first, guards state contracts.
# Slot 2: CognitiveFlow — finish_task / clarification routing.
# Slot 3: ExecutionControl — runtime ops (iteration / dead-end / loop).
# Slot 4 reserved for the future LoggingMiddleware (see module docstring).
#
# Tests in ``conftest.py`` pin this order; do not re-order without
# updating the regression test as well.
DEFAULT_MIDDLEWARE_ORDER: tuple[type, ...] = (
    ProtocolValidationMiddleware,
    CognitiveFlowMiddleware,
    ExecutionControlMiddleware,
)

# Compaction (decision 2026-08-15 §3.6) sits right after the MVP-3 core trio:
# it acts through ``before_model`` (guaranteed to land before the model call
# wherever it sits), and ToolHistoryIntegrity repairs the outgoing request
# later inside ``wrap_model_call``, so the slot only needs to stay behind the
# ProtocolValidation state guard and keep the core trio a contract prefix.
MVP0_MIDDLEWARE_ORDER_CONTRACT: tuple[str, ...] = (
    "ProtocolValidation",
    "CognitiveFlow",
    "ExecutionControl",
    "Compaction",
    "Tracing",
    "ToolError",
    "LoopDetection",
    "ExitControl",
)

# Backward-compatible public name used by the γ0 TDD tests and future PR β.
DEFAULT_MIDDLEWARE_ORDER_CONTRACT = MVP0_MIDDLEWARE_ORDER_CONTRACT

from graph_agent.middleware.factory import (  # noqa: E402
    MIDDLEWARE_ORDER_CONTRACT,
    build_middleware_chain,
    build_middleware_chain_cognitive_flow,
)

__all__ = [
    "DEFAULT_MIDDLEWARE_ORDER",
    "DEFAULT_MIDDLEWARE_ORDER_CONTRACT",
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
