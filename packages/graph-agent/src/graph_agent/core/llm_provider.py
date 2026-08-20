from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any, Protocol, cast, runtime_checkable

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.base import LanguageModelInput
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from pydantic import BaseModel, ConfigDict, Field

from graph_agent.callbacks.emit import _GatewayEventSink
from graph_agent.tracing.steps import LlmCallStep, StepReporter


class LLMProviderRequest(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
    role: str
    messages: list[Any] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMProviderResponse(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
    content: Any
    metadata: dict[str, Any] = Field(default_factory=dict)
    # The thinking that produced the answer, whole. The slices of it are
    # droppable on the wire; this is the one copy that is not.
    reasoning: str = ""


class LLMProviderChunk(BaseModel):
    """One slice of an answer that is still arriving.

    ``content`` is this slice's text, not the text so far. ``metadata`` holds
    whatever the provider reported alongside it; a provider names the model,
    the tool calls and the token usage on whichever slice it knows them, and
    the assembler merges the slices in arrival order.

    ``reasoning`` is what the model said while working out the answer, on the
    slice it said it. It is a separate field rather than more ``content``
    because it is not part of the answer: a caller that folded it in would hand
    the agent loop a message the model never gave, and a reader would see the
    model talking to itself presented as its reply.

    ``restarts_answer`` says this slice begins the answer over: everything
    delivered before it belongs to an attempt that was abandoned and is no part
    of the answer. Hosts behind this Port retry — a larger budget after an
    answer was cut off, another route after one failed — and a retry replaces
    the answer rather than continuing it. Without a way to say so, folding the
    slices produces a message stitched from two attempts, which no model wrote.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
    content: Any = ""
    reasoning: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    restarts_answer: bool = False


class LLMProviderError(Exception):
    def __init__(self, error_code: str, message: str, retryable: bool, details: dict[str, Any]) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.retryable = retryable
        self.details = details


class LLMProviderMissingError(RuntimeError):
    error_code = "llm.provider_missing"
    retryable = False

    def __init__(self, phase_name: str) -> None:
        self.details = {"phase_name": phase_name}
        super().__init__(f"llm_provider is required for LLM phase '{phase_name}'")


@runtime_checkable
class LLMProvider(Protocol):
    def stream(self, request: LLMProviderRequest) -> Iterator[LLMProviderChunk]:
        """Yield the answer in arrival order.

        This is the only way to ask a provider for an answer. A blocking
        alternative would let a caller discard the fact that the answer is
        still arriving — which is the very capability the engine needs — so
        there is no blocking alternative. A client with nothing to reveal
        gradually satisfies this by yielding one slice.
        """
        ...


class LLMProviderChatModel(BaseChatModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    provider: LLMProvider
    role: str
    phase_name: str | None = None
    model_name: str | None = None
    # Engine trace callbacks ride their own field (same convention as
    # PredictGatewayChatModel.event_callbacks): LangChain's inherited
    # ``callbacks`` field is reserved for real LangChain handlers, and stuffing
    # engine objects into it crashes CallbackManager.configure on invoke.
    event_callbacks: tuple[Any, ...] = Field(default_factory=tuple)
    model_override: str | None = None
    bound_tools: tuple[Any, ...] = Field(default_factory=tuple)
    tool_choice: str | None = None
    tool_kwargs: dict[str, Any] = Field(default_factory=dict)
    # Run-scoped identity a parallel sub-run carries on everything it emits, and
    # the node a call belongs to. The phase that builds the model knows both;
    # the model is what emits.
    sub_run_id: str | None = None
    group_key: str | None = None
    parent_node_id: str | None = None
    node_type: str | None = None
    # What the phase's system prompt was made from, and what it was made with.
    # Constant for the phase, announced on every call: a reader looking at one
    # call should not have to find the phase that built the model to learn why
    # the prompt says what it says.
    prompt_template_source: str | None = None
    #: The un-substituted template text and the authored document's path — the
    #: other two halves of "why does this prompt say what it says". Constant for
    #: the phase, announced on every call for the same reason the source id is.
    prompt_template_text: str | None = None
    prompt_source_path: str | None = None
    prompt_variables: dict[str, Any] = Field(default_factory=dict)
    # Shared so a bound copy keeps counting where the original left off (the
    # agent loop binds tools once and then invokes the bound copy every turn,
    # and "call 1, call 1, call 1" is not a sequence anyone can read), but keyed
    # by INVOCATION so the count restarts for each batch item / loop round /
    # resume — the model instance outlives all of those.
    call_counts: dict[str, int] = Field(default_factory=dict)

    @property
    def _llm_type(self) -> str:
        return "graph_agent_llm_provider"

    @property
    def _identifying_params(self) -> dict[str, object]:
        return {
            "role": self.role,
            "phase_name": self.phase_name,
            "model_name": self.model_name,
        }

    def bind_tools(
        self,
        tools: Sequence[Any],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        return cast(
            Runnable[LanguageModelInput, AIMessage],
            self.model_copy(
                update={
                    "bound_tools": tuple(tools),
                    "tool_choice": tool_choice,
                    "tool_kwargs": dict(kwargs),
                }
            ),
        )

    def _request(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None,
        kwargs: dict[str, Any],
    ) -> LLMProviderRequest:
        metadata = {
            "phase_name": self.phase_name,
            "model_override": self.model_override,
            # Not the raw list: what the gateway emits has to come back through
            # the engine's own seam, or it arrives unable to say which subgraph
            # it ran in — the gateway has no idea graphs nest.
            "callbacks": (_GatewayEventSink(self.event_callbacks),),
            "stop": stop,
            "bound_tools": list(self.bound_tools),
            "tool_choice": self.tool_choice,
            "tool_kwargs": dict(self.tool_kwargs),
            **kwargs,
        }
        return LLMProviderRequest(
            role=self.role,
            messages=list(messages),
            metadata={key: value for key, value in metadata.items() if value is not None},
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del run_manager
        # Both halves of the report belong here, at the call, rather than in a
        # wrapper around some callers or a reader of the messages afterwards.
        # An AGENT phase hands this model to LangChain's agent loop, which
        # reaches `_generate` and never touches a wrapper's `invoke`; that path
        # is where the minutes are spent, so a wrapper is exactly the wrong
        # place to keep the signal that says "still working". And a phase that
        # reconstructed its calls from the finished message list could only
        # close them all at once, when the phase was already over — which is
        # what left five steps spinning on a finished run (measured 2026-08-09).
        # Imported here, not at module scope: `graph_agent.middleware.__init__`
        # reaches back into `core.runner`, so a top-level import closes a cycle.
        from graph_agent.middleware.invocation_scope import next_invocation_call_index

        with self._steps().llm_call(
            messages,
            llm_role=self.role,
            resolved_model=self.model_name,
            loop_index=next_invocation_call_index(self.call_counts),
            parent_node_id=self.parent_node_id,
            node_type=self.node_type,
            sub_run_id=self.sub_run_id,
            group_key=self.group_key,
            template_source=self.prompt_template_source,
            template_text=self.prompt_template_text,
            phase_source_path=self.prompt_source_path,
            variables=self.prompt_variables,
        ) as step:
            # The answer is consumed slice by slice even though the agent loop
            # is handed the finished message: the loop needs the whole answer to
            # decide its next move, while everything watching the run needs to
            # know the step is still running. Only the arrival is incremental.
            response = _assemble(
                _reported(self.provider.stream(self._request(messages, stop, kwargs)), step)
            )
            response_metadata = dict(response.metadata)
            tool_calls = response_metadata.pop("tool_calls", None) or []
            usage_metadata = response_metadata.pop("usage_metadata", None)
            resolved_model = response_metadata.get("model_name") or response_metadata.get("model")
            if resolved_model is not None and self.model_name != str(resolved_model):
                object.__setattr__(self, "model_name", str(resolved_model))
            message = AIMessage(
                content=response.content,
                tool_calls=tool_calls,
                response_metadata=response_metadata,
                usage_metadata=usage_metadata,
                # Same key the gateway puts on its own messages, so one reader
                # serves both an engine-driven and a caller-supplied model.
                additional_kwargs=(
                    {"reasoning_content": response.reasoning} if response.reasoning else {}
                ),
            )
            step.finished(message)
        return ChatResult(
            generations=[ChatGeneration(message=message)],
            llm_output=response_metadata,
        )

    def _steps(self) -> StepReporter:
        return StepReporter(callbacks=self.event_callbacks, phase_name=self.phase_name or "unknown")


def _reported(chunks: Iterator[LLMProviderChunk], step: LlmCallStep) -> Iterator[LLMProviderChunk]:
    """Pass the slices through, reporting each one as it goes by.

    A separate pass rather than a hook inside ``_assemble``: folding slices into
    an answer is a pure computation and stays one, while telling the run what
    just arrived is a side effect and stays outside it. Both walk the same
    iterator once, so nothing is buffered to do it.
    """
    for chunk in chunks:
        if chunk.restarts_answer:
            step.delta("", restarts_step=True)
        if chunk.reasoning:
            step.delta(chunk.reasoning, channel="thinking")
        if isinstance(chunk.content, str) and chunk.content:
            step.delta(chunk.content)
        yield chunk


def _assemble(chunks: Iterator[LLMProviderChunk]) -> LLMProviderResponse:
    """Fold the slices back into the one answer the agent loop is given.

    Text slices concatenate. A provider that reports structured content blocks
    instead of text keeps them as blocks — joining those into a string would
    destroy the structure the caller asked for. Metadata merges in arrival
    order, so a key the provider only knows at the end (usage, the model that
    actually served the call) wins over an earlier guess.
    """
    parts: list[Any] = []
    metadata: dict[str, Any] = {}
    thoughts: list[str] = []
    for chunk in chunks:
        if chunk.restarts_answer:
            # Not "prefer the newer value" — the abandoned attempt's own claims
            # (which route answered, why it stopped) describe an answer nobody
            # received, and keeping the ones the replacement does not happen to
            # overwrite would leave them describing this one. Its thinking goes
            # with it: it reasoned its way to an answer nobody received.
            parts.clear()
            metadata.clear()
            thoughts.clear()
        if chunk.content != "" and chunk.content is not None:
            parts.append(chunk.content)
        if chunk.reasoning:
            thoughts.append(chunk.reasoning)
        metadata.update(chunk.metadata)
    if all(isinstance(part, str) for part in parts):
        content: Any = "".join(parts)
    else:
        # A slice of block content is a list of blocks, so the slices nest one
        # level deeper than the answer does; flattening that level restores the
        # single block list a caller would have received in one piece.
        content = [
            block
            for part in parts
            for block in (part if isinstance(part, list) else [part])
        ]
    return LLMProviderResponse(content=content, metadata=metadata, reasoning="".join(thoughts))


class ChatModelProvider:
    """A chat model the caller brought, seen as what it actually is: a provider.

    ``run_skill(mock_llm=...)`` hands the engine a ready-made LangChain model.
    Driving it directly would mean a second kind of model inside the engine —
    one that cannot report its own calls, because the engine did not write it —
    and a run driven by it would go unobserved for that reason alone. Behind the
    Port it is just another way of answering, and every phase above keeps the
    one model, the one reporter and the one set of events.
    """

    def __init__(self, model: Any) -> None:
        self._model = model

    def stream(self, request: LLMProviderRequest) -> Iterator[LLMProviderChunk]:
        """A model invoked whole has nothing to reveal gradually: one slice."""
        model = self._model
        tools = request.metadata.get("bound_tools")
        if tools:
            kwargs = dict(request.metadata.get("tool_kwargs") or {})
            tool_choice = request.metadata.get("tool_choice")
            if tool_choice is not None:
                kwargs["tool_choice"] = tool_choice
            model = model.bind_tools(tools, **kwargs)
        # Only what was actually asked for is passed on. A caller's model is
        # written to whatever signature that caller needs, so handing it a
        # ``stop=None`` nobody requested is how an adapter breaks a model that
        # was working.
        stop = request.metadata.get("stop")
        answer = model.invoke(request.messages, **({"stop": stop} if stop else {}))
        metadata: dict[str, Any] = dict(getattr(answer, "response_metadata", None) or {})
        tool_calls = list(getattr(answer, "tool_calls", None) or [])
        if tool_calls:
            metadata["tool_calls"] = tool_calls
        usage = getattr(answer, "usage_metadata", None)
        if usage:
            metadata["usage_metadata"] = usage
        yield LLMProviderChunk(content=answer.content, metadata=metadata)


class FakeLLMProvider:
    def __init__(
        self,
        response: LLMProviderResponse | None = None,
        error: LLMProviderError | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.requests: list[LLMProviderRequest] = []

    def stream(self, request: LLMProviderRequest) -> Iterator[LLMProviderChunk]:
        """A canned answer has nothing to reveal gradually, so it is one slice."""
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        response = self.response or LLMProviderResponse(content="fake response", metadata={})
        yield LLMProviderChunk(content=response.content, metadata=response.metadata)
