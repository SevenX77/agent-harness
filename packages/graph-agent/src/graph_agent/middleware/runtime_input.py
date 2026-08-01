"""Deliver an AGENT phase's runtime inputs to the model.

The v0.3.0 assembler bakes the cognitive-template system prompt at assembly
time, so ``{key}`` placeholders authored in role/goal/steps stay literal and
the dispatched phase inputs never reach the model at all (field evidence: a
request containing exactly one static SystemMessage). This middleware closes
that gap per model call:

- renders ``{key}`` placeholders in the system message against the blackboard
  view (same context the legacy prompt path used);
- seeds the first user turn with the phase's declared inputs when the
  conversation carries no human message yet.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest
from langchain_core.messages import HumanMessage, SystemMessage

from graph_agent.core.template import _safe_render_template


def _blackboard_view(state: Any) -> dict[str, Any]:
    data = state.get("data") if isinstance(state, dict) else None
    if data is None:
        return {}
    dumped = data.model_dump() if hasattr(data, "model_dump") else dict(data)
    return dumped if isinstance(dumped, dict) else {}


class RuntimeInputMiddleware(AgentMiddleware):
    """Per-model-call rendering + first-turn input seeding for AGENT phases."""

    def __init__(self, phase_name: str, input_keys: tuple[str, ...]) -> None:
        super().__init__()
        self._phase_name = phase_name
        self._input_keys = input_keys

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
        if not any(isinstance(m, HumanMessage) for m in messages):
            payload = {
                key: view[key] for key in self._input_keys if key in view
            } or view
            messages.insert(
                0,
                HumanMessage(
                    content=(
                        "以下是本阶段的输入数据(JSON):\n"
                        + json.dumps(payload, ensure_ascii=False, default=str)
                    )
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
