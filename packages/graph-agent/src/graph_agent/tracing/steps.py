"""Who owns a step, and therefore how a step is reported.

A step is one unit of work a run performs and reports on: it starts, it runs,
it ends. Before this module existed the concept had no home, so each place that
happened to notice a step re-decided its properties — the middleware minted an
identity and timed the call, the agent node built the closing event again with
an identity of its own.

The reporter owns those decisions. A caller says what is happening; it does not
say how that becomes events, which callbacks hear about it, or how long the
step took.

Deliberately not owned here: writing to disk, and the shape of the transport.
The reporter hands events to the run's callbacks through the one dispatch the
package already has, and what the callbacks do with them is theirs.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Literal

from langchain_core.messages import AIMessage, BaseMessage

from graph_agent.callbacks.emit import _safe_emit_event
from graph_agent.callbacks.events import (
    LLMCallEvent,
    LLMDeltaEvent,
    PromptCapturedEvent,
    ToolCallEvent,
    ToolCallStartedEvent,
)
from graph_agent.callbacks.token_accounting import token_usage_of


class ToolCallStep:
    """A tool call that has been announced and is now running.

    ``finished`` is the caller's to invoke because only the caller knows what
    the tool answered — and whether it answered at all. A step nobody finishes
    reported that it started, which is true and is the most that can be said.
    """

    def __init__(
        self,
        reporter: StepReporter,
        *,
        tool_call_id: str,
        tool_name: str,
        args: dict[str, Any],
        parent_node_id: str | None,
        node_type: str | None,
        started_at: float,
    ) -> None:
        self._reporter = reporter
        self._tool_call_id = tool_call_id
        self._tool_name = tool_name
        self._args = args
        self._parent_node_id = parent_node_id
        self._node_type = node_type
        self._started_at = started_at

    def finished(self, result: str) -> None:
        self._reporter._emit(
            ToolCallEvent(
                tool_call_id=self._tool_call_id,
                phase_name=self._reporter.phase_name,
                tool_name=self._tool_name,
                args=self._args,
                result=result,
                duration_ms=(time.perf_counter() - self._started_at) * 1000.0,
                parent_node_id=self._parent_node_id,
                node_type=self._node_type,
            )
        )


class LlmCallStep:
    """An LLM round-trip that has been announced and is now in flight.

    ``finished`` is handed the answer itself, not numbers read out of it. What a
    call cost and which model served it are facts the answer carries, and every
    reader that extracted them separately is how two reports of one call came to
    disagree.

    ``delta`` reports the answer arriving. Every piece repeats ``step_id``
    because an agent turn runs several calls at once: neither arrival order nor
    the phase can say which call a piece belongs to, and a piece nobody can
    place is a piece nobody can show.
    """

    def __init__(
        self,
        reporter: StepReporter,
        *,
        step_id: str,
        parent_node_id: str | None,
        node_type: str | None,
        sub_run_id: str | None,
        group_key: str | None,
    ) -> None:
        self._reporter = reporter
        self._step_id = step_id
        self._parent_node_id = parent_node_id
        self._node_type = node_type
        self._sub_run_id = sub_run_id
        self._group_key = group_key

    @property
    def step_id(self) -> str:
        return self._step_id

    def delta(
        self,
        text: str,
        *,
        channel: Literal["text", "thinking"] = "text",
        restarts_step: bool = False,
    ) -> None:
        """Report that a bit more of this step's output just arrived."""
        self._reporter._emit(
            LLMDeltaEvent(
                phase_name=self._reporter.phase_name,
                step_id=self._step_id,
                channel=channel,
                text=text,
                restarts_step=restarts_step,
                sub_run_id=self._sub_run_id,
                group_key=self._group_key,
            )
        )

    def finished(self, answer: AIMessage) -> None:
        input_tokens, output_tokens = token_usage_of(answer)
        metadata = dict(answer.response_metadata or {})
        model = metadata.get("model_name") or metadata.get("model")
        self._reporter._emit(
            LLMCallEvent(
                phase_name=self._reporter.phase_name,
                step_id=self._step_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                resolved_model=str(model) if model else None,
                response_data=_answer_report(answer, metadata),
                parent_node_id=self._parent_node_id,
                node_type=self._node_type,
                sub_run_id=self._sub_run_id,
                group_key=self._group_key,
            )
        )


