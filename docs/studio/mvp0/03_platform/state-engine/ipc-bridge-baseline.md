# tauri-ipc-bridge (studio system-level) — Baseline (当下代码实现逻辑)

> **Status**: Filled by a1 (Codex), 2026-05-20
> **Scope**: Tauri shell ↔ webview frontend IPC contract (`#[tauri::command]` Rust functions ↔ frontend `invoke()` calls).
> **配套**: 见 [INDEX.md](../../../INDEX.md) 5 维模板 + cross-link 规则 + writing conventions。

## UI/UX

当前 Tauri IPC 只支撑桌面壳能力。
PM 能通过 UI 打开 Cursor、Codex、Terminal、文件管理器，或选择目录。
PM 不能通过 Tauri IPC 直接读写 skill 文件内容。

First term: Tauri IPC means JavaScript in the webview calls a Rust command through `invoke()`.
It is not HTTP.
It is only available in the Tauri desktop runtime.

Frontend runtime checks Tauri by testing `window.__TAURI_INTERNALS__`, see `apps/studio/frontend/src/config/runtime.ts:23` to `apps/studio/frontend/src/config/runtime.ts:25`.
Non-Tauri mode falls back to normal web behavior or shows desktop-only toast.

Sidecar config is the most important IPC.
Frontend calls `get_sidecar_config` in `resolveRuntimeConfig`, see `apps/studio/frontend/src/config/runtime.ts:43` to `apps/studio/frontend/src/config/runtime.ts:48`.
The config sets HTTP/WS base URLs and API token via `initializeRuntimeConfig`, see `apps/studio/frontend/src/config/runtime.ts:51` to `apps/studio/frontend/src/config/runtime.ts:58`.

Shell tool commands are desktop-only.
`openInCursor`, `openInTerminal`, `openInCodex`, and `revealInFileManager` call Rust commands through `invoke`, see `apps/studio/frontend/src/lib/tauri.ts:26` to `apps/studio/frontend/src/lib/tauri.ts:62`.
Directory picker uses Tauri dialog plugin instead of a custom Rust command, see `apps/studio/frontend/src/lib/tauri.ts:64` to `apps/studio/frontend/src/lib/tauri.ts:79`.

The desktop shell does not change the primary Studio navigation model.
The same React app renders in browser dev mode and in Tauri desktop mode.
The visible difference is capability availability: desktop can launch local tools and use sidecar config, while browser mode relies on configured HTTP/WS URLs.
This is why IPC failures usually surface as toast messages rather than separate error pages.

## 前端逻辑

The frontend bridge lives mainly in two files.
Runtime config bridge is `apps/studio/frontend/src/config/runtime.ts:1` to `apps/studio/frontend/src/config/runtime.ts:86`.
Desktop shell bridge is `apps/studio/frontend/src/lib/tauri.ts:1` to `apps/studio/frontend/src/lib/tauri.ts:79`.

`invokeShell` validates path, checks runtime, imports `@tauri-apps/api/core`, invokes a command, and shows toast on failure, see `apps/studio/frontend/src/lib/tauri.ts:4` to `apps/studio/frontend/src/lib/tauri.ts:24`.
It catches all Rust errors into a generic "Failed to open desktop tool" toast.

`revealInFileManager` has a non-Tauri fallback.
If not Tauri, it copies the path to clipboard if possible, see `apps/studio/frontend/src/lib/tauri.ts:38` to `apps/studio/frontend/src/lib/tauri.ts:62`.
Other shell commands simply show "desktop only".

`selectSkillDirectory` uses plugin dialog dynamic import with `@vite-ignore`, see `apps/studio/frontend/src/lib/tauri.ts:64` to `apps/studio/frontend/src/lib/tauri.ts:79`.
It returns `string | null`.
It does not create files.

There are no frontend `listen()` calls for Tauri events in the inspected bridge.
The Rust side also does not emit custom frontend events in the current code path.
So current IPC is request/response commands, not event streaming.

Frontend command calls are intentionally narrow.
`invokeShell` accepts only command name plus path string, see `apps/studio/frontend/src/lib/tauri.ts:4` to `apps/studio/frontend/src/lib/tauri.ts:24`.
There is no generic `invoke(anyCommand, anyPayload)` wrapper exported to feature code.
That keeps feature surfaces from depending directly on arbitrary Rust commands.

Runtime config is initialized once at startup.
`main.tsx` calls `resolveRuntimeConfig` before rendering, see `apps/studio/frontend/src/main.tsx:6` to `apps/studio/frontend/src/main.tsx:14`.
If sidecar config fails, the fallback behavior is controlled in `resolveRuntimeConfig`, not in each API call site.

