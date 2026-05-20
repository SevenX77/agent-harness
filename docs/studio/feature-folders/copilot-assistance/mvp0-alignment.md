# copilot-assistance (studio feature) — MVP0 Alignment (下一步对齐 MVP0 的改造逻辑)

> **Status**: Filled by a1 (Codex), 2026-05-20
> **Scope**: 侧边栏对话驱动、智能 diff 气泡、代码补全、@mentions
> **配套**: 见 [INDEX.md](../../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

MVP0 WILL make Copilot the PM-facing way to ask for V2.1 skill edits without opening a terminal.
The current UI and payload gaps are in [baseline.md](./baseline.md).
This document only describes the forward-looking contract.

First term: `@mention` means a visible token in the chat input that points to a real Studio entity.
Examples are `@file:phases/extract/SKILL.md`, `@phase:extract`, `@edge:extract->summarize`, and `@trace:error-17`.
The existing input hint says "Use '@' to mention nodes, files, or trace events", see `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:195`, but MVP0 WILL make it real.

High-002 WILL be closed by adding an explicit mentions payload.
Current send payload only includes `user_message` and optional `model_override`, see `apps/studio/frontend/src/hooks/useCopilot.ts:143` to `apps/studio/frontend/src/hooks/useCopilot.ts:157`.
Current backend request model also only has `user_message` and `model_override`, see `apps/studio/backend/app/models/copilot.py:21` to `apps/studio/backend/app/models/copilot.py:28`.
MVP0 SHOULD reject any Copilot implementation that relies only on hidden prompt magic.

The chat input SHOULD support three ways to add context.
Clicking a Canvas node SHOULD offer `@phase`.
Clicking a Canvas edge / Context Inspector SHOULD offer `@edge_context`.
Clicking a file in the editor SHOULD offer `@file`.
The spec requires automatic mention for edge context in `.kiro/specs/copilot-context-design/requirements.md:30` to `.kiro/specs/copilot-context-design/requirements.md:38`.

MVP0 SHOULD keep the current streaming bubble behavior but improve token-level visibility.
The current hook batches text deltas every 75ms in `apps/studio/frontend/src/hooks/useCopilot.ts:50` to `apps/studio/frontend/src/hooks/useCopilot.ts:70`.
MVP0 SHOULD keep batching for performance while exposing a typing cursor and partial tool-call state.

MVP0 SHOULD make diff bubbles actionable.
Tool result bubbles already exist through `ToolCallBubble` and `ToolResultBubble`, see `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:29` to `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:37`.
In MVP0, Edit/Write results SHOULD show Apply, Open File, Reject, and Ask Follow-up.
Apply MUST write through the editor/workspace save contract, not silently mutate files behind the editor.

MVP0 SHOULD show the active model/role clearly.
Copilot already loads roles and credentials in `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:83` to `apps/studio/frontend/src/components/copilot/copilot-panel.tsx:100`.
When model resolution fails, the message SHOULD point the PM to LLM Provider Config instead of showing raw SDK errors.

## 前端逻辑

MVP0 WILL split Copilot frontend state into chat, mentions, context, and patch application.
Current `useCopilot` owns messages/status/socket/text queue, see `apps/studio/frontend/src/hooks/useCopilot.ts:25` to `apps/studio/frontend/src/hooks/useCopilot.ts:33`.
MVP0 SHOULD keep that hook but add a mention-aware request builder.

The input composer SHOULD parse mention tokens before send.
It SHOULD not send raw display text like `@extract`.
It SHOULD send structured IDs so the backend can resolve files and trace data safely.

```typescript
export type CopilotMentionType =
  | "file"
  | "phase"
  | "edge_context"
  | "trace_event"
  | "compile_error";

export interface CopilotMention {
  type: CopilotMentionType;
  id: string;
  label: string;
  filePath?: string;
  phaseId?: string;
  runId?: string;
  edge?: {
    sourcePhaseId: string;
    targetPhaseId: string;
  };
}

export interface CopilotImplicitContext {
  view: "canvas" | "editor" | "trace" | "settings" | "welcome";
  selectedNodeId?: string;
  selectedEdgeId?: string;
  activeFilePath?: string;
  activeRunId?: string;
  activeTraceEventId?: string;
  dirtyFiles?: Array<{ path: string; content: string; hash?: string }>;
}

export interface CopilotChatRequest {
  user_message: string;
  model_override?: string;
  mentions: CopilotMention[];
  implicit_context: CopilotImplicitContext;
}
```

The existing `useCopilotContext` SHOULD remain the low-frequency view snapshot channel.
It currently POSTs `view/context/timestamp`, see `apps/studio/frontend/src/hooks/useCopilotContext.ts:39` to `apps/studio/frontend/src/hooks/useCopilotContext.ts:62`.
Mentions are different: they are user-intent references for one message.

MVP0 SHOULD add a mention picker.
A lightweight text-area wrapper is enough; the spec recommends `react-mentions` style behavior instead of heavy rich text, see `.kiro/specs/copilot-context-design/research.md:68` to `.kiro/specs/copilot-context-design/research.md:72`.
The picker SHOULD query current workspace state first, then fallback to backend search if needed.

MVP0 SHOULD connect diff apply to the multi-file editor.
If the assistant edits a file that is currently open and dirty, the UI SHOULD show a three-way choice: apply to draft, open compare, or reject.
The editor already has conflict state through `SaveConflict`, see `apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:13` to `apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:21`.

MVP0 SHOULD normalize tool events into user-readable steps.
Backend event types already include `text_delta`, `tool_use_start`, `tool_use_result`, `error`, and `done`, see `apps/studio/backend/app/models/copilot.py:30` to `apps/studio/backend/app/models/copilot.py:70`.
Frontend normalization exists in `apps/studio/frontend/src/types/copilot.ts:14` to `apps/studio/frontend/src/types/copilot.ts:109`.
MVP0 SHOULD add a `patch_proposed` event for diff bubbles.

## 后端功能

MVP0 WILL upgrade Copilot backend from "view context string injection" to "structured context resolver".
The current service stores view context in memory, see `apps/studio/backend/app/services/copilot.py:117` to `apps/studio/backend/app/services/copilot.py:140`.
It then injects the JSON into a system prompt, see `apps/studio/backend/app/services/copilot.py:165` to `apps/studio/backend/app/services/copilot.py:180`.
MVP0 SHOULD keep that layer but add mention resolution before query.

Mention resolution means the backend expands each mention into trusted context.
For `file`, read the current file content or use dirty file content supplied by frontend.
For `phase`, resolve the V2.1 phase AST and source file.
For `edge_context`, fetch trace edge input/output from trace storage.
For `compile_error`, include structured issue data and file line.

The backend SHOULD continue using Claude Agent SDK.
The current service configures allowed tools Read/Write/Edit/Bash in `apps/studio/backend/app/services/copilot.py:51` to `apps/studio/backend/app/services/copilot.py:54`.
The SDK session setup and working directory are in `apps/studio/backend/app/services/copilot.py:64` to `apps/studio/backend/app/services/copilot.py:114`.
MVP0 SHOULD add safer tool policy around Write/Edit so the frontend sees proposed diffs before final application when possible.

The backend SHOULD manage sessions by skill id and workspace root.
Current query path resolves provider each time, see `apps/studio/backend/app/services/copilot.py:183` to `apps/studio/backend/app/services/copilot.py:223`.
MVP0 SHOULD preserve per-skill continuity while allowing "new chat" to reset episodic memory.
Episodic memory means previous conversation turns, not permanent project knowledge.

The backend SHOULD resolve model through LLM roles.
Current fallback is `copilot_chat` role or model override, see `apps/studio/backend/app/services/copilot.py:372` to `apps/studio/backend/app/services/copilot.py:381`.
MVP0 should surface missing keys as actionable Studio errors, not only a raw `error` event.

## API

MVP0 WILL extend the WebSocket request payload.
The endpoint remains `WS /api/skills/{skill_id}/copilot/ws`, currently routed in `apps/studio/backend/app/routers/copilot.py:34` to `apps/studio/backend/app/routers/copilot.py:55`.

```typescript
export interface CopilotWsClientMessage {
  user_message: string;
  model_override?: string;
  mentions: CopilotMention[];
  implicit_context: CopilotImplicitContext;
  request_id: string;
}

export type CopilotWsServerEvent =
  | { type: "text_delta"; request_id: string; delta: string }
  | { type: "tool_use_start"; request_id: string; id: string; name: string; input?: unknown }
  | { type: "tool_use_result"; request_id: string; id: string; content?: unknown; is_error?: boolean }
  | { type: "patch_proposed"; request_id: string; patch: CopilotPatchProposal }
  | { type: "context_resolved"; request_id: string; resolved: ResolvedCopilotContextSummary }
  | { type: "error"; request_id: string; message: string; code?: string }
  | { type: "done"; request_id: string };
```

Backend Pydantic target:

```python
class CopilotMentionModel(BaseModel):
    type: Literal["file", "phase", "edge_context", "trace_event", "compile_error"]
    id: str
    label: str
    file_path: str | None = None
    phase_id: str | None = None
    run_id: str | None = None
    source_phase_id: str | None = None
    target_phase_id: str | None = None

class CopilotWsRequestPayload(BaseModel):
    user_message: str
    model_override: str | None = None
    mentions: list[CopilotMentionModel] = Field(default_factory=list)
    implicit_context: dict[str, Any] = Field(default_factory=dict)
    request_id: str
```

MVP0 SHOULD add an apply-patch endpoint for user-approved edits.
This keeps "assistant proposed a diff" separate from "workspace files changed".

```typescript
export interface CopilotPatchProposal {
  proposalId: string;
  files: Array<{
    path: string;
    beforeHash?: string;
    beforeText: string;
    afterText: string;
    summary: string;
  }>;
}

export interface ApplyCopilotPatchRequest {
  proposalId: string;
  files: Array<{ path: string; afterText: string; expectedHash?: string }>;
  compileAfterApply: boolean;
}

export interface ApplyCopilotPatchResponse {
  applied: Array<{ path: string; hash: string }>;
  conflicts: Array<{ path: string; reason: string; currentHash?: string }>;
  compile?: { ok: boolean; issues: Array<{ message: string; filePath?: string; line?: number }> };
}
```

## Data Model / State

MVP0 SHOULD distinguish four state layers.
Chat state is messages/events.
Mention state is structured references in the current input.
Context state is current view snapshot.
Patch state is pending diffs awaiting user approval.

```typescript
export interface CopilotPanelState {
  messages: CopilotMessage[];
  connection: "connecting" | "open" | "closed" | "error";
  currentInput: string;
  mentions: CopilotMention[];
  implicitContext: CopilotImplicitContext;
  pendingPatchById: Record<string, CopilotPatchProposal>;
  applyingPatchId?: string;
}
```

MVP0 SHOULD preserve `CopilotMessage` compatibility.
Current model has `id/role/content/events/status`, see `apps/studio/frontend/src/types/copilot.ts:54` to `apps/studio/frontend/src/types/copilot.ts:61`.
New event types should extend `events`, not replace message storage.

MVP0 SHOULD not persist API keys or raw secrets in Copilot context.
Provider configuration is owned by LLM Provider Config.
Copilot can mention model role names but should never include API key content in prompts.

MVP0 SHOULD treat dirty editor buffers as explicit context.
If a file is dirty, the backend file read is stale.
The frontend SHOULD include dirty file content only for mentioned files or active files, not every open buffer.

## Cross-feature interaction

### Copilot mentions owner {#cross-copilot-mentions}

Copilot owns the mention payload schema and prompt assembly.
Canvas supplies selected node/edge IDs through [canvas-topology mvp0](../canvas-topology/mvp0-alignment.md#cross-canvas-copilot-context).
Trace supplies trace event and edge context IDs through [trace-visualization mvp0](../trace-visualization/mvp0-alignment.md#cross-trace-edge-inspection).
Editor supplies active file and dirty draft state through [multi-file-editor mvp0](../multi-file-editor/mvp0-alignment.md#cross-editor-copilot-drafts).

### Copilot patch apply {#cross-copilot-patch-apply}

Copilot owns patch proposal UI.
Multi-file editor owns conflict-aware application of file changes.
The editor contract is [multi-file-editor mvp0](../multi-file-editor/mvp0-alignment.md#cross-editor-save-compile).

### Copilot provider resolution {#cross-copilot-provider-role}

Copilot uses the `copilot_chat` role by default.
Provider and role setup is owned by [llm-provider-config mvp0](../llm-provider-config/mvp0-alignment.md#cross-llm-role-resolution).
Engine runtime model resolution is specified in [execution-runtime mvp0](../../../engine/execution-runtime/mvp0-alignment.md#1-modelresolver-接口声明).

### Copilot lifecycle scaffolding {#cross-copilot-lifecycle-help}

Skill lifecycle may open Copilot with a guided prompt after creating a V2.1 skill.
Lifecycle owns creation; Copilot owns conversational edits after creation.
See [skill-lifecycle mvp0](../skill-lifecycle/mvp0-alignment.md#cross-lifecycle-v21-create).
