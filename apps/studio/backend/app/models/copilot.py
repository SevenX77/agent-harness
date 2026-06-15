"""Studio Copilot API models."""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

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


class CopilotWsRequestPayload(BaseModel):
    """Incoming Copilot WebSocket request payload."""

    model_config = ConfigDict(extra="ignore")

    user_message: str
    model_override: str | None = None
    # The selected copilot role (one per `role_kind=="copilot"` role in settings,
    # each auto-matched to its model group). Defaults to copilot_chat.
    role: str | None = None


class CopilotEventBase(BaseModel):
    """Base model for streamed Copilot WebSocket events."""

    model_config = ConfigDict(extra="forbid")


class CopilotEventContextResolved(CopilotEventBase):
    """F4: echo, as the first streamed event, what context was injected this turn.

    Anti-hidden-prompt-magic (same spirit as F1 "不省略"): the UI shows a
    collapsible "injected context" card so the user can see exactly what the
    copilot was given before it starts.
    """

    type: Literal["context_resolved"] = "context_resolved"
    summary: str
    detail: str


class CopilotEventThinking(CopilotEventBase):
    """Streamed extended-thinking delta.

    F1 (copilot-assist mvp1-alignment): the whole reasoning trace is streamed —
    the UI may collapse it, but it must never be dropped. The frontend renders
    this as a collapsible "Thought" block.
    """

    type: Literal["thinking_delta"] = "thinking_delta"
    content: str


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


class CopilotEventPatchProposed(CopilotEventBase):
    """F5 safe-write (model B): a copilot Write/Edit applied to a workspace file.

    Emitted before the SDK applies the edit (apply-then-review), carrying the
    pre-edit bytes so the UI can show an inline diff and a Reject can restore the
    original bytes through the Rust sole writer. ``after_content`` is best-effort
    for instant rendering; the authoritative applied content is the file on disk.
    """

    type: Literal["patch_proposed"] = "patch_proposed"
    tool_use_id: str
    tool_name: Literal["Write", "Edit"]
    path: str
    before_existed: bool
    before_content: str
    after_content: str


class CopilotEventBashApprovalRequired(CopilotEventBase):
    """F5: a copilot Bash command gated for human-in-the-loop approval.

    The interactive approve/reject round-trip needs a bidirectional WS control
    channel (not yet wired), so the command is held — surfaced for visibility but
    not executed. ``blocked`` distinguishes "held pending approval" from a future
    "approved" state.
    """

    type: Literal["bash_approval_required"] = "bash_approval_required"
    tool_use_id: str
    command: str
    blocked: bool = True


class CopilotEventDone(CopilotEventBase):
    type: Literal["done"] = "done"


class CopilotEventError(CopilotEventBase):
    type: Literal["error"] = "error"
    message: str


CopilotEvent: TypeAlias = Annotated[
    CopilotEventContextResolved
    | CopilotEventThinking
    | CopilotEventText
    | CopilotEventToolUseStart
    | CopilotEventToolUseResult
    | CopilotEventPatchProposed
    | CopilotEventBashApprovalRequired
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
