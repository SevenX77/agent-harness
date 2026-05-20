# multi-file-editor (studio feature) — MVP0 Alignment (下一步对齐 MVP0 的改造逻辑)

> **Status**: Filled by a1 (Codex), 2026-05-20
> **Scope**: 焦点联动 (split-editor)、VSCode 风格侧边文件树、代码编辑器核心
> **配套**: 见 [INDEX.md](../../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

MVP0 WILL make the editor the PM-friendly way to edit a V2.1 skill directory.
Current SplitEditor, file tree, save, and conflict behavior are in [baseline.md](./baseline.md).

First term: V2.1 skill directory means a folder with `GRAPH.md`, `io/inputs.json`, `io/outputs.json`, and `phases/<id>/{LOGIC,SUBGRAPH,SKILL}.md`.
The spec states that physical structure in `.kiro/specs/studio-frontend-v21-multifile-editor/requirements.md:9` to `.kiro/specs/studio-frontend-v21-multifile-editor/requirements.md:10`.

MVP0 SHOULD render a V2.1-aware file tree instead of a generic folder tree.
Generic tree still exists, but the PM view should group files as:
`Graph`, `Inputs/Outputs`, `Phases`, `References`, and `Artifacts`.
Current AssetsPanel builds a folder/file tree from `skillDetail.files`, see `apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:33` to `apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:62`.

MVP0 SHOULD implement Split Editor focus.
Active focus side means the pane that receives the next file open.
The split focus spec defines `activeFocusSide`, see `.kiro/specs/split-editor-focus-enhancement/requirements.md:17` to `.kiro/specs/split-editor-focus-enhancement/requirements.md:24`.
Current behavior defaults to right pane when split is open, see `apps/studio/frontend/src/components/studio/Workspace.tsx:113` to `apps/studio/frontend/src/components/studio/Workspace.tsx:114`.

MVP0 SHOULD make frontmatter editable as a form.
Frontmatter means the YAML-like metadata block at the top of a phase markdown file.
PMs should edit `phase id`, `llm_role`, `depends_on`, and IO fields through controls, while Monaco still shows raw file content for advanced edits.

MVP0 SHOULD support nested subgraph navigation.
Double-clicking a SUBGRAPH node should open the child skill or switch file tree root into the subgraph folder.
Canvas double-click already opens files, see `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:198` to `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:210`.

MVP0 SHOULD show save and compile status together.
The PM should see "saved, compiling, compile failed at GRAPH.md line 17" without hunting in another panel.
Current LazyMonacoPanel already tracks draft/saved/in-flight state in `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:65` to `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:76`.

## 前端逻辑

MVP0 WILL add an explicit workspace file model above current open-file panes.
Current `WorkspaceContextValue` exposes split/open/close/save/conflict callbacks, see `apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:22` to `apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:44`.
MVP0 SHOULD add file tree selection, active focus side, auto-compile state, and V2.1 file role metadata.

```typescript
export type EditorSide = "left" | "right";

export type V21FileRole =
  | "graph"
  | "io_inputs"
  | "io_outputs"
  | "phase_logic"
  | "phase_subgraph"
  | "phase_skill"
  | "reference"
  | "artifact"
  | "unknown";

export interface V21WorkspaceFile {
  path: string;
  role: V21FileRole;
  phaseId?: string;
  language: "markdown" | "json" | "python" | "text";
  content: string;
  savedHash?: string;
  dirty: boolean;
  inFlight: boolean;
}

export interface EditorFocusState {
  splitMode: boolean;
  activeFocusSide: EditorSide;
  openFiles: Partial<Record<EditorSide, V21WorkspaceFile>>;
}
```

MVP0 SHOULD make `openFile(path)` target `activeFocusSide`.
Clicking inside a pane sets focus to that pane.
Closing the active pane moves focus to the remaining pane, as required by `.kiro/specs/split-editor-focus-enhancement/requirements.md:31` to `.kiro/specs/split-editor-focus-enhancement/requirements.md:40`.

MVP0 SHOULD preserve debounce save and flush-on-unmount.
Current debounce save is in `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:163` to `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:179`.
Current flush-on-switch/unmount is in `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:146` to `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:161`.

MVP0 SHOULD run auto-compile after a successful save.
Current Workspace compile logic is in `apps/studio/frontend/src/components/studio/Workspace.tsx:292` to `apps/studio/frontend/src/components/studio/Workspace.tsx:322`.
The editor should debounce compile separately from save so typing does not compile on every keystroke.

MVP0 SHOULD parse V2.1 file roles from path.
Current language detection is suffix-based in `apps/studio/frontend/src/components/studio/panels/panel-files.ts:5` to `apps/studio/frontend/src/components/studio/panels/panel-files.ts:9`.
MVP0 SHOULD add role detection rules for `GRAPH.md`, `io/*.json`, and `phases/*/*.md`.

## 后端功能

MVP0 SHOULD continue using backend file APIs for reads/writes.
The write client uses `writeSkillFile(skillId, filePath, draft, savedHash)`, see `apps/studio/frontend/src/api/client.ts:162` to `apps/studio/frontend/src/api/client.ts:173`.
The backend skill detail endpoint supplies files, see `apps/studio/backend/app/routers/skills.py:98` to `apps/studio/backend/app/routers/skills.py:105`.

MVP0 SHOULD enforce V2.1 file placement.
The editor spec says only valid V2.1 locations are allowed, see `.kiro/specs/studio-frontend-v21-multifile-editor/requirements.md:34` to `.kiro/specs/studio-frontend-v21-multifile-editor/requirements.md:38`.
The editor should not create a phase file in the wrong directory and then rely on compile to catch it later.

MVP0 SHOULD integrate with workspace file system watcher.
External edits need to notify the editor and trigger conflict handling.
System-level watcher planning is in [workspace-file-system mvp0](../../system-level/workspace-file-system/mvp0-alignment.md#cross-feature-interaction).

MVP0 SHOULD not bypass hash conflict protection.
Current save includes hash conflict behavior in `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:97` to `apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:144`.
Copilot and Canvas file changes must use the same conflict semantics.

MVP0 SHOULD let backend return file roles with SkillDetail.
Frontend can infer roles, but backend already knows skill structure after compile.
Returning roles avoids duplicated parsing logic in Canvas, Editor, and Copilot.

## API

MVP0 SHOULD keep existing file save API and add a role-aware file tree response.

```typescript
export interface V21FileTreeNode {
  id: string;
  path: string;
  name: string;
  kind: "folder" | "file";
  role?: V21FileRole;
  phaseId?: string;
  children?: V21FileTreeNode[];
  hash?: string;
  hasCompileIssue?: boolean;
}

export interface SkillFilesResponse {
  skillId: string;
  rootPath: string;
  files: V21WorkspaceFile[];
  tree: V21FileTreeNode[];
  manifestHash: string;
}
```

Existing write API should be treated as:

```typescript
export interface WriteSkillFileRequest {
  path: string;
  content: string;
  expectedHash?: string;
}

export interface WriteSkillFileResponse {
  path: string;
  content: string;
  hash: string;
  compile?: {
    ok: boolean;
    issues: Array<{ message: string; filePath?: string; line?: number; phaseId?: string }>;
  };
}

export async function writeSkillFile(
  skillId: string,
  path: string,
  content: string,
  expectedHash?: string
): Promise<WriteSkillFileResponse>;
```

MVP0 SHOULD add a compile-after-save option.

```typescript
export interface SaveAndCompileRequest {
  file: WriteSkillFileRequest;
  compileAfterSave: true;
}
```

MVP0 SHOULD expose frontmatter parsing as a UI helper contract.

```typescript
export interface PhaseFrontmatterDraft {
  phaseId: string;
  phaseType: "logic" | "subgraph" | "skill";
  name?: string;
  dependsOn: string[];
  llmRole?: string;
  subSkillRef?: string;
  inputKeys?: string[];
  outputKeys?: string[];
}
```

## Data Model / State

MVP0 SHOULD keep draft state per file, not per pane.
A file can move from left pane to right pane without losing draft.
The current `OpenFile` contains `savedHash`, see `apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:4` to `apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:13`.

```typescript
export interface MultiFileEditorState {
  filesByPath: Record<string, V21WorkspaceFile>;
  focus: EditorFocusState;
  selectedTreePath?: string;
  compileState: {
    status: "idle" | "queued" | "running" | "success" | "failed";
    issuesByPath: Record<string, Array<{ message: string; line?: number; phaseId?: string }>>;
  };
  conflicts: Array<SaveConflict>;
}
```

MVP0 SHOULD make the file tree derived from `filesByPath`.
The tree should not be a separate mutable source of truth.
External file changes should update file records first, then tree projection.

MVP0 SHOULD keep conflict state compatible with current dialog.
Current `SaveConflict` has side/path/localContent/remoteContent/baseHash/errorMessage, see `apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:13` to `apps/studio/frontend/src/components/studio/WorkspaceContext.tsx:21`.
MVP0 should add `source: "editor" | "copilot" | "canvas" | "external"` so the PM knows what caused the conflict.

## Cross-feature interaction

### Editor V2.1 file tree owner {#cross-editor-v21-file-tree}

Multi-file editor owns the V2.1 file tree projection and open-file behavior.
Canvas uses this when double-clicking phase nodes, see [canvas-topology mvp0](../canvas-topology/mvp0-alignment.md#cross-canvas-graph-patch).
Skill lifecycle uses this when opening a newly created skill, see [skill-lifecycle mvp0](../skill-lifecycle/mvp0-alignment.md#cross-lifecycle-v21-create).

### Editor save compile owner {#cross-editor-save-compile}

Multi-file editor owns conflict-aware save and auto-compile.
Copilot applies approved diffs through this owner path, see [copilot-assistance mvp0](../copilot-assistance/mvp0-alignment.md#cross-copilot-patch-apply).
Trace displays compile issues produced by this flow, see [trace-visualization mvp0](../trace-visualization/mvp0-alignment.md#cross-trace-compile-issues).

### Editor Copilot drafts {#cross-editor-copilot-drafts}

Editor owns dirty draft content.
Copilot can include dirty file context only through this state, see [copilot-assistance mvp0](../copilot-assistance/mvp0-alignment.md#cross-copilot-mentions).

### Editor subgraph navigation {#cross-editor-subgraph-nav}

Editor owns file navigation into SUBGRAPH sources.
Canvas owns subgraph node selection.
Engine owns subgraph runtime isolation in [state-and-io-contract mvp0](../../../engine/state-and-io-contract/mvp0-alignment.md#cross-state-blackboard-isolation).
