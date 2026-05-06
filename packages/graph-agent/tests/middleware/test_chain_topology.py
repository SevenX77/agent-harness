"""MVP-3 T11: middleware chain topological order regression test.

The test pins the design.md §5.6 specification: the four-slot
middleware chain runs in the order
``ProtocolValidation → CognitiveFlow → ExecutionControl`` (Logging
slot reserved for a future commit). Re-ordering the slots silently
is the latent bug class the fixed order was introduced to make
impossible — this test catches a slot swap at collection time
rather than waiting for a tool-failure scenario to surface it.
"""

from __future__ import annotations

from graph_agent.middleware import (
    DEFAULT_MIDDLEWARE_ORDER,
    CognitiveFlowMiddleware,
    ExecutionControlMiddleware,
    ProtocolValidationMiddleware,
)


def test_middleware_chain_topological_order_is_fixed() -> None:
    """ProtocolValidation runs first, CognitiveFlow second, ExecutionControl third.

    ProtocolValidation must precede CognitiveFlow because state
    contract checks gate every later middleware (CognitiveFlow's
    ``IOManager.resolve_hoist`` assumes ``state['data']`` carries no
    ``_``-prefixed keys when it runs). CognitiveFlow must precede
    ExecutionControl because dead-end / loop detection relies on
    ToolMessages already routed through CognitiveFlow's
    ``wrap_tool_call``.
    """
    assert (
        ProtocolValidationMiddleware,
        CognitiveFlowMiddleware,
        ExecutionControlMiddleware,
    ) == DEFAULT_MIDDLEWARE_ORDER, (
        "DEFAULT_MIDDLEWARE_ORDER drifted from the design.md §5.6 "
        f"specification; got {[c.__name__ for c in DEFAULT_MIDDLEWARE_ORDER]!r}"
    )


def test_middleware_chain_classes_are_distinct() -> None:
    """Each slot must be a unique middleware class.

    Repeating the same class twice is meaningless (the registry
    treats identity, not substitution); we pin uniqueness so the
    factory cannot accidentally double-register.
    """
    assert len(DEFAULT_MIDDLEWARE_ORDER) == len(set(DEFAULT_MIDDLEWARE_ORDER))


def test_middleware_chain_names_match_design_doc() -> None:
    """Names track design.md §5.2 / §5.3 / §5.4 verbatim."""
    names = [cls.__name__ for cls in DEFAULT_MIDDLEWARE_ORDER]
    assert names == [
        "ProtocolValidationMiddleware",
        "CognitiveFlowMiddleware",
        "ExecutionControlMiddleware",
    ]
