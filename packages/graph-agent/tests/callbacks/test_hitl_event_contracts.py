from __future__ import annotations

from graph_agent.callbacks.events import InterruptedEvent, ResumedEvent


def test_hitl_events_expose_checkpoint_and_namespace_contract() -> None:
    interrupted = InterruptedEvent(
        phase_name="main",
        thread_id="run-1",
        checkpoint_id="cp-1",
        checkpoint_ns="agent:main",
        namespace="agent:main",
        ns="agent:main",
    )
    resumed = ResumedEvent(
        thread_id="run-1",
        human_input="answer",
        resumed_from_phase="main",
        checkpoint_id="cp-1",
        checkpoint_ns="agent:main",
        namespace="agent:main",
        ns="agent:main",
    )

    assert interrupted.checkpoint_id == "cp-1"
    assert interrupted.checkpoint_ns == "agent:main"
    assert interrupted.namespace == "agent:main"
    assert interrupted.ns == "agent:main"
    assert resumed.checkpoint_id == "cp-1"
    assert resumed.checkpoint_ns == "agent:main"
    assert resumed.namespace == "agent:main"
    assert resumed.ns == "agent:main"
