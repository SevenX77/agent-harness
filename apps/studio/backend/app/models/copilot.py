"""Studio Copilot V1 API models."""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypeAlias

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

CopilotBackend: TypeAlias = Literal["claude", "deepseek", "gemini", "openai"]
CopilotToolName: TypeAlias = Literal["Read", "Write", "Edit", "Bash"]
CopilotView: TypeAlias = Literal[
    "WelcomeScreen",
    "Edit",
    "Compile",
    "Validate",
    "Predict",
    "Run",
    "Publish",
]


class BackendStatus(BaseModel):
    """Sanitized credential state for a backend."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    has_key: bool
    v1_5_placeholder: bool = Field(
        False,
        validation_alias=AliasChoices("v1_5_placeholder", "V1_5_PLACEHOLDER"),
        serialization_alias="V1_5_PLACEHOLDER",
    )


class CredentialsReadResponse(BaseModel):
    """Sanitized credential response."""

    model_config = ConfigDict(extra="forbid")

    backends: dict[CopilotBackend, BackendStatus]
    active_backend: CopilotBackend


class CredentialsWriteRequest(BaseModel):
    """Credential write or active backend switch request."""

    model_config = ConfigDict(extra="forbid")

    backend: CopilotBackend
    api_key: str | None
    set_active: bool = False


class CopilotEventBase(BaseModel):
    """Base model for streamed Copilot WebSocket events."""

    model_config = ConfigDict(extra="forbid")


class CopilotEventText(CopilotEventBase):
    type: Literal["text_delta"] = "text_delta"
    content: str


class CopilotEventToolUseStart(CopilotEventBase):
    type: Literal["tool_use_start"] = "tool_use_start"
    tool_name: CopilotToolName
    tool_input: dict[str, Any]


class CopilotEventToolUseResult(CopilotEventBase):
    type: Literal["tool_use_result"] = "tool_use_result"
    tool_name: str
    success: bool
    result_summary: str


class CopilotEventDone(CopilotEventBase):
    type: Literal["done"] = "done"


class CopilotEventError(CopilotEventBase):
    type: Literal["error"] = "error"
    message: str


CopilotEvent: TypeAlias = Annotated[
    CopilotEventText
    | CopilotEventToolUseStart
    | CopilotEventToolUseResult
    | CopilotEventDone
    | CopilotEventError,
    Field(discriminator="type"),
]


class ContextUpdateRequest(BaseModel):
    """Update the cached Studio view context for Copilot."""

    model_config = ConfigDict(extra="forbid")

    view: CopilotView
    context: dict[str, Any]
    timestamp: int


class ContextUpdateResponse(BaseModel):
    """Response for a Studio view context update."""

    model_config = ConfigDict(extra="forbid")

    accepted: bool
    reason: Literal["out_of_order"] | None = None
    summary: str | None = None
