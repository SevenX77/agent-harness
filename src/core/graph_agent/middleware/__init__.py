"""MVP-3 middleware package: 4 core middleware (B3 simplification).

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
4. (TBD) Logging — emits the unified callback events; left for a
   later commit since the existing ``LoggingCallback`` already
   covers most of the surface and the middleware version requires
   the MVP-4 phase_executor rewrite to fully take over.

The fixed list :data:`DEFAULT_MIDDLEWARE_ORDER` exists so callers can
construct the chain without re-deriving the order. A regression test
in ``tests/graph_agent/conftest.py`` pins the sequence — silently
re-ordering middleware is precisely the kind of latent bug MVP-3 set
out to make impossible.

Note: the legacy ``cognitive/middlewares.py`` module remains wired
into ``phase_executor.py`` and ``harness.py`` during the MVP-3 → MVP-4
transition; the legacy module is scheduled for removal once MVP-4
phase_executor finishes its rewrite (the legacy ``ValidationMiddleware``
ctor signature is too entangled with the executor's runtime ctx for a
T11-scope swap).
"""

from __future__ import annotations

from .cognitive_flow import CognitiveFlowMiddleware
from .execution_control import ExecutionControlMiddleware
from .protocol_validation import ProtocolValidationMiddleware

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

__all__ = [
    "DEFAULT_MIDDLEWARE_ORDER",
    "CognitiveFlowMiddleware",
    "ExecutionControlMiddleware",
    "ProtocolValidationMiddleware",
]
