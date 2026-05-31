# agent-cognitive-architecture (architecture) — MVP0 Alignment (下一步对齐 MVP0 的改造逻辑)

> **Status**: Filled by a1 (Codex), 2026-05-20
> **Scope**: baseline: 旧 GraphAgentHarness 单文件线性控制流; MVP0: V2.1 LangGraph DAG + LOGIC/SUBGRAPH/SKILL 三态心智模型
> **配套**: 见 [INDEX.md](../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

MVP0 WILL make Studio present one primary agent mental model: a V2.1 directed graph made of LOGIC, SUBGRAPH, and SKILL phases.
The current dual state is documented in [baseline.md](./baseline.md), so this file describes the forward target.

First term: mental model means the user-facing explanation of how work happens.
In MVP0, the PM should understand "data enters a graph, each phase transforms or reasons over it, trace shows every phase input/output".
The PM should not need to know the old `GraphAgentHarness` class exists.

First term: DAG means Directed Acyclic Graph.
It is a graph whose edges point forward and cannot loop back.
Canvas already renders nodes and edges through React Flow in `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:177` to `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:222`.
MVP0 SHOULD make that visual graph the canonical UI for skill structure.

MVP0 SHOULD visually distinguish the three phase kinds.
LOGIC means deterministic code.
SUBGRAPH means a fixed child graph call.
SKILL means an LLM-driven agent phase.
The engine already names these AST types in `packages/graph-agent/src/graph_agent/core/manifest.py:69` to `packages/graph-agent/src/graph_agent/core/manifest.py:90`.
Canvas MVP0 owns the visual grammar in [canvas-topology mvp0](../../studio/feature-folders/canvas-topology/mvp0-alignment.md#cross-canvas-graph-patch).

MVP0 SHOULD hide old Harness concepts from the PM workflow.
Terms like retry router, checkpointer, heartbeat, and PhaseExecutor can remain internal implementation history, but they should not be the primary UI explanation.
The old Harness currently constructs phases/callbacks/checkpointer/graph builder in `packages/graph-agent/src/graph_agent/core/harness.py:356` to `packages/graph-agent/src/graph_agent/core/harness.py:390`.
MVP0 SHOULD not expose these as first-class Studio controls.

MVP0 SHOULD expose runtime transparency through trace, not through Harness logs.
Trace is the PM-readable timeline of graph execution.
Engine tracing MVP0 defines `TraceEventKind` and `V2TracingCallback`; Studio trace owns the UI in [trace-visualization mvp0](../../studio/feature-folders/trace-visualization/mvp0-alignment.md#cross-trace-edge-inspection).

MVP0 SHOULD make Copilot progressive disclosure explicit.
Progressive disclosure means the prompt receives only the context needed for the current user action, not the whole repository every time.
The UI expression is `@mentions`, and the owner contract is [copilot-assistance mvp0](../../studio/feature-folders/copilot-assistance/mvp0-alignment.md#cross-copilot-mentions).

## 前端逻辑

MVP0 WILL make frontend cognition flow through three stores/contracts: graph selection, trace selection, and Copilot mentions.
Graph selection identifies phase or edge.
Trace selection identifies event or edge payload.
Copilot mentions identify file/phase/edge/trace references for one chat request.

Current frontend graph mapping flattens V2.1 phases to `mode: "logic"` in `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:20` to `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:29`.
MVP0 SHOULD replace that with a `phaseType` projection that preserves LOGIC/SUBGRAPH/SKILL.

The frontend SHOULD treat `depends_on` as topology and phase IO as dataflow.
Current edges are built from `dependsOn`, see `apps/studio/frontend/src/components/nodes/buildEdges.ts:23` to `apps/studio/frontend/src/components/nodes/buildEdges.ts:49`.
MVP0 SHOULD overlay phase-level IO from engine contracts so an edge can show what data moves through it.

```typescript
export type CognitivePhaseType = "logic" | "subgraph" | "skill";

export interface CognitiveGraphNode {
  phaseId: string;
  name: string;
  phaseType: CognitivePhaseType;
  sourceFile: string;
  dependsOn: string[];
  io?: {
    inputKeys: string[];
    outputKeys: string[];
  };
  runtime?: {
    status: "idle" | "running" | "success" | "failed";
    latestTraceEventId?: string;
  };
}

export interface CognitiveGraphEdge {
  edgeId: string;
  sourcePhaseId: string;
  targetPhaseId: string;
  topologyKind: "depends_on" | "io_mapping" | "subgraph_boundary";
  hasTraceSnapshot: boolean;
}
```

MVP0 SHOULD make Copilot context explicit at send time.
Current chat send path only builds `{ user_message, model_override? }`, see `apps/studio/frontend/src/hooks/useCopilot.ts:143` to `apps/studio/frontend/src/hooks/useCopilot.ts:157`.
MVP0 SHOULD include structured mentions and implicit context as specified by Copilot mvp0.

```typescript
export interface CognitiveCopilotContext {
  selected:
    | { type: "phase"; phaseId: string }
    | { type: "edge"; sourcePhaseId: string; targetPhaseId: string }
    | { type: "trace_event"; runId: string; eventId: string }
    | { type: "file"; path: string }
    | null;
  mentions: Array<{
    type: "file" | "phase" | "edge_context" | "trace_event" | "compile_error";
    id: string;
    label: string;
  }>;
}
```

MVP0 SHOULD treat frontend as a consumer of engine truth, not as a second graph compiler.
Canvas may draft graph patches, but compile and IO validation belong to engine skill-compilation and state contracts.
Graph patch API is defined by [canvas-topology mvp0](../../studio/feature-folders/canvas-topology/mvp0-alignment.md#cross-canvas-graph-patch).

## 后端功能

MVP0 WILL deprecate old `GraphAgentHarness` as a primary runtime path.
Deprecate means "no longer the route Studio relies on", not "delete immediately".
The class still exists in `packages/graph-agent/src/graph_agent/core/harness.py:331` to `packages/graph-agent/src/graph_agent/core/harness.py:354`, and `Harness = GraphAgentHarness` still exists at `packages/graph-agent/src/graph_agent/core/harness.py:1150`.
MVP0 SHOULD make new work target V2.1 graph runtime first.

The V2.1 runtime entry should become the canonical path for directory skills.
Current `_run_v030_skill_dict()` compiles, assembles, and invokes the graph in `packages/graph-agent/src/graph_agent/core/runner.py:298` to `packages/graph-agent/src/graph_agent/core/runner.py:342`.
MVP0 SHOULD connect this path to ModelResolver, callbacks, trace, input funnel, and artifact output.

The backend SHOULD keep `run_skill()` as the public compatibility entry but route V2.1 through a clean architecture.
Current `run_skill()` signature is in `packages/graph-agent/src/graph_agent/core/runner.py:65` to `packages/graph-agent/src/graph_agent/core/runner.py:79`.
The old path may remain for legacy skills, but Studio MVP0 should create and run V2.1 skills.

MVP0 SHOULD make LOGIC/SUBGRAPH/SKILL a closed runtime dispatch.
Current dispatch happens in `_build_phase_node()` in `packages/graph-agent/src/graph_agent/core/graph_assembler.py:156` to `packages/graph-agent/src/graph_agent/core/graph_assembler.py:215`.
MVP0 SHOULD add missing runtime contracts around each branch rather than moving behavior back into Harness.

MVP0 SHOULD solve P0-1 by inserting ModelResolver before graph assembly.
Current runner derives `chat_model` / `active_model_resolver` before graph assembly in `packages/graph-agent/src/graph_agent/core/runner.py:332` to `packages/graph-agent/src/graph_agent/core/runner.py:342`, and SKILL node raises without a model in `packages/graph-agent/src/graph_agent/core/graph_assembler.py:408` to `packages/graph-agent/src/graph_agent/core/graph_assembler.py:413`.
Execution runtime owns the ModelResolver interface in [execution-runtime mvp0](../../engine/execution-runtime/mvp0-alignment.md#1-modelresolver-接口声明).

MVP0 SHOULD solve P1-4 by making trace/callback a V2.1 lifecycle contract.
Current runner builds an event sink in `packages/graph-agent/src/graph_agent/core/runner.py:237` to `packages/graph-agent/src/graph_agent/core/runner.py:248`.
Studio currently passes an `event_subscriber` function via `_queue_event_subscriber`, not a callback list, in `apps/studio/backend/app/services/run_manager.py:74` to `apps/studio/backend/app/services/run_manager.py:105`.
Tracing owns the event model in [tracing-and-observability mvp0](../../engine/tracing-and-observability/mvp0-alignment.md#api).

MVP0 SHOULD upgrade Copilot session building.
Current backend only injects cached view context into prompt in `apps/studio/backend/app/services/copilot.py:165` to `apps/studio/backend/app/services/copilot.py:180`.
MVP0 should resolve mentions to files, phases, edge context, trace events, and compile issues before calling Claude Agent SDK.

## API

MVP0 SHOULD declare architecture-level public contracts that feature docs implement.
The goal is not one mega endpoint; it is a stable boundary between Studio UI, Studio backend, and engine runtime.

Engine run contract:

```python
@dataclass
class V21RunRequest:
    skill_root: Path
    inputs: dict[str, Any]
    model_resolver: ModelResolver
    trace_sink: TraceSink | None = None
    artifact_dir: Path | None = None
    run_id: str | None = None

@dataclass
class V21RunResult:
    run_id: str
    final_state: BlackboardState
    phase_outputs: dict[str, dict[str, Any]]
    artifacts: list[Path]
    trace_summary: dict[str, Any]

def run_v21_skill(request: V21RunRequest) -> V21RunResult:
    """Canonical MVP0 runtime for V2.1 directory skills."""
```

Graph cognition projection contract:

```typescript
export interface CognitiveGraphSnapshot {
  skillId: string;
  manifestHash: string;
  nodes: CognitiveGraphNode[];
  edges: CognitiveGraphEdge[];
  compileIssues: Array<{
    code: string;
    severity: "error" | "warning";
    message: string;
    phaseId?: string;
    filePath?: string;
    line?: number;
  }>;
}
```

Copilot context build contract:

```python
class CopilotMention(BaseModel):
    type: Literal["file", "phase", "edge_context", "trace_event", "compile_error"]
    id: str
    label: str

class CopilotSessionRequest(BaseModel):
    skill_id: str
    user_message: str
    mentions: list[CopilotMention] = Field(default_factory=list)
    implicit_context: dict[str, Any] = Field(default_factory=dict)
    model_override: str | None = None

async def build_copilot_session_context(
    request: CopilotSessionRequest,
    workspace: StudioWorkspace,
) -> ResolvedCopilotContext:
    """Resolve frontend mentions into trusted prompt context."""
```

MVP0 SHOULD not keep the old architecture pseudo API `build_copilot_session(skill_id, error_log)`.
High-002 requires mentions payload, and the request model should match [copilot-assistance mvp0](../../studio/feature-folders/copilot-assistance/mvp0-alignment.md#cross-copilot-mentions).

## Data Model / State

MVP0 WILL define one engine runtime state spine.
State spine means the data structures that carry execution from input, through phases, to output and trace.
For V2.1, that spine is `BlackboardState` plus phase-level IO envelopes, not old Harness working memory.

Current `BlackboardState` has `data`, `flow`, `messages`, and `run_id`, see `packages/graph-agent/src/graph_agent/runtime/state.py:35` to `packages/graph-agent/src/graph_agent/runtime/state.py:41`.
Current `shallow_dict_merge` rejects top-level key conflicts in `packages/graph-agent/src/graph_agent/runtime/state.py:13` to `packages/graph-agent/src/graph_agent/runtime/state.py:32`.
MVP0 SHOULD wrap this with explicit phase inputs and outputs from [state-and-io-contract mvp0](../../engine/state-and-io-contract/mvp0-alignment.md#cross-state-blackboard-isolation).

```python
@dataclass
class CognitivePhaseEnvelope:
    phase_id: str
    phase_type: Literal["logic", "subgraph", "skill"]
    input_data: dict[str, Any]
    output_data: dict[str, Any]
    messages_delta: list[Any]
    trace_event_ids: list[str]
```

MVP0 SHOULD keep `GraphManifest` as the compile-time structure.
Current manifest has `phases`, `io_inputs_ref`, and `io_outputs_ref`, see `packages/graph-agent/src/graph_agent/core/manifest.py:45` to `packages/graph-agent/src/graph_agent/core/manifest.py:56`.
MVP0 SHOULD add phase IO schema through skill-compilation, not by inventing a separate Studio-only model.

MVP0 SHOULD make Studio run state a projection of engine state.
Current Studio `RunDetail` reads metadata, input data, events, final context, and artifacts in `apps/studio/backend/app/services/run_manager.py:304` to `apps/studio/backend/app/services/run_manager.py:317`.
MVP0 should continue exposing Studio-friendly run detail while preserving event and phase output fidelity.

MVP0 SHOULD make Copilot context state message-scoped.
View context can remain cached, but mentions belong to one chat request.
Current view context update model is `ContextUpdateRequest` in `apps/studio/backend/app/models/copilot.py:73` to `apps/studio/backend/app/models/copilot.py:80`.

## Cross-feature interaction

### Architecture V2.1 runtime owner {#cross-architecture-v21-runtime}

This architecture doc owns the top-level statement: V2.1 graph runtime becomes the primary mental and execution model.
Execution details are owned by [execution-runtime mvp0](../../engine/execution-runtime/mvp0-alignment.md#1-modelresolver-接口声明), [skill-compilation mvp0](../../engine/skill-compilation/mvp0-alignment.md#api), and [state-and-io-contract mvp0](../../engine/state-and-io-contract/mvp0-alignment.md#cross-state-blackboard-isolation).

### Architecture graph UI mapping {#cross-architecture-graph-ui}

Canvas owns visual graph editing and phase/edge interaction.
Architecture only requires that Canvas preserve LOGIC/SUBGRAPH/SKILL semantics.
See [canvas-topology mvp0](../../studio/feature-folders/canvas-topology/mvp0-alignment.md#cross-canvas-graph-patch).

### Architecture Copilot disclosure {#cross-architecture-copilot-disclosure}

Copilot owns mentions payload and patch application.
Architecture requires the request be structured and resolvable by backend.
See [copilot-assistance mvp0](../../studio/feature-folders/copilot-assistance/mvp0-alignment.md#cross-copilot-mentions).

### Architecture trace observability {#cross-architecture-trace}

Trace owns PM-visible phase input/output and edge inspection.
Architecture requires runtime events to come from execution, not frontend simulation.
See [trace-visualization mvp0](../../studio/feature-folders/trace-visualization/mvp0-alignment.md#cross-trace-edge-inspection) and [tracing-and-observability mvp0](../../engine/tracing-and-observability/mvp0-alignment.md#api).

### Architecture prod-dev boundary {#cross-architecture-prod-dev}

The process boundary and packaging split are owned by [prod-dev-separation mvp0](../prod-dev-separation/mvp0-alignment.md#cross-prod-dev-engine-boundary).
This file only defines what the runtime is, not where each process lives.