class StepReporter:
    """The one exit a phase's steps are reported through.

    Bound to a phase and its callbacks once, so no call site threads either of
    them into an event again.
    """

    def __init__(self, *, callbacks: Any, phase_name: str) -> None:
        # Kept exactly as handed over: a run's callbacks arrive as a sequence, a
        # single sink object or a plain subscriber, and the package's dispatch
        # already knows all three. Normalising here would be a second opinion
        # about what a callback is.
        self._callbacks = callbacks
        self.phase_name = phase_name

    @contextmanager
    def llm_call(
        self,
        messages: list[BaseMessage],
        *,
        llm_role: str | None = None,
        resolved_model: str | None = None,
        loop_index: int = 1,
        parent_node_id: str | None = None,
        node_type: str | None = None,
        sub_run_id: str | None = None,
        group_key: str | None = None,
        template_source: str | None = None,
        variables: dict[str, Any] | None = None,
    ) -> Iterator[LlmCallStep]:
        """Announce a round-trip, then hand back the step that is now in flight.

        Announcing before the request leaves is the whole point: a round-trip is
        the longest thing a run does, and a report written afterwards can only
        say it is over.
        """
        step_id = uuid.uuid4().hex
        self._emit(
            PromptCapturedEvent(
                phase_name=self.phase_name,
                step_id=step_id,
                llm_role=llm_role,
                resolved_model=resolved_model,
                resolved_prompt=[_prompt_entry(message) for message in messages],
                template_source=template_source,
                variables=dict(variables or {}),
                loop_index=loop_index,
                sub_run_id=sub_run_id,
                group_key=group_key,
            )
        )
        yield LlmCallStep(
            self,
            step_id=step_id,
            parent_node_id=parent_node_id,
            node_type=node_type,
            sub_run_id=sub_run_id,
            group_key=group_key,
        )

    @contextmanager
    def tool_call(
        self,
        *,
        tool_call_id: str,
        tool_name: str,
        args: dict[str, Any] | None = None,
        parent_node_id: str | None = None,
        node_type: str | None = "tool",
    ) -> Iterator[ToolCallStep]:
        """Announce a tool call, then hand back the step that is now running."""
        resolved_args = dict(args or {})
        self._emit(
            ToolCallStartedEvent(
                tool_call_id=tool_call_id,
                phase_name=self.phase_name,
                tool_name=tool_name,
                args=resolved_args,
                parent_node_id=parent_node_id,
                node_type=node_type,
            )
        )
        yield ToolCallStep(
            self,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            args=resolved_args,
            parent_node_id=parent_node_id,
            node_type=node_type,
            started_at=time.perf_counter(),
        )

    def completed_tool_call(
        self,
        *,
        tool_call_id: str,
        tool_name: str,
        args: dict[str, Any] | None = None,
        result: str,
        parent_node_id: str | None = None,
        node_type: str | None = None,
    ) -> None:
        """Report a call that was only noticed once it was already over.

        No duration and no start event: both would have to be invented, and an
        invented moment is worse than an absent one.
        """
        self._emit(
            ToolCallEvent(
                tool_call_id=tool_call_id,
                phase_name=self.phase_name,
                tool_name=tool_name,
                args=dict(args or {}),
                result=result,
                duration_ms=None,
                parent_node_id=parent_node_id,
                node_type=node_type,
            )
        )

    def _emit(
        self,
        event: ToolCallStartedEvent
        | ToolCallEvent
        | PromptCapturedEvent
        | LLMCallEvent
        | LLMDeltaEvent,
    ) -> None:
        _safe_emit_event(self._callbacks, event)


def _prompt_entry(message: BaseMessage) -> dict[str, Any]:
    """The light-weight shape a reader renders: who spoke and what they said."""
    return {"role": str(getattr(message, "type", None) or "unknown"), "content": message.content}


def _answer_report(answer: AIMessage, metadata: dict[str, Any]) -> dict[str, Any]:
    """What the answer says about itself, for a reader inspecting the call.

    The provider's own metadata keys stay at the top level — a reader looking
    for ``model_name`` or ``mocked_source`` finds them where the provider put
    them, instead of under a nesting this layer invented.
    """
    report = dict(metadata)
    report["content"] = answer.content
    report["tool_calls"] = list(answer.tool_calls or [])
    usage = answer.usage_metadata
    report["usage"] = dict(usage) if usage else None
    return report


__all__ = ["LlmCallStep", "StepReporter", "ToolCallStep"]