## 后端功能

Tauri Rust starts and manages the Python sidecar.
`run()` registers commands and starts sidecar unless `STUDIO_TAURI_DISABLE_SIDECAR=1`, see `apps/studio/tauri/src/lib.rs:147` to `apps/studio/tauri/src/lib.rs:194`.
On exit it shuts down the sidecar, see `apps/studio/tauri/src/lib.rs:200` to `apps/studio/tauri/src/lib.rs:217`.

Command list:
`get_sidecar_config` is defined in `apps/studio/tauri/src/lib.rs:15` to `apps/studio/tauri/src/lib.rs:33`.
`get_sidecar_stderr` is defined in `apps/studio/tauri/src/lib.rs:35` to `apps/studio/tauri/src/lib.rs:52`.
`open_in_cursor` is defined in `apps/studio/tauri/src/lib.rs:62` to `apps/studio/tauri/src/lib.rs:65`.
`open_in_codex` is defined in `apps/studio/tauri/src/lib.rs:67` to `apps/studio/tauri/src/lib.rs:70`.
`reveal_in_file_manager` is defined in `apps/studio/tauri/src/lib.rs:72` to `apps/studio/tauri/src/lib.rs:99`.
`open_in_terminal` is defined in `apps/studio/tauri/src/lib.rs:101` to `apps/studio/tauri/src/lib.rs:145`.
They are registered in `tauri::generate_handler!` at `apps/studio/tauri/src/lib.rs:150` to `apps/studio/tauri/src/lib.rs:157`.

Sidecar runtime config is Rust-serialized.
`SidecarRuntimeConfig` has port/baseURL/wsURL/resourceDir/api_token, see `apps/studio/tauri/src/sidecar.rs:77` to `apps/studio/tauri/src/sidecar.rs:98`.
Sidecar manager starts Python, waits for health, and stores config, see `apps/studio/tauri/src/sidecar.rs:113` to `apps/studio/tauri/src/sidecar.rs:143`.

Sidecar launch config locates bundled Python/backend/site-packages/resources, see `apps/studio/tauri/src/sidecar.rs:51` to `apps/studio/tauri/src/sidecar.rs:74`.
Spawn sets `PYTHONPATH`, `STUDIO_RESOURCE_DIR`, `STUDIO_API_TOKEN`, and `STUDIO_EXIT_ON_ORPHAN`, see `apps/studio/tauri/src/sidecar.rs:241` to `apps/studio/tauri/src/sidecar.rs:260`.

Shell command execution uses OS-specific helpers.
The Rust `spawn_tool` helper starts external commands with platform branches, see `apps/studio/tauri/src/lib.rs:54` to `apps/studio/tauri/src/lib.rs:60`.
`reveal_in_file_manager` uses Finder on macOS, Explorer on Windows, and `xdg-open` on Linux, see `apps/studio/tauri/src/lib.rs:72` to `apps/studio/tauri/src/lib.rs:99`.
`open_in_terminal` has its own platform branches, see `apps/studio/tauri/src/lib.rs:101` to `apps/studio/tauri/src/lib.rs:145`.

Sidecar lifecycle has startup and shutdown paths.
`SidecarManager::start` spawns the child process and waits for health, see `apps/studio/tauri/src/sidecar.rs:145` to `apps/studio/tauri/src/sidecar.rs:183`.
Shutdown first sends an HTTP shutdown request and then kills the process if needed, see `apps/studio/tauri/src/sidecar.rs:279` to `apps/studio/tauri/src/sidecar.rs:315`.
The Tauri layer therefore owns backend process lifetime in desktop mode.

## API

Rust command signatures:

```rust
fn get_sidecar_config(
    state: tauri::State<'_, SidecarAppState>,
) -> Result<sidecar::SidecarRuntimeConfig, String>

fn get_sidecar_stderr(state: tauri::State<'_, SidecarAppState>) -> Vec<String>

fn open_in_cursor(path: String) -> Result<(), String>
fn open_in_codex(path: String) -> Result<(), String>
fn reveal_in_file_manager(path: String) -> Result<(), String>
fn open_in_terminal(path: String) -> Result<(), String>
```

Frontend command union:

```typescript
type TauriCommand =
  | "open_in_cursor"
  | "open_in_terminal"
  | "open_in_codex"
  | "reveal_in_file_manager";
```

The union is in `apps/studio/frontend/src/lib/tauri.ts:4`.

Sidecar config TS model:

```typescript
export interface SidecarConfig {
  port: number
  baseURL: string
  wsURL: string
  resourceDir: string
  api_token?: string | null
}
```

