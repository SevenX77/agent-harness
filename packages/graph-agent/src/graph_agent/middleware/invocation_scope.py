"""Which invocation of a phase is running right now.

A middleware instance is built once per phase node, at graph-assembly time
(``core/graph_assembler.build_middleware_chain`` call site), and the assembled
graph is then invoked again for every batch item, every loop round and every
resume. So any per-invocation state a middleware keeps — a turn counter, a
nudge budget — has to be keyed by the invocation, or item 2 opens holding
item 1's numbers.

The key is defined ONCE here because two middlewares in the same chain need
the same answer and already drifted apart: ``ExitControlMiddleware`` was fixed
to scope its budgets this way while ``ExecutionControlMiddleware`` kept a plain
instance counter, which is how one continuous turn count came to span two
independent executions in the field.
"""

from __future__ import annotations

#: The key to use when no graph invocation is in progress at all — a hook
#: called directly rather than through ``agent_graph.invoke``. That is not a
#: broken state: outside a graph there is exactly one invocation, so one
#: constant key is the right answer rather than a missing one.
NO_RUNNABLE_CONTEXT = "no-runnable-context"


def agent_invocation_key() -> str:
    """Identify ONE invocation of this phase, not one run.

    ``thread_id`` is a run constant, so on its own it collapses every iteration
    of an iterated phase into a single scope: item 2 of a batch opens with item
    1's spent nudges and its turn count (field evidence: run
    2026-08-15T10-19-55_df555c19, counter 1..8 for chapter 1 then 9 for chapter
    2; run 2026-08-19T01-56-15_d0733362, the same shape on the turn counter).

    The assembler therefore stamps ``agent_invocation_id`` on the config it
    hands ``agent_graph.invoke`` — the same channel ``max_iterations`` travels
    on, which is the evidence that a custom ``configurable`` key reaches a
    middleware hook. ``checkpoint_ns`` cannot serve here: what LangGraph
    exposes to a hook is the PER-HOOK namespace (measured:
    ``ExitControlMiddleware.before_model:<uuid>``, a fresh uuid per call), so
    keying on it would reset the scope every turn.
    """
    from langgraph.config import get_config

    try:
        configurable = get_config().get("configurable", {})
    except RuntimeError:
        return NO_RUNNABLE_CONTEXT
    thread_id = str(configurable.get("thread_id") or "default")
    invocation_id = str(configurable.get("agent_invocation_id") or "")
    return f"{thread_id}|{invocation_id}"


def next_invocation_call_index(counts: dict[str, int]) -> int:
    """The 1-based index of the LLM call starting now, within THIS invocation.

    Same disease, one layer up: the chat model is built once per phase node
    (``_resolve_phase_chat_model``) and reused for every batch item, so a plain
    counter on it keeps climbing across items — measured on the batch fixture in
    ``tests/core/test_agent_loop_iteration_is_per_execution.py`` as loop_index
    1..6 for two items that each spent three calls, where the truth is 1,2,3
    then 1,2,3 again.

    Counting per LLM CALL rather than per model turn is deliberate and stays:
    one turn can spend several calls (the same fixture shows turn 1 spending
    two), so this number and ``AgentLoopIterationEvent.iteration`` answer
    different questions and neither can be derived from the other.
    """
    key = agent_invocation_key()
    index = counts.get(key, 0) + 1
    counts[key] = index
    return index
