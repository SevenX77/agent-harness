"""MVP-3 middleware package: core middleware and MVP0 order contracts.

The package replaces the legacy decorator-style middleware chain that
used to live in ``cognitive/middlewares.py`` with four single-purpose
classes the framework wires in a fixed topological order:

1. :class:`ProtocolValidationMiddleware` (T7) — state contract guards
   (BusinessData / FrameworkState invariants + SchemaEngine validate
   on the after-model boundary). Runs first because every later
   middleware assumes the state shape is already valid.
2. :class:`CognitiveFlowMiddleware` (T8) — finish_task interception
   plus attended/unattended clarification handling.
3. :class:`ExecutionControlMiddleware` (T9) — iteration counter,
   dead-end detection, lightweight loop detection, metrics
   aggregation.
4. (TBD) Tracing / ToolError / LoopDetection — PR γ0 locks their
   future order as string contracts; PR β wires the runtime classes.

The fixed list :data:`DEFAULT_MIDDLEWARE_ORDER` exists so callers can
construct the chain without re-deriving the order. A regression test
in ``tests/graph_agent/conftest.py`` pins the sequence — silently
re-ordering middleware is precisely the kind of latent bug MVP-3 set
out to make impossible.

Note: Phase 3 M7 retired the legacy ``cognitive/middlewares.py``
parallel pipeline (PHASE3_DESIGN.md §3); after Strategy C gave every
live LLM phase a strongly-typed ``output_schema``, all finish_task
routing flows through this MVP-3 middleware chain exclusively. The
remaining helpers in ``cognitive/middlewares.py`` are shared utilities
only (working memory, dead-end pruning, agent-loop iteration,
unattended clarification, ``create_custom_middlewares``).
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
