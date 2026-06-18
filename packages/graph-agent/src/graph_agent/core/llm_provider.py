from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, cast, runtime_checkable

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.base import LanguageModelInput
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from pydantic import BaseModel, ConfigDict, Field


class LLMProviderRequest(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
    role: str
    messages: list[Any] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMProviderResponse(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
    content: Any
    metadata: dict[str, Any] = Field(default_factory=dict)


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
    def invoke(self, request: LLMProviderRequest) -> LLMProviderResponse:
        ...


class LLMProviderChatModel(BaseChatModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    provider: LLMProvider
    role: str
    phase_name: str | None = None
    model_name: str | None = None
    callbacks: tuple[Any, ...] = Field(default_factory=tuple)
    model_override: str | None = None
    bound_tools: tuple[Any, ...] = Field(default_factory=tuple)
    tool_choice: str | None = None
    tool_kwargs: dict[str, Any] = Field(default_factory=dict)

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

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del run_manager
        metadata = {
            "phase_name": self.phase_name,
            "model_override": self.model_override,
            "callbacks": self.callbacks,
            "stop": stop,
            "bound_tools": list(self.bound_tools),
            "tool_choice": self.tool_choice,
            "tool_kwargs": dict(self.tool_kwargs),
            **kwargs,
        }
        response = self.provider.invoke(
            LLMProviderRequest(
                role=self.role,
                messages=list(messages),
                metadata={key: value for key, value in metadata.items() if value is not None},
            )
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
        )
        return ChatResult(
            generations=[ChatGeneration(message=message)],
            llm_output=response_metadata,
        )


class FakeLLMProvider:
    def __init__(
        self,
        response: LLMProviderResponse | None = None,
        error: LLMProviderError | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.requests: list[LLMProviderRequest] = []

    def invoke(self, request: LLMProviderRequest) -> LLMProviderResponse:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        if self.response is not None:
            return self.response
        return LLMProviderResponse(content="fake response", metadata={})
