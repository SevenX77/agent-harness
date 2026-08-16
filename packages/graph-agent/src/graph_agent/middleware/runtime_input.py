"""Deliver an AGENT phase's runtime inputs to the model.

The v0.3.0 assembler bakes the cognitive-template system prompt at assembly
time, so ``{key}`` placeholders authored in role/goal/steps stay literal and
the dispatched phase inputs never reach the model at all (field evidence: a
request containing exactly one static SystemMessage). This middleware closes
that gap per model call:

- renders ``{key}`` placeholders in the system message against the blackboard
  view (same context the legacy prompt path used);
- delivers the phase's declared inputs as a JSON block, on every model call.

Delivery is per call because this is a ``wrap_model_call`` middleware: the block
is handed to the model but never written back to state. ``ModelRequest.messages``
is rebuilt from ``state["messages"]`` on every model node entry, and only the
model's own output is merged back. So each turn starts without the block and
must be given it again.

The criterion for "does this request already have it" is the block's own
content. It used to be "does the history hold ANY HumanMessage", which is a
proxy for the wrong thing: nudges, dead-end warnings and loop diagnostics are
all HumanMessages written into the conversation by sibling middlewares, so the
first nudge a phase received silenced its own inputs for every later turn of
that phase (field evidence: run ``2026-08-15T12-40-22_bb6e358a``, where every
never-nudged phase got one delivery per model call and every nudged phase got
exactly one in total).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest
from langchain_core.messages import HumanMessage, SystemMessage

from graph_agent.callbacks.emit import _safe_emit_event
from graph_agent.callbacks.events import RuntimeInputInjectedEvent
from graph_agent.core.template import _safe_render_template

#: Opening line of the engine's input block. It is also the block's identity:
#: a message that starts a delivery of this phase's inputs carries it verbatim.
_INPUT_BLOCK_HEADER = "以下是本阶段的输入数据(JSON):\n"


def _blackboard_view(state: Any) -> dict[str, Any]:
    data = state.get("data") if isinstance(state, dict) else None
    if data is None:
        return {}
    dumped = data.model_dump() if hasattr(data, "model_dump") else dict(data)
    return dumped if isinstance(dumped, dict) else {}


class RuntimeInputMiddleware(AgentMiddleware):
    """Per-model-call placeholder rendering + input delivery for AGENT phases."""

    def __init__(
        self,
        phase_name: str,
        input_keys: tuple[str, ...],
        *,
        callbacks: Sequence[Any] | None = None,
    ) -> None:
        super().__init__()
        self._phase_name = phase_name
        self._input_keys = input_keys
        self._callbacks = callbacks

    def _transformed_request(self, request: ModelRequest) -> ModelRequest:
        view = _blackboard_view(request.state)

        system_message = request.system_message
        if system_message is not None and isinstance(system_message.content, str):
            rendered = _safe_render_template(
                system_message.content, view, phase_name=self._phase_name
            )
            if rendered != system_message.content:
                system_message = SystemMessage(content=rendered)

        messages = list(request.messages)
        payload = {key: view[key] for key in self._input_keys if key in view} or view
        content = _INPUT_BLOCK_HEADER + json.dumps(
            payload, ensure_ascii=False, default=str
        )

        # Idempotent on its own output: the block identifies itself by content,
        # so re-running over an already-transformed request changes nothing,
        # while a sibling middleware's HumanMessage — or another phase's block —
        # never suppresses this phase's delivery.
        if not any(
            isinstance(m, HumanMessage) and m.content == content for m in messages
        ):
            messages.insert(0, HumanMessage(content=content))
            # Glass-box decision 2026-08-13 D4 lists 「注了输入」 among the
            # decisions a machine reports, against 路过 which stays silent: one
            # event per turn actually handed the inputs, none for a skip.
            delivered = sorted(str(key) for key in payload)
            _safe_emit_event(
                self._callbacks,
                RuntimeInputInjectedEvent(
                    phase_name=self._phase_name,
                    keys=delivered,
                    message=(
                        f"Handed phase {self._phase_name!r} the runtime input(s) "
                        f"for this model call: {', '.join(delivered) or '(empty)'}."
                    ),
                ),
            )

        return request.override(system_message=system_message, messages=messages)

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Any],
    ) -> Any:
        return handler(self._transformed_request(request))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Any],
    ) -> Any:
        # Async graph executions dispatch to the async hook only; without this
        # counterpart input delivery silently never runs there.
        return await handler(self._transformed_request(request))
