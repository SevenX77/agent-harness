"""Studio Copilot API models."""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field


class CopilotWsRequestPayload(BaseModel):
    """Incoming Copilot WebSocket request payload."""

    model_config = ConfigDict(extra="ignore")

    user_message: str
    # 会话身份契约(COPILOT_ASSIST-5):消息属于哪个前端会话标签。后端以
    # (skill, session) 隔离 SDK 对话;没有归属的消息在边界拒绝,绝不落进
    # "当前恰好活跃的对话"。
    session_id: str = Field(min_length=1)
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


class CopilotEventToolApprovalTimedOut(CopilotEventBase):
    """A held tool call whose approval window expired before anyone answered.

    Carries ``tool_use_id`` because the point of the event is to name WHICH
    hold died. The timeout used to travel as a generic ``error``, which could
    say that something expired but not what — so the card it was about had no
    way to recognise itself and sat on "Waiting for approval." with live
    buttons, forever, while the task behind it had already been stopped
    (problem ledger CP7).

    The stop is not negotiable and not a denial: ``can_use_tool`` returns
    ``interrupt=True`` so the model halts, rather than handing it a refusal no
    human ever made and letting the turn run on (COPILOT_ASSIST-8).
    """

    type: Literal["tool_approval_timed_out"] = "tool_approval_timed_out"
    tool_use_id: str
    tool_name: str
    message: str


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
    | CopilotEventToolApprovalTimedOut
    | CopilotEventDone
    | CopilotEventError,
    Field(discriminator="type"),
]


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


class CopilotInterruptResponse(BaseModel):
    """Result of a copilot stop-button interrupt (R7-I).

    ``interrupted`` is False when there was no active turn to stop — the click
    landed after the turn already finished, which is a harmless no-op.
    """

    model_config = ConfigDict(extra="forbid")

    interrupted: bool


class CopilotSessionCloseRequest(BaseModel):
    """Close one frontend tab's backend SDK conversation (COPILOT_ASSIST-5)."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)


class CopilotSessionCloseResponse(BaseModel):
    """``closed`` counts dropped SDK clients — 0 when the tab never talked to
    the backend (a draft tab closed before its first message), which is a
    harmless no-op, not an error."""

    model_config = ConfigDict(extra="forbid")

    closed: int
