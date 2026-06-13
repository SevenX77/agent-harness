from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class LLMProviderRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    role: str
    messages: list[Any] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMProviderResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    content: Any
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMProviderError(Exception):
    def __init__(self, error_code: str, message: str, retryable: bool, details: dict[str, Any]) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.retryable = retryable
        self.details = details


@runtime_checkable
class LLMProvider(Protocol):
    def invoke(self, request: LLMProviderRequest) -> LLMProviderResponse:
        ...


class FakeLLMProvider:
    def __init__(
        self,
        response: LLMProviderResponse | None = None,
        error: LLMProviderError | None = None,
    ) -> None:
        self.response = response
        self.error = error

    def invoke(self, request: LLMProviderRequest) -> LLMProviderResponse:
        if self.error is not None:
            raise self.error
        if self.response is not None:
            return self.response
        return LLMProviderResponse(content="fake response", metadata={})