It is defined in `apps/studio/frontend/src/config/runtime.ts:3` to `apps/studio/frontend/src/config/runtime.ts:9`.

Current command gaps:

| Capability | Current IPC? |
|---|---|
| Read skill file | No |
| Write skill file | No |
| Initialize workspace scaffold | No |
| Watch workspace | No, backend watcher |
| Keychain read/write | No |
| Sidecar config | Yes |
| Open desktop tool | Yes |
| Directory picker | Dialog plugin |

Current sidecar startup result:

```rust
struct SidecarAppState {
    manager: Mutex<Option<sidecar::SidecarManager>>,
    startup_error: Mutex<Option<String>>,
}
```

This is defined in `apps/studio/tauri/src/lib.rs:10` to `apps/studio/tauri/src/lib.rs:13`.
`get_sidecar_config` returns startup error text when manager config is missing, see `apps/studio/tauri/src/lib.rs:15` to `apps/studio/tauri/src/lib.rs:33`.

Current frontend runtime entry point:

```typescript
export async function resolveRuntimeConfig(): Promise<SidecarConfig | null>
export function initializeRuntimeConfig(config: SidecarConfig | null): void
export function isTauriRuntime(): boolean
```

These functions live in `apps/studio/frontend/src/config/runtime.ts:23` to `apps/studio/frontend/src/config/runtime.ts:86`.

## Data Model & State

Tauri state is `SidecarAppState`.
It holds `manager` and `startup_error`, see `apps/studio/tauri/src/lib.rs:10` to `apps/studio/tauri/src/lib.rs:13`.
This state is not visible to frontend except through commands.

Sidecar manager state holds child process, token, runtime config, stderr ring, and shutdown timeout, see `apps/studio/tauri/src/sidecar.rs:101` to `apps/studio/tauri/src/sidecar.rs:111`.
Frontend gets a copy of runtime config through `get_sidecar_config`.

Frontend runtime state stores normalized config in module variable `runtimeConfig`, see `apps/studio/frontend/src/config/runtime.ts:21` to `apps/studio/frontend/src/config/runtime.ts:23`.
`initializeRuntimeConfig` configures Axios base URL and token, see `apps/studio/frontend/src/config/runtime.ts:51` to `apps/studio/frontend/src/config/runtime.ts:58`.

IPC errors are strings.
Rust commands return `Result<_, String>`, and frontend catches without preserving code/details in `apps/studio/frontend/src/lib/tauri.ts:18` to `apps/studio/frontend/src/lib/tauri.ts:23`.
There is no structured IPC error model.

Dev vs prod:
In web/dev runtime, `isTauriRuntime()` is false and most IPC functions show desktop-only toast.
In desktop runtime, sidecar config comes from Rust.
Production Tauri bundle includes sidecar resources, while dev can disable sidecar by env.

Data crossing IPC is small.
Commands pass paths, config objects, or stderr line arrays.
They do not pass full skill files, run traces, or large artifact payloads.
Those larger data flows remain HTTP or WebSocket backend responsibilities.

The sidecar stderr ring is a diagnostic state surface.
`get_sidecar_stderr` returns captured lines from the manager when available, see `apps/studio/tauri/src/lib.rs:35` to `apps/studio/tauri/src/lib.rs:52`.
The ring is maintained in `SidecarManager`, see `apps/studio/tauri/src/sidecar.rs:107` to `apps/studio/tauri/src/sidecar.rs:111`.
This gives desktop support visibility without exposing the whole process object to React.

Security boundary is command-level.
Frontend code cannot call arbitrary shell commands through the current public helper; it can only request named commands.
Rust still performs the actual OS process spawn.
There is no current keychain store or permission prompt layer beyond Tauri plugin permissions and command availability.

## Cross-feature interaction

### Tauri current shell boundary {#cross-tauri-current-shell-boundary}

Tauri IPC currently owns desktop shell actions and sidecar config.
Workspace file reads/writes are backend HTTP, documented in [workspace-file-system baseline](../workspace-file-system/baseline.md).

### Tauri prod-dev baseline boundary {#cross-tauri-prod-dev-baseline}

Tauri is part of the prod/dev separation boundary.
Architecture details are in [prod-dev-separation baseline](../../../architecture/prod-dev-separation/baseline.md).

### Tauri event gap {#cross-tauri-event-gap}

Current bridge has no Tauri frontend event listeners or custom emits.
Realtime workspace/run events are backend WebSockets, documented in [event-bus-and-websocket baseline](../event-bus-and-websocket/baseline.md).
