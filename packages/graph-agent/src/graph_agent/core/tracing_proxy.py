"""TracingClientProxy — intercept LLM round-trips for Prompt Capture.

Wraps a LangChain chat-model client so that every call to :meth:`invoke`
(the entry point DeerFlow's agent loop uses) emits a
:class:`~graph_agent.callbacks.events.PromptCapturedEvent` through the
registered callbacks *before* the wrapped client runs. All other
attributes — streaming methods, tool-binding helpers, config-copy, the
`model` / `name` introspection fields used by LangGraph — are forwarded
unchanged via ``__getattr__`` so the wrapper stays transparent to the
agent loop.

Design invariants:

* **No surface changes to the wrapped client.** If Langchain adds a new
  method, it remains reachable through the proxy without a code edit
  here.
* **Failure in the callback chain never hides an LLM failure.** Callback
  exceptions are logged and swallowed; the wrapped LLM call still runs
  and its result (or exception) is the proxy's return value.
* **The proxy is per-phase.** Each phase builds its own proxy with the
  current phase_name + resolved model name, so Studio can render a
  well-scoped prompt history without the harness having to reach into
  ``threading.local``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from graph_agent.callbacks.events import PromptCapturedEvent

if TYPE_CHECKING:
    from collections.abc import Iterable

    from graph_agent.callbacks.base import Callback

logger = logging.getLogger(__name__)


class TracingClientProxy:
    """Transparent proxy around a chat-model client for prompt capture."""

    def __init__(
        self,
        wrapped_client: Any,
        callbacks: Iterable[Callback],
        *,
        phase_name: str,
        llm_role: str | None = None,
        resolved_model: str | None = None,
        sub_run_id: str | None = None,
        group_key: str | None = None,
    ) -> None:
        # The underscored names keep them out of the way of LangChain's
        # attribute introspection — any `chat_model.foo` lookup that does
        # not match one of the proxy's own methods falls through to the
        # wrapped client via __getattr__.
        self._wrapped = wrapped_client
        self._callbacks = list(callbacks)
        self._phase_name = phase_name
        self._llm_role = llm_role
        self._resolved_model = resolved_model
        self._sub_run_id = sub_run_id
        self._group_key = group_key
        self._loop_index = 0  # Incremented before emit, so the first call is 1.

    # ------------------------------------------------------------------
    # The one call we want to observe
    # ------------------------------------------------------------------

    def invoke(
        self,
        messages: Any,
        *args: Any,
        template_source: str | None = None,
        variables: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Emit ``prompt_captured``, then delegate to the wrapped client.

        ``template_source`` and ``variables`` are optional hints that
        advanced callers (Studio, test fixtures) may pass to enrich the
        captured event; DeerFlow's default agent loop omits them, and the
        event is still useful with them set to ``None`` / ``{}``.
        """
        self._loop_index += 1
        self._emit_prompt_captured(messages, template_source, variables)
        # The wrapped client's real invoke signature is (input, config=None)
        # in langchain-core; forward all positional + keyword args verbatim
        # so we never accidentally strip a future parameter.
        return self._wrapped.invoke(messages, *args, **kwargs)

    # ------------------------------------------------------------------
    # Transparent forwarding for everything else
    # ------------------------------------------------------------------

    def __getattr__(self, name: str) -> Any:
        # ``__getattr__`` is only consulted for attributes that are NOT set
        # on the proxy itself, so this is safe: proxy-owned state
        # (``_wrapped`` etc.) resolves directly and never hits this method.
        return getattr(self._wrapped, name)

    def __repr__(self) -> str:
        return (
            f"TracingClientProxy(phase={self._phase_name!r}, "
            f"role={self._llm_role!r}, model={self._resolved_model!r})"
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _emit_prompt_captured(
        self,
        messages: Any,
        template_source: str | None,
        variables: dict[str, Any] | None,
    ) -> None:
        try:
            event = PromptCapturedEvent(
                phase_name=self._phase_name,
                llm_role=self._llm_role,
                resolved_model=self._resolved_model,
                template_source=template_source,
                variables=variables or {},
                resolved_prompt=_normalise_messages(messages),
                sub_run_id=self._sub_run_id,
                group_key=self._group_key,
                loop_index=self._loop_index,
            )
        except Exception:
            # Swallow serialisation issues: a broken event must never take
            # down the actual LLM call the agent depends on.
            logger.exception(
                "TracingClientProxy: failed to build PromptCapturedEvent (phase=%s)",
                self._phase_name,
            )
            return

        for cb in self._callbacks:
            try:
                cb.on_event(event)
            except Exception:
                logger.exception(
                    "TracingClientProxy: callback %r raised on prompt_captured; "
                    "continuing with other callbacks",
                    type(cb).__name__,
                )


def _normalise_messages(messages: Any) -> list[dict[str, Any]]:
    """Best-effort conversion of LangChain message inputs to plain dicts.

    ``invoke`` accepts many shapes: a single string, a list of
    ``BaseMessage`` objects, a list of ``(role, content)`` tuples, or an
    already-serialised dict list. For the trace we store a light-weight
    list of dicts — Studio only needs role/content to render the prompt.
    """
    if messages is None:
        return []

    if isinstance(messages, str):
        return [{"role": "user", "content": messages}]

    if isinstance(messages, dict):
        return [messages]

    if isinstance(messages, (list, tuple)):
        out: list[dict[str, Any]] = []
        for item in messages:
            if isinstance(item, dict):
                out.append(item)
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                out.append({"role": str(item[0]), "content": item[1]})
            else:
                # LangChain BaseMessage objects expose type/content attrs.
                role = getattr(item, "type", None) or getattr(item, "role", None)
                content = getattr(item, "content", None)
                if role is not None or content is not None:
                    out.append({"role": str(role or "unknown"), "content": content})
                else:
                    out.append({"role": "unknown", "content": str(item)})
        return out

    # Anything else (LangChain PromptValue, rare exotic types) falls back
    # to a single serialised payload so the event still round-trips.
    return [{"role": "unknown", "content": str(messages)}]


__all__ = ["TracingClientProxy"]
