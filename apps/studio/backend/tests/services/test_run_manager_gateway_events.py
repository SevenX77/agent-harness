from __future__ import annotations


def test_studio_queue_callback_serializes_gateway_fallback_event() -> None:
    from app.services.run_manager import _queue_event_subscriber
    from graph_agent_gateway.events import LLMFallbackEvent

    class RecordingQueue:
        def __init__(self) -> None:
            self.items: list[dict[str, object]] = []

        def put(self, item: dict[str, object]) -> None:
            self.items.append(item)

    queue = RecordingQueue()
    subscriber = _queue_event_subscriber(queue)

    subscriber(
        LLMFallbackEvent(
            phase_name="e2e",
            from_provider="primary:route",
            to_provider="fallback:route",
            reason="RuntimeError: probe failed",
            context={
                "role_name": "graph_agent",
                "fallback_decision": "fallback_allowed",
            },
        )
    )

    assert queue.items == [
        {
            "type": "event",
            "event": {
                "event_type": "llm_fallback",
                "phase_name": "e2e",
                "from_provider": "primary:route",
                "to_provider": "fallback:route",
                "reason": "RuntimeError: probe failed",
                "code": "[F-v3-gateway-llm-fallback]",
                "context": {
                    "role_name": "graph_agent",
                    "fallback_decision": "fallback_allowed",
                },
            },
        }
    ]
