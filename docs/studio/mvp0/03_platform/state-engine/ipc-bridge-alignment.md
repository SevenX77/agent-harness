# tauri-ipc-bridge (studio system-level) — MVP0 Alignment (下一步对齐 MVP0 的改造逻辑)

> **Status**: Filled by a1 (Codex), 2026-05-20
> **Scope**: Tauri shell ↔ webview frontend IPC contract (`#[tauri::command]` Rust functions ↔ frontend `invoke()` calls).
> **配套**: 见 [INDEX.md](../../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

MVP0 WILL keep Tauri IPC as a desktop capability bridge, not a business runtime.
The current command list is in [baseline.md](./baseline.md).

PM-facing desktop actions SHOULD be clear:
choose folder, reveal file, open terminal/tool, manage local sidecar health, and store API keys securely.
PM should not see Tauri as a separate product surface.

MVP0 SHOULD add structured sidecar diagnostics.
Today `get_sidecar_stderr` returns lines, see `apps/studio/tauri/src/lib.rs:35` to `apps/studio/tauri/src/lib.rs:52`.
The UI should show sidecar status, recent stderr, and retry guidance when backend fails to start.

MVP0 SHOULD add keychain-backed credential storage if LLM provider config moves secrets out of JSON files.
Keychain means OS credential storage, for example macOS Keychain, Windows Credential Manager, or Secret Service.
LLM provider config owns provider UI in [llm-provider-config mvp0](../../03_platform/llm-gateway/mvp0-alignment.md#cross-llm-secure-storage).

MVP0 SHOULD not add Tauri commands for editing normal skill files unless backend cannot own it.
Workspace file system MVP0 says scaffold and complex writes should go through backend, see [workspace-file-system mvp0](../workspace-file-system/mvp0-alignment.md#前端逻辑).
Tauri can select paths and reveal files.

## 前端逻辑

MVP0 SHOULD wrap all invokes in a typed bridge.
Current frontend calls `invoke(command, { path })` directly inside helpers, see `apps/studio/frontend/src/lib/tauri.ts:18` to `apps/studio/frontend/src/lib/tauri.ts:23`.
MVP0 should return structured errors and preserve command name.

```typescript
export interface TauriIpcError {
  command: string;
  code: string;
  message: string;
  details?: unknown;
}

export async function invokeStudioCommand<TArgs, TResult>(
  command: string,
  args: TArgs,
): Promise<TResult>;
```

MVP0 SHOULD keep non-Tauri fallbacks explicit.
`revealInFileManager` already copies path in browser mode, see `apps/studio/frontend/src/lib/tauri.ts:56` to `apps/studio/frontend/src/lib/tauri.ts:61`.
Other commands should return a typed `desktop_unavailable` error instead of silently no-oping.

MVP0 SHOULD add IPC payload size guidance.
Large file reads/writes should not cross IPC unless required.
HTTP backend file APIs are already the skill file path, see `apps/studio/frontend/src/api/client.ts:162` to `apps/studio/frontend/src/api/client.ts:173`.
Tauri IPC should pass paths and small metadata, not megabytes of skill content.

MVP0 SHOULD expose a single `useTauriBridge()` hook.
It should report `available`, `runtimeConfig`, and `commands`.
This prevents components from repeating runtime detection.

## 后端功能

MVP0 SHOULD add workspace path helper commands only where native dialogs or OS integration are required.
Directory picker currently uses plugin dialog directly, see `apps/studio/frontend/src/lib/tauri.ts:64` to `apps/studio/frontend/src/lib/tauri.ts:79`.
If policy requires Rust-side validation, add a wrapper command.

Proposed Rust commands:

```rust
#[tauri::command]
fn select_workspace_directory() -> Result<Option<String>, StudioIpcError>;

#[tauri::command]
fn keychain_read(service: String, account: String) -> Result<Option<String>, StudioIpcError>;

#[tauri::command]
fn keychain_write(service: String, account: String, secret: String) -> Result<(), StudioIpcError>;

#[tauri::command]
fn keychain_delete(service: String, account: String) -> Result<(), StudioIpcError>;

#[tauri::command]
fn get_sidecar_status(state: tauri::State<'_, SidecarAppState>) -> Result<SidecarStatus, StudioIpcError>;
```

MVP0 SHOULD not add `workspace.init` as Tauri FS writer unless PM explicitly chooses frontend-native scaffolding.
The current audit High-004 asks ownership to be clear; backend API is the better owner because scaffold may touch `.workspace`, templates, and indexes.
Skill lifecycle and workspace file system own that backend path.

Sidecar lifecycle SHOULD remain Rust-owned.
Current startup attempts and health check live in `apps/studio/tauri/src/sidecar.rs:113` to `apps/studio/tauri/src/sidecar.rs:143`.
MVP0 can expose status, but should not let frontend directly kill arbitrary processes.

MVP0 SHOULD normalize Rust errors.
Current commands return `String`, see `apps/studio/tauri/src/lib.rs:15` to `apps/studio/tauri/src/lib.rs:145`.
Structured errors will make frontend toasts specific and testable.

## API

Rust error model:

```rust
#[derive(Debug, serde::Serialize)]
pub struct StudioIpcError {
    pub code: String,
    pub message: String,
    pub details: Option<serde_json::Value>,
}

pub type StudioIpcResult<T> = Result<T, StudioIpcError>;
```

Sidecar status:

```rust
#[derive(Debug, serde::Serialize)]
pub struct SidecarStatus {
    pub running: bool,
    pub port: Option<u16>,
    pub base_url: Option<String>,
    pub stderr_tail: Vec<String>,
    pub startup_error: Option<String>,
}
```

Frontend bridge:

```typescript
export interface SidecarStatusDto {
  running: boolean;
  port?: number;
  baseURL?: string;
  stderrTail: string[];
  startupError?: string;
}

export interface KeychainSecretRef {
  service: "studio-llm";
  account: string;
}

export interface TauriBridge {
  available: boolean;
  getSidecarConfig(): Promise<SidecarConfig>;
  getSidecarStatus(): Promise<SidecarStatusDto>;
  openInCursor(path: string): Promise<void>;
  openInCodex(path: string): Promise<void>;
  openInTerminal(path: string): Promise<void>;
  revealInFileManager(path: string): Promise<void>;
  keychainRead(ref: KeychainSecretRef): Promise<string | null>;
  keychainWrite(ref: KeychainSecretRef, secret: string): Promise<void>;
  keychainDelete(ref: KeychainSecretRef): Promise<void>;
}
```

IPC payload policy:

```typescript
export interface IpcPayloadPolicy {
  maxInlineBytes: 256_000;
  largeFileStrategy: "use_backend_http" | "use_temp_file_token";
  binaryPayloadsAllowed: false;
}
```

## Data Model & State

MVP0 SHOULD keep Tauri state small.
Tauri state should include sidecar process, runtime config, startup error, and maybe keychain availability.
It should not include current skill graph, editor drafts, or trace events.

Frontend state should treat Tauri as capability provider.
Runtime config already becomes API base URL and token through `initializeRuntimeConfig`, see `apps/studio/frontend/src/config/runtime.ts:51` to `apps/studio/frontend/src/config/runtime.ts:58`.
MVP0 should add `tauriCapabilities`.

```typescript
export interface TauriCapabilities {
  shellTools: boolean;
  dialog: boolean;
  keychain: boolean;
  sidecar: boolean;
}
```

Secrets should be referenced by opaque id in frontend state.
Do not put API key plaintext in React global state longer than necessary.
LLM config can display masked values and ask keychain on save/test.

Large workspace file content should remain backend-owned.
This avoids duplicating file watcher, conflict handling, and hash checks across Rust and Python.

## Cross-feature interaction

### Tauri keychain owner {#cross-tauri-keychain-owner}

Tauri IPC owns native keychain command contracts if MVP0 moves secrets out of JSON files.
LLM provider config owns provider UI and role resolution, see [llm-provider-config mvp0](../../03_platform/llm-gateway/mvp0-alignment.md#cross-llm-secure-storage).

### Tauri workspace selection owner {#cross-tauri-workspace-selection}

Tauri owns native folder selection and reveal/open actions.
Backend owns scaffold and file writes.
Workspace file system details are in [workspace-file-system mvp0](../workspace-file-system/mvp0-alignment.md#前端逻辑).

### Tauri prod boundary owner {#cross-tauri-prod-boundary}

Tauri owns desktop sidecar lifecycle.
Prod/dev architecture owns process separation in [prod-dev-separation mvp0](../../../architecture/prod-dev-separation/mvp0-alignment.md#cross-prod-dev-tauri).

### Tauri event boundary {#cross-tauri-event-boundary}

MVP0 realtime events should remain backend WebSocket events unless there is a native-only reason.
Transport details are in [event-bus-and-websocket mvp0](../event-bus-and-websocket/mvp0-alignment.md#cross-events-state-ingestion).

