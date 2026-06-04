# Requirement Specification - Studio Copilot Chat Redesign

## 1. Background & Core Pain Points

The current Studio Copilot Panel acts merely as a visual placeholder rather than an intelligent, context-aware agent assistant:
* **Empty "@" Mention Shell**: The textarea placeholder advertises using `@` to mention nodes, files, or trace events, but it is a plain `<textarea>` with zero keyboard interception or dropdown menu functionality.
* **Payload Gaps**: The WebSocket payload only transmits `{ user_message, model_override }`. The backend has no structured knowledge of what files, phases, or trace elements the user is referring to.
* **Out-of-Sync View Snapshots**: Low-frequency HTTP POST syncs (`useCopilotContext`) upload general view summaries but fail to pair the user's immediate message with the active editor dirty buffer or active canvas selections.
* **Destructive Tool Writes**: When the assistant invokes `Write` or `Edit` tools, it mutates files directly on the workspace disk behind the user's back. This risks overwriting active editor dirty buffers and causing silent code loss or editing conflicts.
* **Brittle LLM Error Reporting**: Missing API keys or network timeout issues surface as raw python traceback exception strings, frustrating PMs and offering no actionable recovery path.

---

## 2. Functional Requirements

### 2.1 Mention Picker & Auto-Mention Keyboard Interception (`MentionMenu`)
* **REQ-1**: Implement a **Mention Autocomplete Picker**:
  * Intercept the `@` keystroke inside the Copilot input area.
  * Render a floating popover list (`MentionMenu`) styled using shadcn/ui design tokens.
  * The menu lists categorizable references available in the active Skill:
    * **Files**: Workspace file path structure (e.g. `phases/extract/SKILL.md`).
    * **Phases**: Studio canvas nodes (e.g. `agent_planner`).
    * **Edge Contexts**: Connection data flows (e.g. `extract->summarize`).
    * **Errors**: Active compilation or compilation/lint issues (e.g. `compile_error_12`).
  * Support keyboard navigation (Arrow Up/Down, Enter to confirm, Escape to cancel) and high-speed fuzzy filtering (<50ms delay).
* **REQ-2**: Implement **Auto-Mention Canvas Interactions**:
  * Clicking a node on the Graph Canvas automatically appends `@phase:<phase_id>` to the composer.
  * Clicking a connection line edge dot to open Context Inspector automatically appends `@edge_context:<source_id>-><target_id>`.
  * Selecting a file in the workspace file list or editor automatically exposes a capsule picker to mention it.
* **REQ-3**: Implement **UI Pill Tokenization**:
  * Selected mentions must be rendered inside the input field as non-editable **UI Pill Capsules** with distinct colors per entity type and inline close buttons.

---

### 2.2 Schema-Driven Implicit Context Assembly
* **REQ-4**: Implement **Structured Implicit Context Transmission**:
  * Attach an `implicit_context` block to the WebSocket chat send request payload:
    * Active view identifier.
    * Selected node/edge IDs.
    * Active file paths.
    * **Dirty Editor Buffer Sync**: Include current memory-dirty file buffers only for mentioned or active files to ensure the LLM reviews draft edits instead of stale disk contents.
* **REQ-5**: Implement **Backend Context Resolver**:
  * The backend must resolve structured IDs sent in `mentions` and `implicit_context` prior to querying the model.
  * Expand `file` references to full text (preferring frontend's dirty buffers).
  * Expand `phase` nodes by parsing their AST parameters (mode, tools, prompt, exit contracts) and source code.
  * Expand `edge_context` to serialized JSON inputs/outputs retrieved from trace database.
  * Progressive Prompt Assembly: Segment resolved details into explicit XML tags (e.g. `<referenced_file path="...">`) appended to the system instructions.

---

### 2.3 Safe Patch Proposal & Actionable Diff Application
* **REQ-6**: Implement **Safer Tool Policies (Patch Proposals)**:
  * Restrict `Write` and `Edit` tools from writing directly to disk while the session is active.
  * Instead, translate tool actions into a `patch_proposed` server-to-client WebSocket event containing a structured diff (`proposalId`, `beforeText`, `afterText`, `summary`).
* **REQ-7**: Implement **Actionable Diff Bubbles**:
  * Render proposed diffs as interactive widgets featuring `Apply` (Write to workspace), `Reject` (Dismiss), and `Open Compare` (Side-by-side Monaco diff panel) buttons.
* **REQ-8**: Implement **Conflict-Aware Patch Application**:
  * Clicking `Apply` calls `POST /api/skills/{skill_id}/copilot/apply-patch`.
  * The backend validates hashes against the current workspace files, performs safe writes, and automatically executes an incremental compile, returning a detailed compile response (status, issue lines, and messages) back to the UI.

---

## 3. UX & Workspace Interaction Details

### 3.1 Model/Role Resolution Guidance
* **REQ-9**: Clear Model/Role status representation. Surface current active fallback model routing information clearly on the panel header.
* **REQ-10**: In the event of model failure (such as missing credentials or network errors), display a clean visual card providing a direct link to the `LLM Provider settings` page instead of a raw stack trace.

---

### 3.2 Performance and Round-Trip Latency
* **REQ-11**: The frontend streaming text queue must continue buffering token chunks and flushing updates every 75ms to optimize DOM pressure while maintaining an active blinking cursor animation.
* **REQ-12**: All UI styling must adhere strictly to the Radix theme tokens (deep indigo-violet primary, zinc-950 background) and respect the 0.375rem rounded boundary defined in `FRONTEND_UI_SPEC.md`.
