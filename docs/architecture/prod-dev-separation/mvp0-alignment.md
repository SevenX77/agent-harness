# prod-dev-separation (architecture) — MVP0 Alignment (下一步对齐 MVP0 的改造逻辑)

> **Status**: Filled by a1 (Codex), 2026-05-20
> **Scope**: baseline: Harness/Callbacks/Schema 缠绕现状; MVP0: Engine 降为纯节点合集 + Studio 降为外部唤起壳
> **配套**: 见 [INDEX.md](../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

MVP0 WILL make the product boundary understandable to a PM.
Studio is the development shell.
Engine is the execution library.
Tauri is the desktop wrapper.
The current mixed state is in [baseline.md](./baseline.md).

First term: development shell means the UI and local services that help create, edit, run, and inspect skills.
First term: execution library means the code that compiles and runs V2.1 graph phases.
The PM should not have to distinguish these layers during normal use, but the architecture must separate their responsibilities.

MVP0 SHOULD keep one visible Studio app, not separate prod/dev UIs.
Current runtime config already changes behavior by environment in `apps/studio/frontend/src/config/runtime.ts:23` to `apps/studio/frontend/src/config/runtime.ts:58`.
MVP0 SHOULD make these states explicit: Desktop Production, Local Development, and Dev Tunnel.

Desktop Production SHOULD use Tauri sidecar only.
The app should start a local backend, expose a local token to the frontend, and avoid Vite/cloudflared paths.
Current sidecar startup is in `apps/studio/tauri/src/lib.rs:166` to `apps/studio/tauri/src/lib.rs:188`.

Local Development SHOULD use Vite proxy and local backend.
Current Vite proxy maps `/api` and `/ws` to `127.0.0.1:8787`, see `apps/studio/frontend/vite.config.ts:47` to `apps/studio/frontend/vite.config.ts:68`.
MVP0 SHOULD label this as dev-only and keep it out of production packaging logic.

Dev Tunnel SHOULD remain an explicit remote-browser access mode.
The token bootstrap currently reads `#tkn=` into sessionStorage in `apps/studio/frontend/src/config/tunnel-token.ts:1` to `apps/studio/frontend/src/config/tunnel-token.ts:13`.
MVP0 SHOULD not let tunnel behavior leak into Tauri production defaults.

## 前端逻辑

MVP0 WILL keep the frontend talking only to Studio backend over HTTP/WS and to Tauri over IPC for desktop-only actions.
The frontend should never import graph-agent or execute Python.
Current API client base URL and token handling are in `apps/studio/frontend/src/api/client.ts:20` to `apps/studio/frontend/src/api/client.ts:54`.

The frontend SHOULD have a typed runtime mode.

```typescript
export type StudioRuntimeMode = "desktop_prod" | "local_dev" | "dev_tunnel";

export interface StudioRuntimeBoundary {
  mode: StudioRuntimeMode;
  apiBaseUrl: string;
  wsBaseUrl: string;
  apiTokenSource: "tauri_sidecar" | "env_dev" | "tunnel_hash";
  tauriIpcAvailable: boolean;
  devProxyEnabled: boolean;
}
```

Current `SidecarConfig` has port/baseURL/wsURL/resourceDir/api_token in `apps/studio/frontend/src/config/runtime.ts:3` to `apps/studio/frontend/src/config/runtime.ts:9`.
MVP0 SHOULD wrap it in `StudioRuntimeBoundary` so code can branch intentionally.

Frontend business APIs SHOULD stay identical across modes.
`compileSkill`, `startRun`, `getSkillDetail`, and `writeSkillFile` are currently all in the same client surface, see `apps/studio/frontend/src/api/client.ts:81` to `apps/studio/frontend/src/api/client.ts:173`.
That is good separation: the UI does not care whether backend came from Tauri sidecar or local dev server.

Tauri IPC SHOULD stay desktop-system-only.
Current desktop helpers live in `apps/studio/frontend/src/lib/tauri.ts:4` to `apps/studio/frontend/src/lib/tauri.ts:79`.
MVP0 SHOULD not route business actions like "run graph" through Tauri IPC.

WebSocket construction SHOULD remain backend-owned.
Current `wsUrl()` converts API base URL to WS URL and adds token in `apps/studio/frontend/src/api/client.ts:101` to `apps/studio/frontend/src/api/client.ts:108`.
MVP0 SHOULD keep run events, Copilot, and terminal WS under Studio backend contracts.

## 后端功能

MVP0 WILL make Studio backend an adapter, not a second engine.
Adapter means it authenticates, reads/writes workspace files, starts runs, stores traces/artifacts, and translates results for UI.
Engine owns compile/run semantics.

Current backend imports graph-agent directly for compile and run.
Compile adapter is in `apps/studio/backend/app/services/skills.py:294` to `apps/studio/backend/app/services/skills.py:311`.
Run worker calls `run_skill()` in `apps/studio/backend/app/services/run_manager.py:220` to `apps/studio/backend/app/services/run_manager.py:235`.
MVP0 SHOULD narrow this to a single V2.1 engine execution boundary.

Engine SHOULD become a pure node/graph runtime surface.
Pure means no Studio event schema, no Tauri path assumptions, no UI concepts, and no Copilot session logic.
It can still emit trace events, but those events must be engine lifecycle events, not UI commands.

MVP0 SHOULD resolve Harness/Callbacks/Schema entanglement by moving callbacks to V2 tracing.
Legacy runner creates callbacks in `packages/graph-agent/src/graph_agent/core/runner.py:284` to `packages/graph-agent/src/graph_agent/core/runner.py:286`.
V2.1 currently deletes callbacks in `packages/graph-agent/src/graph_agent/core/runner.py:462`.
The replacement is [tracing-and-observability mvp0](../../engine/tracing-and-observability/mvp0-alignment.md#api).

MVP0 SHOULD solve A1-A6 at the engine boundary.
Runtime input funnel, phase-level IO, subgraph isolation, and blackboard conflict rules belong in engine state-and-io.
Architecture should only require Studio to call that boundary instead of patching around it.
See [state-and-io-contract mvp0](../../engine/state-and-io-contract/mvp0-alignment.md#cross-state-blackboard-isolation).

Tauri SHOULD own sidecar process lifecycle only.
Current sidecar config points to bundled Python/backend/resources in `apps/studio/tauri/src/sidecar.rs:53` to `apps/studio/tauri/src/sidecar.rs:74`.
Spawn env is set in `apps/studio/tauri/src/sidecar.rs:241` to `apps/studio/tauri/src/sidecar.rs:260`.
MVP0 SHOULD keep that lifecycle but not make Tauri understand graph internals.

Backend auth SHOULD stay shared across modes.
Current auth requires `STUDIO_API_TOKEN` or `STUDIO_DEV_TUNNEL_TOKEN` in `apps/studio/backend/app/main.py:66` to `apps/studio/backend/app/main.py:99`.
MVP0 SHOULD keep no-dev-bypass as the default.

## API

MVP0 SHOULD define three API boundaries: frontend-backend, backend-engine, frontend-Tauri.
Each boundary needs a clear signature and owner.

Frontend-backend boundary remains REST/WS.
The routers are registered in `apps/studio/backend/app/main.py:112` to `apps/studio/backend/app/main.py:140`.
Business endpoints such as compile/run remain backend APIs, see `apps/studio/backend/app/routers/skills.py:108` to `apps/studio/backend/app/routers/skills.py:118` and `apps/studio/backend/app/routers/runs.py:27` to `apps/studio/backend/app/routers/runs.py:55`.

Backend-engine boundary SHOULD be a narrow Python contract.

```python
class EngineRuntimePort(Protocol):
    def compile(self, skill_root: Path) -> CompiledSkill: ...

    def run_v21(
        self,
        skill_root: Path,
        inputs: dict[str, Any],
        model_resolver: ModelResolver,
        trace_sink: TraceSink,
        artifact_dir: Path,
        run_id: str,
    ) -> V21RunResult: ...
```

Studio backend implementation:

```python
class StudioEngineAdapter:
    def __init__(self, runtime: EngineRuntimePort, run_store: RunStore) -> None: ...

    async def start_run(self, request: StudioRunRequest) -> StudioRunHandle:
        """Validate Studio request, invoke engine runtime, persist trace/artifacts."""
```

Frontend-Tauri boundary SHOULD stay sidecar/system capability only.

```typescript
export interface TauriSidecarConfig {
  port: number;
  baseURL: string;
  wsURL: string;
  resourceDir: string;
  api_token: string;
}

export interface TauriDesktopCommands {
  get_sidecar_config(): Promise<TauriSidecarConfig>;
  open_in_cursor(path: string): Promise<void>;
  open_in_terminal(path: string): Promise<void>;
  reveal_in_file_manager(path: string): Promise<void>;
}
```

Current Tauri command registration is in `apps/studio/tauri/src/lib.rs:147` to `apps/studio/tauri/src/lib.rs:157`.
MVP0 SHOULD not add `run_graph` or `compile_graph` Tauri commands.

Dev tunnel contract SHOULD be configuration, not a separate API.

```typescript
export interface DevTunnelRuntimeConfig {
  mode: "dev_tunnel";
  apiBaseUrl: "/api";
  wsBaseUrl: "/ws";
  tokenHashParam: "tkn";
}
```

## Data Model / State

MVP0 WILL separate state ownership by layer.
Frontend owns UI state.
Studio backend owns workspace/run/artifact state.
Engine owns graph runtime state.
Tauri owns sidecar process state.

```typescript
export interface ProdDevStateOwnership {
  frontend: ["panel layout", "draft files", "selected node", "active run view"];
  studioBackend: ["workspace index", "run records", "trace events", "artifacts"];
  engine: ["CompiledSkill", "BlackboardState", "phase inputs", "phase outputs"];
  tauri: ["sidecar process", "resource root", "desktop commands"];
}
```

Engine `BlackboardState` stays inside engine runtime.
It is currently defined in `packages/graph-agent/src/graph_agent/runtime/state.py:35` to `packages/graph-agent/src/graph_agent/runtime/state.py:41`.
Studio may persist final state or trace projections, but it should not mutate the live blackboard.

Studio run state SHOULD remain a persisted projection.
Current `get_run_detail()` reads input, trace, final state, and artifacts from run storage in `apps/studio/backend/app/services/run_manager.py:408` to `apps/studio/backend/app/services/run_manager.py:422`.
MVP0 SHOULD extend this with V2 trace events and phase outputs.

Tauri sidecar state SHOULD remain process lifecycle state.
Current health/config path is in `apps/studio/tauri/src/sidecar.rs:123` to `apps/studio/tauri/src/sidecar.rs:134`.
Frontend sees only a config object, not the Rust child process.

Packaging state SHOULD separate dev and prod resources.
Current Tauri config includes frontend dist/devUrl and bundled resources in `apps/studio/tauri/tauri.conf.json:6` to `apps/studio/tauri/tauri.conf.json:33`.
MVP0 SHOULD make the production bundle depend on built frontend and bundled backend/runtime, while dev uses Vite and source backend.

## Cross-feature interaction

### Prod/dev engine boundary owner {#cross-prod-dev-engine-boundary}

This document owns the architecture boundary between Studio backend and engine.
Engine runtime details are owned by [execution-runtime mvp0](../../engine/execution-runtime/mvp0-alignment.md#1-modelresolver-接口声明), [state-and-io-contract mvp0](../../engine/state-and-io-contract/mvp0-alignment.md#cross-state-blackboard-isolation), and [tracing-and-observability mvp0](../../engine/tracing-and-observability/mvp0-alignment.md#api).

### Prod/dev Studio shell owner {#cross-prod-dev-studio-shell}

Studio remains the development shell for visual edit/run/debug.
Canvas, editor, trace, Copilot, provider config, and lifecycle are feature owners:
[canvas-topology mvp0](../../studio/feature-folders/canvas-topology/mvp0-alignment.md#cross-canvas-graph-patch),
[multi-file-editor mvp0](../../studio/feature-folders/multi-file-editor/mvp0-alignment.md#cross-editor-save-compile),
[trace-visualization mvp0](../../studio/feature-folders/trace-visualization/mvp0-alignment.md#cross-trace-edge-inspection),
[copilot-assistance mvp0](../../studio/feature-folders/copilot-assistance/mvp0-alignment.md#cross-copilot-mentions),
[llm-provider-config mvp0](../../studio/feature-folders/llm-provider-config/mvp0-alignment.md#cross-llm-role-resolution),
and [skill-lifecycle mvp0](../../studio/feature-folders/skill-lifecycle/mvp0-alignment.md#cross-lifecycle-v21-create).

### Prod/dev Tauri boundary {#cross-prod-dev-tauri}

Tauri owns sidecar startup, resource discovery, and desktop commands.
Workspace file semantics are owned by [workspace-file-system mvp0](../../studio/system-level/workspace-file-system/mvp0-alignment.md).
Tauri should not become a business runtime.

### Prod/dev cognitive link {#cross-prod-dev-cognitive-link}

Agent cognitive architecture defines the runtime mental model.
This file defines where that runtime lives and how Studio invokes it.
See [agent-cognitive-architecture mvp0](../agent-cognitive-architecture/mvp0-alignment.md#cross-architecture-v21-runtime).

### Prod/dev dev-mode boundary {#cross-prod-dev-dev-mode}

Dev tunnel and Vite proxy are development access modes only.
They should continue to use backend auth and the same API surface, but they should not shape production Tauri packaging.
