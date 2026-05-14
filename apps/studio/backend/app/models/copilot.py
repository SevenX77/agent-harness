"""Studio Copilot API models."""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

CopilotBackend: TypeAlias = Literal["claude", "deepseek", "gemini", "openai"]
ProviderKind: TypeAlias = Literal["anthropic", "openai-compat", "google"]
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


class ProviderConfig(BaseModel):
    """One configured Copilot provider."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    name: str
    kind: ProviderKind
    api_key: str = ""
    base_url: str = ""
    active_model_id: str | None = None


class CopilotCredentials(BaseModel):
    """Credential file schema stored at ``~/.studio/copilot.json``."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    active_provider_id: str
    providers: list[ProviderConfig]


BackendStatus = ProviderConfig
CredentialsReadResponse = CopilotCredentials
CredentialsWriteRequest = CopilotCredentials
TestCredentialsRequest = ProviderConfig
TestCredentialsResponse = CopilotCredentials


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
