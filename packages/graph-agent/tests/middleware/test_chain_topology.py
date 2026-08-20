"""The middleware chain's order is a contract, and this pins it.

Re-ordering the chain silently is the latent bug class the fixed order exists to
make impossible, and 2026-08-20 showed what that bug looks like when nothing
catches it: with tracing sitting BELOW the middlewares that answer tool calls
themselves, `ToolCallStartedEvent` was emitted zero times in a real run while
every layer above it — the type, the export, the frontend mirror, the trace
renderer — looked perfectly wired.

The order is stated once, in `MVP0_MIDDLEWARE_ORDER_CONTRACT`. There used to be a
second statement of the same fact (`DEFAULT_MIDDLEWARE_ORDER`, a three-class
tuple asserted to equal the contract's first three), and it is gone: one fact
described in two places is a fact that can disagree with itself, and this move
is precisely the edit that would have made it disagree.
"""

from __future__ import annotations

from graph_agent.core.io_manager import IOManager
from graph_agent.middleware import (
    MVP0_MIDDLEWARE_ORDER_CONTRACT,
    CognitiveFlowMiddleware,
    CompactionMiddleware,
    ExecutionControlMiddleware,
    ExitControlMiddleware,
    LoopDetectionMiddleware,
    ProtocolValidationMiddleware,
    ToolErrorHandlingMiddleware,
    TracingMiddleware,
)
from graph_agent.middleware.factory import build_middleware_chain


def test_the_chain_order_is_the_contract() -> None:
    assert MVP0_MIDDLEWARE_ORDER_CONTRACT == (
        "Tracing",
        "ProtocolValidation",
        "CognitiveFlow",
        "ExecutionControl",
        "Compaction",
        "ToolError",
        "LoopDetection",
        "ExitControl",
    )


def test_tracing_wraps_every_middleware_that_can_answer_a_tool_call() -> None:
    """The observer sits outside the deciders, or it observes only their leftovers.

    `CognitiveFlowMiddleware` answers the tools it intercepts without calling
    `handler(request)`, so anything below it in the chain never sees those calls
    — and those are most of the calls an agent phase makes. Same reasoning as
    registering the logger first in Django's `MIDDLEWARE` or Express's
    `app.use`: the layer that must see everything goes on the outside.
    """
    order = MVP0_MIDDLEWARE_ORDER_CONTRACT
    for decider in ("CognitiveFlow", "ToolError"):
        assert order.index("Tracing") < order.index(decider), (
            f"{decider} can answer a tool call without calling through, so "
            "Tracing placed after it stops seeing those calls entirely"
        )


def test_state_guards_still_precede_every_middleware_that_reads_state() -> None:
    """Moving the observer must not cost the state guard its position.

    ProtocolValidation runs before CognitiveFlow / ExecutionControl / Compaction
    because each of them assumes the state shape is already valid
    (CognitiveFlow's `IOManager.resolve_hoist` assumes `state['data']` carries no
    `_`-prefixed keys). Tracing is exempt: it reads no state, only tool calls.
    """
    order = MVP0_MIDDLEWARE_ORDER_CONTRACT
    for reader in ("CognitiveFlow", "ExecutionControl", "Compaction", "ExitControl"):
        assert order.index("ProtocolValidation") < order.index(reader)


def test_each_slot_is_a_distinct_middleware() -> None:
    assert len(MVP0_MIDDLEWARE_ORDER_CONTRACT) == len(set(MVP0_MIDDLEWARE_ORDER_CONTRACT))


def test_the_built_chain_matches_the_contract() -> None:
    """The contract is only worth pinning if the factory actually follows it.

    Compared as CLASSES, not as names derived from them: a slot's contract name
    is deliberately shorter than its class name (`ToolError` /
    `ToolErrorHandlingMiddleware`), and a test that re-derives one from the other
    would be asserting a naming convention instead of the order it exists for.
    """
    chain = build_middleware_chain(io_manager=IOManager([]), phase_name="main")

    assert [type(middleware) for middleware in chain] == [
        TracingMiddleware,
        ProtocolValidationMiddleware,
        CognitiveFlowMiddleware,
        ExecutionControlMiddleware,
        CompactionMiddleware,
        ToolErrorHandlingMiddleware,
        LoopDetectionMiddleware,
        ExitControlMiddleware,
    ]
