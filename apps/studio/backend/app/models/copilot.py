"""Studio Copilot API models."""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

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
    # Absolute imported/local workspace root. When present, the backend validates
    # it against Studio's skill index and uses it as the Copilot SDK cwd.
    workspace_root: str | None = None
    # Structured Golden-owned judge facts prepared before sending a Copilot Judge
    # chat turn. These are prompt context, not opaque refs hidden in prose.
    judge_context: dict[str, Any] | None = None


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
    """F8: transcribes EVERY tool call the SDK reports, by its real name.

    Tool policy (what may run) is enforced at the SDK layer (allowed_tools /
    can_use_tool) — the transcript never editorializes, so `tool_name` is an
    open string, not the pre-allowed subset (the model legitimately runs
    read-only tools like Glob/Grep outside that list).
    """

    type: Literal["tool_use_start"] = "tool_use_start"
    # Open string: the SDK reports real tool names (incl. read-only tools and
    # studio MCP tools mcp__studio__<tool>); policy lives in SDK options.
    tool_name: str
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
    before_hash: str | None
    after_hash: str
    diff: str
    checkpoint_id: str


class CopilotEventToolApprovalRequired(CopilotEventBase):
    """A copilot tool call held for human-in-the-loop approval (挂起式).

    Bash 一律审批;Read/Glob/Grep 仅在目标越出 workspace + 挂载目录时审批。
    ``can_use_tool`` awaits the user's verdict — approving lets the CLI run the
    tool itself so its result reaches the model's context. ``detail`` is the
    Bash command text or the out-of-fence path being read.
    """

    type: Literal["tool_approval_required"] = "tool_approval_required"
    tool_use_id: str
    tool_name: str
    detail: str


class CopilotEventDone(CopilotEventBase):
    type: Literal["done"] = "done"


class CopilotEventError(CopilotEventBase):
    type: Literal["error"] = "error"
    message: str
    error_code: str | None = None
    error_payload: dict[str, Any] | None = None


CopilotEvent: TypeAlias = Annotated[
    CopilotEventContextResolved
    | CopilotEventThinking
    | CopilotEventText
    | CopilotEventToolUseStart
    | CopilotEventToolUseResult
    | CopilotEventPatchProposed
    | CopilotEventToolApprovalRequired
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


class CopilotToolApprovalRequest(BaseModel):
    """Approve or reject a held Copilot tool call."""

    model_config = ConfigDict(extra="forbid")

    tool_use_id: str
    approve: bool


class CopilotToolApprovalResponse(BaseModel):
    """Result of resolving a held Copilot tool call.

    ``resolved`` is False when the approval no longer exists (already resolved,
    timed out, or session reset). Execution happens in the CLI after approval,
    so there is no stdout/stderr here by design.
    """

    model_config = ConfigDict(extra="forbid")

    tool_use_id: str
    approved: bool
    resolved: bool
    message: str | None = None
