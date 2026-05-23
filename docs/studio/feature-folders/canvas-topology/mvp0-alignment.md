# canvas-topology (studio feature) — MVP0 Alignment (下一步对齐 MVP0 的改造逻辑)

> **Status**: Filled by a1 (Codex), 2026-05-20
> **Scope**: React Flow 画布微观 / 宏观拓扑展现、节点连接、布局流
> **配套**: 见 [INDEX.md](../../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

MVP0 WILL make Canvas the primary way a PM edits a V2.1 skill without opening YAML or a terminal.
The current state is documented in [baseline.md](./baseline.md), so this file only describes the target delta.

First term: React Flow means the node-and-edge canvas library used by Studio.
Current Canvas already renders React Flow nodes and edges in `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:177` to `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:222`.
MVP0 SHOULD keep that foundation but make the graph editable, inspectable, and V2.1-type aware.

High-001 WILL be implemented in the canvas itself.
Animated gradient edges are the visual cue for "data moved through this edge".
Hover-hidden handles are the visual cue for "this node can be connected, but the port is not noise until needed".
Current `ContextEdge` only sets `strokeWidth`, see `apps/studio/frontend/src/components/edges/ContextEdge.tsx:35` to `apps/studio/frontend/src/components/edges/ContextEdge.tsx:37`.
Current handle rendering is always visible on skill nodes, see `apps/studio/frontend/src/components/nodes/SkillNode.tsx:74` and `apps/studio/frontend/src/components/nodes/SkillNode.tsx:124`.

MVP0 SHOULD render phase type as a first-class visual grammar.
LOGIC means deterministic code transform.
SUBGRAPH means fixed child graph delegation.
SKILL means LLM-driven agent phase.
The engine already has `LogicNodeAST`, `SubgraphNodeAST`, and `SkillNodeAST`, see `packages/graph-agent/src/graph_agent/core/manifest.py:69` to `packages/graph-agent/src/graph_agent/core/manifest.py:90`.
The UI SHOULD not flatten V2.1 phases into `mode: "logic"` as the current converter does in `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:20` to `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:29`.

MVP0 SHOULD support adding a new phase from the canvas.
The PM flow is: drag a phase type from a small toolbar, drop it between nodes, name it, then Studio writes the V2.1 files.
This is intentionally visual because the locked MVP0 goal says the PM does not write YAML.

MVP0 SHOULD support edge inspection from the edge midpoint button.
The button already exists visually in `apps/studio/frontend/src/components/edges/ContextEdge.tsx:39` to `apps/studio/frontend/src/components/edges/ContextEdge.tsx:60`.
In MVP0, clicking it WILL open Context Inspector instead of only calling `stopPropagation`.
Context Inspector means a read-only panel that shows the JSON payload passed from source phase output into target phase input.

MVP0 SHOULD keep MiniMap and fitView, but add a "dirty topology" indicator.
Dirty topology means the React Flow state differs from the saved `GRAPH.md`.
This matters because current `onConnect` only changes frontend state, see `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:135` to `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:151`.

MVP0 SHOULD show compile errors near affected nodes and edges.
Compile means the backend parses the skill directory and validates structure before run.
The compile endpoint is already present in `apps/studio/backend/app/routers/skills.py:108` to `apps/studio/backend/app/routers/skills.py:118`.
The UI SHOULD turn "missing dependency" into a red edge/node badge, not a generic toast.

## 前端逻辑

MVP0 WILL split Canvas frontend logic into three explicit layers.
Layer one is projection: `SkillDetail.manifest` becomes React Flow nodes and edges.
Layer two is editing: user operations become a pending `GraphPatch`.
Layer three is persistence: the patch is written back to V2.1 files and recompiled.

The projection layer SHOULD consume V2.1 phase type directly.
Current `SkillDetail` carries manifest/files/topology fields, see `apps/studio/frontend/src/api/types.ts:383` to `apps/studio/frontend/src/api/types.ts:403`.
Current node data already has `filePath`, `dependsOn`, `llmRole`, `tools`, `subagents`, and `subgraphPath`, see `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:162` to `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:184`.
MVP0 SHOULD preserve those fields and add `phaseType`, `ioSummary`, and `compileStatus`.

The editing layer SHOULD replace ad-hoc `phaseNodes` mutation with a typed reducer.
Current `buildEdges` computes dependencies from `dependsOn`, see `apps/studio/frontend/src/components/nodes/buildEdges.ts:23` to `apps/studio/frontend/src/components/nodes/buildEdges.ts:49`.
MVP0 reducer SHOULD emit operations like `add_phase`, `delete_phase`, `connect_phase`, `disconnect_phase`, `rename_phase`, and `move_phase`.
Move operations are UI-only unless layout positions are persisted later; dependency operations MUST persist.

The persistence layer SHOULD call the existing file write API for MVP0.
The client function exists in `apps/studio/frontend/src/api/client.ts:162` to `apps/studio/frontend/src/api/client.ts:173`.
MVP0 can write `GRAPH.md` through `writeSkillFile` first, then call compile.
This is deliberately smaller than introducing a full graph patch backend endpoint on day one.

MVP0 SHOULD still define a proposed patch API because the file-write fallback is too coarse for long-term correctness.
The proposed API below is the desired contract, even if MVP0 initially implements it through `writeSkillFile`.

```typescript
export type CanvasPhaseType = "logic" | "subgraph" | "skill";

export interface CanvasPhaseNode {
  id: string;
  name: string;
  phaseType: CanvasPhaseType;
  filePath: string;
  dependsOn: string[];
  llmRole?: string;
  subgraphPath?: string;
  status?: "idle" | "running" | "success" | "failed" | "compile_error";
}

export interface CanvasEdgeData {
  id: string;
  sourcePhaseId: string;
  targetPhaseId: string;
  hasTraceData: boolean;
  traceRunId?: string;
  contextPreview?: string;
}

export type GraphPatchOperation =
  | { type: "add_phase"; phase: CanvasPhaseNode; insertAfter?: string }
  | { type: "delete_phase"; phaseId: string }
  | { type: "connect_phase"; sourcePhaseId: string; targetPhaseId: string }
  | { type: "disconnect_phase"; sourcePhaseId: string; targetPhaseId: string }
  | { type: "rename_phase"; phaseId: string; nextName: string }
  | { type: "set_phase_type"; phaseId: string; phaseType: CanvasPhaseType };
```

`onConnect` SHOULD produce a `connect_phase` operation.
`onEdgesDelete` SHOULD produce `disconnect_phase`.
Dragging a phase from the toolbar SHOULD produce `add_phase`.
The reducer SHOULD keep undo/redo possible because graph editing mistakes are common.

MVP0 SHOULD route double-clicks by phase type.
LOGIC opens `LOGIC.md`.
SUBGRAPH opens `SUBGRAPH.md` or navigates into the child skill.
SKILL opens `SKILL.md`.
Current double-click opens a generic `phases/<id>/<id>.md`, see `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:198` to `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:210`.

MVP0 SHOULD keep cycle detection before persisting.
Current dagre layout already checks `graphlib.alg.isAcyclic`, see `apps/studio/frontend/src/lib/layout.ts:45` to `apps/studio/frontend/src/lib/layout.ts:47`.
The new reducer SHOULD run the same invariant before writing `GRAPH.md`.

## 后端功能

Canvas has no dedicated backend today, but MVP0 SHOULD create one small backend capability: safe graph mutation.
Safe means the backend validates that a Canvas edit still produces a compilable V2.1 graph before it is treated as saved.

MVP0 SHOULD reuse existing skill compile service.
`compile_skill_for_studio` already calls graph-agent compile with `cache=False`, see `apps/studio/backend/app/services/skills.py:294` to `apps/studio/backend/app/services/skills.py:311`.
The canvas save flow SHOULD write files, then compile, then return structured issues to the UI.

MVP0 SHOULD use engine compile dataflow work as the source of truth for edge validity.
The engine mvp0 defines phase-level IO schema and compile issues in [skill-compilation mvp0](../../../engine/skill-compilation/mvp0-alignment.md#api).
The canvas should not guess whether an edge is valid only from node id strings.

MVP0 SHOULD use engine state-and-io work as the source of truth for edge payload.
Phase-level IO isolation is specified in [state-and-io-contract mvp0](../../../engine/state-and-io-contract/mvp0-alignment.md#cross-state-blackboard-isolation).
That contract will let Canvas say "this edge carries `{clean_text}`" instead of only drawing a line.

MVP0 SHOULD write V2.1 physical files for newly added phases.
For LOGIC, create `phases/<id>/LOGIC.md`.
For SUBGRAPH, create `phases/<id>/SUBGRAPH.md`.
For SKILL, create `phases/<id>/SKILL.md`.
The V2.1 editor spec states this file structure in `.kiro/specs/studio-frontend-v21-multifile-editor/design.md:109` to `.kiro/specs/studio-frontend-v21-multifile-editor/design.md:115`.

MVP0 SHOULD not let Canvas silently create legacy `SKILL.md` single-file content.
The multi-file editor requirement says V2.1 physical structure is `GRAPH.md`, `io/*.json`, and `phases/*/{LOGIC,SUBGRAPH,SKILL}.md`, see `.kiro/specs/studio-frontend-v21-multifile-editor/requirements.md:9` to `.kiro/specs/studio-frontend-v21-multifile-editor/requirements.md:10`.

## API

MVP0 SHOULD support the existing file-write path and define the graph-patch path.
The file-write path uses `PUT /api/skills/{skill_id}/files/{path}` through the frontend client in `apps/studio/frontend/src/api/client.ts:162` to `apps/studio/frontend/src/api/client.ts:173`.
The graph-patch path SHOULD be added when backend mutation is ready.

```typescript
export interface ApplyGraphPatchRequest {
  skillId: string;
  baseManifestHash: string;
  operations: GraphPatchOperation[];
  compileAfterWrite: boolean;
}

export interface ApplyGraphPatchResponse {
  skillId: string;
  manifestHash: string;
  changedFiles: Array<{
    path: string;
    hash: string;
    change: "created" | "updated" | "deleted";
  }>;
  graph: {
    phases: CanvasPhaseNode[];
    edges: CanvasEdgeData[];
  };
  compile: {
    ok: boolean;
    issues: Array<{
      severity: "error" | "warning";
      code: string;
      message: string;
      filePath?: string;
      line?: number;
      phaseId?: string;
      edgeId?: string;
    }>;
  };
}

export async function applyGraphPatch(
  request: ApplyGraphPatchRequest
): Promise<ApplyGraphPatchResponse>;
```

Proposed REST signature:

```http
POST /api/skills/{skill_id}/graph/patch
Content-Type: application/json

ApplyGraphPatchRequest -> ApplyGraphPatchResponse
```

MVP0 SHOULD expose an edge-inspection fetch API through trace visualization, not Canvas ownership.
Canvas owns the click and selected edge.
Trace owns the historical input/output data.

```typescript
export interface InspectEdgeRequest {
  skillId: string;
  runId: string;
  sourcePhaseId: string;
  targetPhaseId: string;
}

export interface InspectEdgeResponse {
  edgeId: string;
  runId: string;
  sourcePhaseId: string;
  targetPhaseId: string;
  sourceOutput: Record<string, unknown>;
  targetInput: Record<string, unknown>;
  reducerDiff?: Record<string, unknown>;
  truncated: boolean;
}
```

## Data Model / State

MVP0 SHOULD separate saved graph state from draft graph state.
Saved state is the compiled V2.1 manifest.
Draft state is the local graph after user edits but before save/compile.
This avoids the current problem where `onConnect` changes only React state and then disappears after reload.

```typescript
export interface CanvasTopologyState {
  savedManifestHash: string;
  savedNodes: CanvasPhaseNode[];
  savedEdges: CanvasEdgeData[];
  draftNodes: CanvasPhaseNode[];
  draftEdges: CanvasEdgeData[];
  pendingOperations: GraphPatchOperation[];
  selected:
    | { type: "phase"; phaseId: string }
    | { type: "edge"; edgeId: string; sourcePhaseId: string; targetPhaseId: string }
    | null;
  dirty: boolean;
  compileIssuesByTarget: Record<string, string[]>;
}
```

MVP0 SHOULD fill `hasTraceData` from run trace.
The current field exists but is hard-coded false in `apps/studio/frontend/src/components/nodes/buildEdges.ts:8` to `apps/studio/frontend/src/components/nodes/buildEdges.ts:20`.
When a run completes, trace visualization SHOULD publish which phase-pair edges have snapshots.

MVP0 SHOULD store expanded subgraph UI state separately from graph file state.
Current Canvas already has `expandedSubgraphs`, see `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:59` to `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:61`.
That state is UI preference, not V2.1 manifest content.

MVP0 SHOULD keep layout positions ephemeral unless a dedicated layout file is introduced.
The MVP0 goal is visual edit/run/debug, not versioned layout authoring.
Persist dependencies and files first; persist layout later only if PM needs stable diagrams.

## Cross-feature interaction

### Canvas graph patch owner {#cross-canvas-graph-patch}

Canvas owns graph topology editing.
Multi-file editor owns text editing of files.
When Canvas creates or rewires a phase, it SHOULD update files through the same save/compile contract used by the editor, but the source of the action remains Canvas.
The editor-side file tree rendering is specified in [multi-file-editor mvp0](../multi-file-editor/mvp0-alignment.md#cross-editor-v21-file-tree).

### Cross trace edge inspection {#cross-canvas-edge-inspection}

Canvas owns the edge click and selected edge state.
Trace visualization owns the data payload shown in Context Inspector.
The Trace owner side is [trace-visualization mvp0](../trace-visualization/mvp0-alignment.md#cross-trace-edge-inspection).
Engine event data comes from [tracing-and-observability mvp0](../../../engine/tracing-and-observability/mvp0-alignment.md#api) and [state-and-io-contract mvp0](../../../engine/state-and-io-contract/mvp0-alignment.md#cross-state-blackboard-isolation).

### Cross copilot canvas mentions {#cross-canvas-copilot-context}

Canvas selection SHOULD become a Copilot mention candidate.
The actual mention payload schema is owned by [copilot-assistance mvp0](../copilot-assistance/mvp0-alignment.md#cross-copilot-mentions).
Canvas only provides selected phase/edge identity and a short label.

### Cross skill lifecycle canvas creation {#cross-canvas-phase-create}

Skill lifecycle owns templates and initial V2.1 skill creation.
Canvas owns in-workspace phase insertion after a skill exists.
The lifecycle flow links here when the wizard opens the new skill into the visual graph; see [skill-lifecycle mvp0](../skill-lifecycle/mvp0-alignment.md#cross-lifecycle-v21-create).
