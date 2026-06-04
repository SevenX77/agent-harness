# Research Specification - Studio Copilot Chat Redesign

## 1. Industry Benchmarks

### 1.1 Cursor: "@" Mention and Pill Mechanics
* **Workflow**: Typing `@` opens a popup for `Files`, `Folders`, `Code Blocks`, and `Docs`. Selecting a target wraps the entity into a visual Pill Capsule.
* **Payload Delivery**: Pill references are transformed into context tokens. The actual content of the referenced files is injected into `<context>` tags in the prompt envelope.
* **Key Takeaway**: Converting text to Pills prevents users from accidentally mutating path references and isolates search actions to dedicated scopes.

### 1.2 GitHub Copilot Chat (VS Code): Context Variables
* **Workflow**: Uses `#file`, `#selection` to reference editor states, and `@` to query specialized assistant roles.
* **Key Takeaway**: Reusing standard symbols (like `@` or `#`) matches muscle memory. Using `@` to trigger both roles and entity scopes in a unified popup is highly intuitive.

### 1.3 Progressive Disclosure prompting
* **Concept**: Large-context models function best when context is structured progressively.
* **Hierarchy**:
  * **Layer 1 (Static)**: Global instructions, skill schema boundaries.
  * **Layer 2 (Situational)**: Workspace state, selected node properties.
  * **Layer 3 (Explicit Mentions)**: Files/Phases explicitly referred to by the user.
  * **Layer 4 (Diagnostics)**: Active compilation and lint issue tracebacks.

---

## 2. Workspace Codebase Analysis

Our scan of the workspace reveals the following layout and API hook footprints:

### 2.1 Frontend Footprints
* **`copilot-panel.tsx:191-197`**: Uses a standard HTML `<textarea>` with simple `rows={1}` and a placeholder. Intercepting input events and rendering floating portals requires adapting this to a custom autocomplete component.
* **`useCopilot.ts:143-157`**:
  ```typescript
  const payload = { user_message: trimmed }
  socketRef.current.send(JSON.stringify(payload))
  ```
  This is a critical gap. The payload must be expanded to include structured `mentions` arrays and the `implicit_context` state.
* **`useCopilotContext.ts`**: POSTs low-frequency context update requests (`/skills/{skillId}/copilot/context`). This acts as an out-of-band background sync. It does not solve instant state validation for specific message runs.
* **`DiffBubble.tsx`**: Renders a static diff viewer but doesn't implement action triggers (Apply/Reject) or link back to save operations.

### 2.2 Backend Footprints
* **`app/routers/copilot.py:34-55`**: Captures WebSocket connections at `/api/skills/{skill_id}/copilot/ws` and validates tokens. Passes the message strings directly to the streaming service without resolving mentions.
* **`app/models/copilot.py:21-28`**: `CopilotWsRequestPayload` lacks fields for mentions and implicit workspace snapshots.
* **`app/services/copilot.py:183-199`**: The prompt assembly flow simply stringifies the last saved view context dictionary and appends it to the base template. It does not perform target file queries or parse graph node dependencies dynamically.

---

## 3. Proposed Payload Contract

### 3.1 Frontend-to-Backend WebSocket Contract

```typescript
export interface CopilotMention {
  type: "file" | "phase" | "edge_context" | "trace_event" | "compile_error";
  id: string;
  label: string;
  filePath?: string;
  phaseId?: string;
}

export interface CopilotImplicitContext {
  view: "canvas" | "editor" | "trace" | "settings" | "welcome";
  selectedNodeId?: string;
  selectedEdgeId?: string;
  activeFilePath?: string;
  activeRunId?: string;
  dirtyFiles?: Array<{ path: string; content: string }>;
}

export interface CopilotWsClientMessage {
  user_message: string;
  model_override?: string;
  mentions: CopilotMention[];
  implicit_context: CopilotImplicitContext;
  request_id: string;
}
```

### 3.2 Backend Pydantic Schemas

```python
class CopilotMentionModel(BaseModel):
    type: Literal["file", "phase", "edge_context", "trace_event", "compile_error"]
    id: str
    label: str
    file_path: str | None = None
    phase_id: str | None = None

class CopilotWsRequestPayload(BaseModel):
    user_message: str
    model_override: str | None = None
    mentions: list[CopilotMentionModel] = Field(default_factory=list)
    implicit_context: dict[str, Any] = Field(default_factory=dict)
    request_id: str
```

---

## 4. Key Architectural Trade-Offs

### 4.1 UI Input Wrapper: react-mentions vs. Tiptap
* **Tiptap (Rich Text)**: Extremely customizable, supports native nodes and custom HTML extensions.
  * *Trade-off*: Heavily increases bundle size, requires complex React portal logic for simple text field sizing, and introduces unnecessary input styling overhead.
* **react-mentions (Lightweight Wrapper)**: A compact package wrapping textareas that matches characters (like `@`) and displays standard popup lists.
  * *Decision*: **Adopt react-mentions (or a custom lightweight React portal wrapper)**. It preserves native layout stability, fits beautifully inside our compact sidebars, and satisfies the 50ms lookup latency requirement.

### 4.2 Dirty Buffers Synchronization Strategy
* **Option A**: Upload all open buffer states on every message.
  * *Trade-off*: Bloats WebSocket traffic, especially when working in large-scale repositories with hundreds of open lines.
* **Option B**: Fetch buffers on-demand from the backend through a separate request loop.
  * *Trade-off*: Increases round-trip latency and creates complex race conditions during streaming responses.
* **Option C (Recommended)**: Selective sync. Only transmit dirty data for files **explicitly mentioned** or **currently focused** by the editor.
  * *Decision*: **Implement Option C**. This guarantees the assistant accesses the latest draft changes while keeping payload weights minimal.

### 4.3 Safe Write (Diff Apply) vs. Silent Mutate
* **Silent Mutate (Current)**: Assistant writes directly to the disk via Claude SDK processes.
  * *Trade-off*: Risk of silent compile errors, buffer conflicts with open dirty editors, and lack of visual oversight.
* **Smart Patch (Propose-Apply)**: Assistant returns structured diffs. The UI highlights differences, and writes are completed only on explicit user approval.
  * *Decision*: **Smart Patch**. Restricting tool direct disk writes in the SDK agent session ensures complete user control over workspace integrity and keeps developers in a safe editing loop.
