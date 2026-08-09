"""LangChain callback bridge: tool reporting and per-phase token accounting."""

from __future__ import annotations

import json
import logging
import time
from contextvars import ContextVar
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler

from graph_agent.callbacks.base import Callback
from graph_agent.callbacks.token_accounting import account_llm_call

logger = logging.getLogger(__name__)

_CURRENT_TOOL_CALLBACKS: ContextVar[dict[str, Any] | None] = ContextVar(
    "graph_agent_current_tool_callbacks",
    default=None,
)


def current_tool_callback_context() -> dict[str, Any] | None:
    """Return callbacks/phase for the tool currently invoked by LangChain."""
    return _CURRENT_TOOL_CALLBACKS.get()


def _extract_text_content(content: Any) -> str:
    """Extract user-visible text from provider-specific response content."""
    if isinstance(content, str):
        return content
    if not content:
        return ""
    if isinstance(content, list):
        text_parts: list[str] = []
        for block in content:
            text = _extract_text_block(block)
            if text:
                text_parts.append(text)
        return "\n".join(text_parts).strip()
    return str(content)


def _extract_text_block(block: Any) -> str:
    if isinstance(block, str):
        return block
    if not isinstance(block, dict):
        return ""
    text = block.get("text")
    if not isinstance(text, str) or not text:
        return ""
    if block.get("type") == "thinking":
        return ""
    return text


def _first_generation(generations: Any) -> Any | None:
    if not generations or len(generations) <= 0:
        return None
    gen_list = generations[0]
    if not gen_list or len(gen_list) <= 0:
        return None
    return gen_list[0]


def _extract_prompt_completion_tokens(usage: Any) -> tuple[int, int] | None:
    if not isinstance(usage, dict):
        return None
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    if not prompt_tokens and not completion_tokens:
        return None
    return (int(prompt_tokens or 0), int(completion_tokens or 0))


def _extract_input_output_tokens(usage: Any) -> tuple[int, int] | None:
    if not isinstance(usage, dict):
        return None
    input_tokens = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    if not input_tokens and not output_tokens:
        return None
    return (input_tokens, output_tokens)


class _HarnessCallbackBridge(BaseCallbackHandler):
    """Bridge LangChain Agent events into GraphAgent callback hooks."""

    def __init__(
        self,
        phase_name: str,
        callbacks: list[Callback],
        metrics: dict[str, Any],
        *,
        max_tool_calls: int = 0,
    ) -> None:
        self.phase_name = phase_name
        self._callbacks = callbacks
        self._metrics = metrics
        self._pending_tools: dict[str, dict[str, Any]] = {}
        self._tool_call_count: int = 0
        self._max_tool_calls: int = max(0, int(max_tool_calls))

    def should_block_tool_call(self) -> bool:
        """Return True when phase-level tool budget is exhausted."""
        return self._max_tool_calls > 0 and self._tool_call_count >= self._max_tool_calls

    def on_llm_end(self, response: Any, *, run_id: UUID | None = None, **kwargs: Any) -> None:
        """Fold what the call cost into the phase's running totals.

        Reporting the call is the chat model's, not this handler's: the model
        knows the moment a round-trip starts, and a run watching itself needs
        that moment far more than it needs a second copy of the ending. What is
        left here is the accounting, because the phase's metrics dict is a piece
        of phase state the model has no business holding.
        """
        del kwargs, run_id
        input_tokens, output_tokens = self._extract_tokens(response)
        account_llm_call(self._metrics, input_tokens, output_tokens)

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Capture tool args and start time for tracing."""
        if run_id is None:
            return
        tool_name = str(serialized.get("name") or kwargs.get("name") or "unknown")
        try:
            parsed = json.loads(input_str) if input_str else {}
            args = parsed if isinstance(parsed, dict) else {"input": parsed}
        except Exception as exc:
            logger.warning("[Bridge] Tool input JSON parse failed in %s: %s", self.phase_name, exc)
            args = {"input": input_str}
        self._pending_tools[str(run_id)] = {
            "tool_name": tool_name,
            "args": args,
            "start_mono": time.monotonic(),
            "context_token": _CURRENT_TOOL_CALLBACKS.set(
                {
                    "phase_name": self.phase_name,
                    "callbacks": self._callbacks,
                }
            ),
        }

    def on_tool_end(self, output: Any, *, run_id: UUID | None = None, **kwargs: Any) -> None:
        """Forward tool completion to GraphAgent callbacks."""
        run_key = str(run_id) if run_id is not None else ""
        pending = self._pending_tools.pop(run_key, {})
        token = pending.get("context_token")
        if token is not None:
            _CURRENT_TOOL_CALLBACKS.reset(token)
        tool_name = pending.get("tool_name") or kwargs.get("name", "unknown")
        args = pending.get("args", {})
        self._tool_call_count += 1

        output_text = str(output)
        start_mono = pending.get("start_mono")
        duration_ms = None
        if isinstance(start_mono, float):
            duration_ms = (time.monotonic() - start_mono) * 1000.0

        for cb in self._callbacks:
            try:
                cb.on_tool_call(
                    self.phase_name,
                    str(tool_name),
                    args if isinstance(args, dict) else {},
                    output_text,
                    duration_ms=duration_ms,
                )
            except TypeError:
                try:
                    cb.on_tool_call(
                        self.phase_name,
                        str(tool_name),
                        args if isinstance(args, dict) else {},
                        output_text,
                    )
                except Exception as exc:
                    logger.warning("[Bridge] callback error in %s: %s", self.phase_name, exc)
            except Exception as exc:
                logger.warning("[Bridge] callback error in %s: %s", self.phase_name, exc)

    def on_llm_error(
        self, error: BaseException, *, run_id: UUID | None = None, **kwargs: Any
    ) -> None:
        del kwargs
        del run_id
        logger.warning("[Bridge] LLM error in %s: %s", self.phase_name, error)

    def on_tool_error(
        self, error: BaseException, *, run_id: UUID | None = None, **kwargs: Any
    ) -> None:
        del kwargs
        run_key = str(run_id) if run_id is not None else ""
        pending = self._pending_tools.pop(run_key, {})
        token = pending.get("context_token")
        if token is not None:
            _CURRENT_TOOL_CALLBACKS.reset(token)
        logger.warning("[Bridge] Tool error in %s: %s", self.phase_name, error)

    @staticmethod
    def _extract_tokens(response: Any) -> tuple[int, int]:
        """Extract token usage from provider-specific LLM result structures."""
        llm_output = getattr(response, "llm_output", None) or {}
        if isinstance(llm_output, dict):
            tokens = _extract_prompt_completion_tokens(llm_output.get("token_usage", {}))
            if tokens is not None:
                return tokens

        generations = getattr(response, "generations", None)
        first_generation = _first_generation(generations)
        if first_generation is None:
            return (0, 0)

        gen_info = getattr(first_generation, "generation_info", None) or {}
        tokens = _extract_prompt_completion_tokens(gen_info.get("usage", {}))
        if tokens is not None:
            return tokens

        message = getattr(first_generation, "message", None)
        response_metadata = getattr(message, "response_metadata", None) or {}
        if isinstance(response_metadata, dict):
            tokens = _extract_input_output_tokens(response_metadata.get("usage", {}))
            if tokens is not None:
                return tokens

        return (0, 0)


__all__ = [
    "_HarnessCallbackBridge",
    "_extract_text_content",
]
