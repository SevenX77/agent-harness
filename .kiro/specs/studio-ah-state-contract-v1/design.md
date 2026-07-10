---
spec: studio-ah-state-contract-v1
status: Draft (revised per operator-review-findings.md F1-F8, 2026-07-09 review / 2026-07-10 revision)
target_goal: "Studio 接入 ah v1.4.0+ 结构化 runtime snapshot"
last_updated: 2026-07-10
revision_source: operator-review-findings.md
revision_trace: REVISION-TRACE.md
---

# Studio ah State Contract V1 Design

## Overview

This feature replaces Studio's local ah lifecycle guessing with ah v1.4.0+'s structured state contract. Tauri becomes a thin adapter around `ah events --format json` (primary decision plane) and `ah status --json` (bootstrap/fallback read); the frontend remains a projection of the server-authoritative status event.

The important behavior change is conceptual, in three parts:

1. `ahd alive && active=false` is not automatically an error. It can be the correct state after master exits, after a session closes, or while no selected config has an active runtime.
2. `runtime_state` is a **four-value phase**, not a boolean: `active`, `inactive`, `starting`, `degraded`. `starting` is hands-off (startup in progress); `degraded` must expose a working Open-with-cleanup path, never a fully dead button set. Cleanup is driven by ah's own per-session cleanup-eligibility fields, not by Studio re-deriving "non-terminal therefore kill".
3. Ownership is not just "which config", but **who owns the config**: a config Studio discovers by walking up the directory tree may belong to someone else's already-running ah session (including this very repository's own operator-managed fleet). Only Studio-generated temp configs are eligible for lifecycle mutation; every snapshot is identity-checked against the config Studio actually asked about before it is trusted.

## Goals

- Use ah v1.4.0+ as the lifecycle authority.
- Remove `ah ps` text parsing and tmux liveness probing from normal status decisions.
- Make `active`, `inactive`, `starting`, `degraded`, and daemon-absent states explicit and testable — not just the terminal session statuses.
- Make the events stream the primary decision plane, with `status --json` as bootstrap/fallback input only, arbitrated by `sequence`.
- Draw an explicit ownership line between workspace-owned ah configs (read-only) and Studio-managed temp configs (full lifecycle), and clamp the environment Studio's ah invocations inherit.
- Keep React UI as a thin projection of Tauri status events, using a payload rich enough to represent all of the above truthfully.

## Non-Goals

- Do not implement native process supervision in Studio.
- Do not read or migrate ah sqlite.
- Do not add Studio-owned lifecycle states that duplicate ah's state machine.
- Do not clean non-Studio ah stacks, including workspace-owned configs Studio did not create.
- Do not allow more than one Studio-managed ahd per workspace at a time (unchanged product invariant; see Requirements 6.3).

## Architecture

### Existing Architecture Analysis

Current Studio status handling mixes multiple sources:

- `ah events --format json` feeds status events.
- A separate runtime inspection path calls `ah ps`, parses textual rows, and probes tmux sessions.
- Cleanup can fall through to direct tmux session killing.
- `find_ah_config` walks up from the workspace root with no ownership distinction, and prefers whatever it finds over the Studio temp config (lib.rs:203-218, lib.rs:828-833).
- ah invocations on Windows go through a `wsl.exe -e bash -lc` **login shell**, which inherits the user's WSL profile environment, including anything that pins `AH_STATE_DIR`/`CCBD_STATE_DIR`/`XDG_STATE_HOME` (lib.rs:858/879/927).
- The frontend event payload is `{claude: bool, codex: bool}` with an explicit claude-wins suppression of codex (lib.rs:63-73, lib.rs:1244-1246), even though the frontend already renders a dual-active state.

This creates a second, weaker lifecycle model inside Studio, plus two latent ownership-safety gaps and an expressiveness gap in the UI payload. The v1.4.0+ contract, applied with explicit ownership and phase handling, removes all of these.

### Architecture Pattern & Boundary Map

```mermaid
flowchart LR
  UI["React Copilot Panel"] --> EVT["Tauri code-assistant-status-changed (per-assistant enum + reason)"]
  EVT --> ADAPTER["Studio ah adapter"]
  ADAPTER --> OWN["Config ownership classifier\n(workspace-owned vs Studio-managed)"]
  ADAPTER --> ENV["Env clamp: AH_STATE_DIR / CCBD_STATE_DIR / XDG_STATE_HOME"]
  ADAPTER --> STATUS["ah status --json (bootstrap/fallback)"]
  ADAPTER --> EVENTS["ah events --format json (primary decision plane)"]
  ADAPTER --> IDCHECK["Snapshot identity check\n(config_path/state_dir match)"]
  ADAPTER --> CLOSE["ah stop / ah kill (Studio-managed configs only)"]
  STATUS --> AHD["ahd state contract"]
  EVENTS --> AHD
  CLOSE --> AHD
```

**Architecture Integration**:

- Selected pattern: external-contract adapter, with an explicit ownership boundary layer in front of it.
- Domain boundary: ah owns runtime lifecycle; Studio owns assistant registration, config generation, config ownership classification, UI projection, and user command orchestration.
- Existing patterns preserved: frontend consumes Tauri events and commands through `tauri.ts`.
- New component rationale: a typed runtime snapshot parser prevents string parsing drift; a config ownership classifier prevents lifecycle commands from ever reaching a config Studio did not create; an env clamp prevents inherited shell state from silently redirecting which ah instance Studio talks to.
- Steering compliance: single source of truth, explicit boundary, fail fast at external contract boundary.

### Technology Stack

| Layer | Choice / Version | Role in Feature | Notes |
|-------|------------------|-----------------|-------|
| Frontend | React / Tauri invoke | Display per-assistant Open/Attach/Close/Starting/Degraded/Error projection | No lifecycle inference |
| Native Shell | Rust Tauri | ah adapter, ownership classifier, env clamp, event emission | Main change area |
| Runtime | ah >= 1.4.0 | Lifecycle authority | External contract |
| Events | JSONL snapshots | Live status updates, primary decision plane | Complete snapshots, not deltas; ordered by `sequence` |

## System Flows

### One-shot open decision

```mermaid
sequenceDiagram
  participant UI
  participant Tauri
  participant AH as ah CLI
  UI->>Tauri: Open assistant
  Tauri->>Tauri: version gate (cached, includes events-subscription check)
  Tauri->>Tauri: classify config ownership (workspace-owned vs Studio-managed)
  Tauri->>AH: ah --config cfg status --json (bootstrap read; ignored if events snapshot already available)
  Tauri->>AH: ensure events subscription running for cfg
  Tauri->>Tauri: identity-check latest events snapshot against cfg
  alt runtime_state=active
    Tauri-->>UI: attach existing runtime
  else runtime_state=inactive, all sessions terminal
    Tauri->>AH: ah --config cfg start --wait (Studio-managed config only)
    Tauri-->>UI: starting event
  else runtime_state=starting
    Tauri-->>UI: starting projection, hands-off, no action taken
  else runtime_state=degraded
    Tauri->>AH: cleanup via sessions[].safe_to_cleanup/cleanup_required, then start
    Tauri-->>UI: cleanup-then-starting projection
  else status --json errored and no events snapshot yet (daemon-absent bootstrap gap)
    Tauri->>AH: wait for/start events subscription to get structured daemon_absent snapshot
    Tauri-->>UI: treat as inactive, not error
  else unsupported schema, failed identity check, or genuine command error
    Tauri-->>UI: actionable error
  end
```

### Live status subscription (primary decision plane)

```mermaid
sequenceDiagram
  participant AH as ah events
  participant Tauri
  participant UI
  AH-->>Tauri: complete JSON snapshot (with sequence)
  Tauri->>Tauri: parse, validate schema, identity-check config_path/state_dir
  Tauri->>Tauri: apply only if sequence > last-applied sequence
  Tauri->>Tauri: map runtime_state phase to per-assistant enum (Requirement 6.1)
  Tauri-->>UI: code-assistant-status-changed
```

### Close cleanup

```mermaid
sequenceDiagram
  participant UI
  participant Tauri
  participant AH as ah CLI
  UI->>Tauri: Close
  Tauri->>Tauri: confirm target config is Studio-managed (never workspace-owned)
  Tauri->>AH: ah --config cfg stop
  Tauri->>AH: ah --config cfg status --json / latest events snapshot
  alt still non-terminal per sessions[].cleanup_required
    Tauri->>AH: ah --config cfg kill --session <id-from-snapshot> --force
  end
  Tauri-->>UI: inactive snapshot
```

## Requirements Traceability

| Requirement | Summary | Components | Interfaces | Flows |
|-------------|---------|------------|------------|-------|
| 1.1-1.8 | ah version gate, single-sourced, covers events subscription | Studio ah adapter | `ah version`, `ah --version` | open, attach, cleanup, events subscription |
| 2.1-2.7 | events-primary status SSOT, status as bootstrap/fallback, sequence arbitration, identity check | Runtime snapshot parser | `status --json`, `events --format json` | status, live events |
| 3.1-3.8 | runtime_state phase + active-state UI semantics, incl. starting/degraded | Tauri event projection, Copilot panel | `code-assistant-status-changed` | open decision |
| 4.1-4.8 | cleanup safety, config ownership classification, env clamp, snapshot identity | Cleanup orchestrator, config ownership classifier, env clamp | `ah stop`, `ah kill` | close cleanup |
| 5.1-5.12 | tests | fixtures and unit tests | mocked/recorded ah CLI output | all flows |
| 6.1-6.3 | per-assistant status payload | Tauri event projection | `code-assistant-status-changed` | all flows |

## Components and Interfaces

### Tauri ah adapter

| Field | Detail |
|-------|--------|
| Intent | Execute ah commands and translate ah snapshots into Studio status events |
| Requirements | 1.1, 1.2, 1.5, 1.6, 1.7, 2.1, 2.2, 2.3, 4.1 |

**Responsibilities & Constraints**

- Run version gate (single-sourced constant, cached per session) before lifecycle commands and before spawning the events subscriber.
- Execute `ah --config <path> events --format json` as the primary decision-plane input; treat `ah --config <path> status --json` as a bootstrap/fallback read only.
- Never use `ah ps` text or tmux probing for normal lifecycle decisions.
- Clamp `AH_STATE_DIR`/`CCBD_STATE_DIR`/`XDG_STATE_HOME` on every ah invocation, including the Windows `wsl.exe -e bash -lc` login-shell path.

### Config ownership classifier

| Field | Detail |
|-------|--------|
| Intent | Classify a discovered ah config as workspace-owned (read-only) or Studio-managed (full lifecycle) before any command runs against it |
| Requirements | 4.6 |

**Responsibilities & Constraints**

- A config found by walking up from the workspace root (`find_ah_config`) is workspace-owned unless it is also the registered Studio temp config for that assistant.
- Workspace-owned configs are eligible only for `status`/`events`/observational `attach`; never for `start`/`stop`/`kill`.
- Studio-managed temp configs (Studio temp namespace) are eligible for full lifecycle commands.
- This classification runs before `ah_config_for_status`'s current preference order is applied, replacing "prefer whatever is found" with an explicit ownership gate.

### Runtime snapshot parser

| Field | Detail |
|-------|--------|
| Intent | Parse and validate ah v1.4.0+ runtime snapshots, and reject any snapshot that does not belong to the requested config |
| Requirements | 2.1, 2.2, 2.5, 2.6, 2.7, 3.1, 3.2, 3.5, 3.6, 3.7, 4.8 |

**State Management**

- State model (see Data Models below for exact field names, corrected per F8):
  - `schemaVersion`, `runtimeState`, `active`, `ahdAlive`, `reason`, `sequence`
  - `configPath` (nullable), `workspacePath`, `stateDir`
  - `sessions[]`, `agents[]`
- Invariants:
  - ah-provided `active` and `runtimeState` are authoritative once identity-checked.
  - Unknown schema is rejected.
  - Unknown status is displayed diagnostically and not silently treated as healthy.
  - A snapshot whose `configPath`/`stateDir` does not match the requested config is discarded, not applied (Requirement 2.7/4.8).
  - `sequence` is monotonic per config; an older-or-equal `sequence` value never overwrites a newer applied snapshot (Requirement 2.1/2.6).

### Cleanup orchestrator

| Field | Detail |
|-------|--------|
| Intent | Close Studio-managed ah runtimes without crossing ownership boundaries |
| Requirements | 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7 |

**Responsibilities & Constraints**

- Use `ah stop` as the normal close path, and only ever against a Studio-managed config (per the ownership classifier).
- Re-read the current snapshot (events-primary, `status --json` fallback) after stop.
- Escalate only with `ah kill --session <id> --force` for session ids from the selected config's latest identity-checked snapshot, and only where the snapshot marks that session `cleanup_required`/not `safe_to_cleanup`.
- Do not directly kill tmux sessions during normal cleanup.
- Ignore ahd stacks outside the Studio-managed temp config namespace, including a workspace-owned config found by directory walk-up.
- `degraded`-state cleanup (Requirement 3.7) runs only at the same four user-triggered timings as normal cleanup: Open prepare, Attach's CleanupStale branch, Close, app quit — never as a side effect of the passive events-snapshot handler.

## Data Models

### Normalized runtime snapshot

Field names below are corrected against the real 1.4.0/1.5.0 CLI output recorded in `operator-review-findings.md` F8, not against the README's illustrative example (research.md already flagged that the README example should not be hardcoded).

```typescript
type AhRuntimeSnapshot = {
  schemaVersion: number
  runtimeState: 'active' | 'inactive' | 'starting' | 'degraded'
  active: boolean
  ahdAlive: boolean
  reason?: string
  sequence: number
  configPath: string | null   // null observed when daemon started without a config
  workspacePath?: string
  stateDir?: string
  sessions: AhSessionSnapshot[]
  agents: AhAgentSnapshot[]
}

type AhSessionSnapshot = {
  sessionId: string
  status: string
  masterState?: string
  masterTmuxAlive?: boolean
  masterPaneId?: string
  liveAgents?: number         // real field name; NOT `activeAgents`
  dbTrackedAgents?: number
  safeToCleanup?: boolean     // ah's own cleanup-eligibility judgment; consume, do not re-derive
  cleanupRequired?: boolean
}

type AhAgentSnapshot = {
  agentId: string
  sessionId?: string
  provider?: string
  state: string
  tmuxAlive?: boolean
}
```

Changes from the prior draft, all sourced from F8's real-snapshot evidence:

- Added `ahdAlive` (top-level) — required by Requirement 3.3 and test 5.1; without it Studio cannot distinguish "ahd alive, active=false" from "ahd gone".
- Added `sequence` (top-level) — required by Requirement 2.1/2.6's arbitration rule (F5).
- `configPath` is now `string | null` — observed null when a daemon is started without a config.
- Renamed `activeAgents` to `liveAgents`, and added `dbTrackedAgents` — the real v2 snapshot does not have `activeAgents`.
- Added `safeToCleanup`/`cleanupRequired` on `AhSessionSnapshot` — ah already computes per-session cleanup eligibility; Requirement 4.2/3.7 consume these fields directly instead of Studio re-deriving "non-terminal therefore kill".

This TypeScript-like shape is descriptive. The implementation should use Rust types in the Tauri layer.

### Frontend event payload (per-assistant, replaces the two-boolean shape)

```typescript
type AssistantStatus = 'inactive' | 'starting' | 'active' | 'degraded' | 'error'

type CodeAssistantStatusChangedPayload = {
  claude: { status: AssistantStatus; reason?: string }
  codex: { status: AssistantStatus; reason?: string }
}
```

This replaces `{claude: bool, codex: bool}` outright (lib.rs:63-73) and removes the claude-wins suppression at lib.rs:1244-1246 (Requirement 6.1/6.2). This is a direct breaking change to the payload shape — no dual-format emission, no version-sniffing on the frontend — consistent with this repository's no-backward-compatibility rule.

## Error Handling

- Unsupported ah version: block start/attach/cleanup and events subscription; show update guidance.
- Unsupported schema: block lifecycle decision and show actual schema version.
- Invalid JSON: include command stderr in diagnostics and preserve last known UI state as stale/error.
- `status --json` non-zero exit with unstructured stderr and no events snapshot yet available: treat as an inconclusive bootstrap gap, not an error — attempt/await the events subscription's structured `daemon_absent` snapshot before deciding (Requirement 2.2/2.3).
- Snapshot identity mismatch (`configPath`/`stateDir` does not match requested config): discard the snapshot, surface a diagnostic, do not use it for any decision (Requirement 2.7/4.8).
- Workspace-owned config discovered where a Studio-managed config was expected: never issue lifecycle commands against it; surface it as read-only/observation-only (Requirement 4.6).
- ah command timeout: do not mutate UI to active or closed based on guesswork.
- Missing ah binary: use existing installer/provisioning path.

## Testing Strategy

- Unit Tests:
  - Parse v1.4.0+ active, inactive, starting, degraded, daemon-absent, `CLOSED`, and failed snapshots — sourced from recorded real CLI output, not the README example.
  - Reject unsupported schema.
  - Reject old ah version, including for the events subscription path.
  - Reject a snapshot with mismatched `configPath`/`stateDir`.
  - Sequence arbitration: an older-or-equal-sequence snapshot never overwrites a newer applied one.
- Integration Tests:
  - Open decision uses the events-primary/status-fallback plane, not `ah ps`.
  - `status --json` daemon-absent error does not get treated as authoritative when an events `daemon_absent` snapshot is available.
  - `starting` phase performs no cleanup/no duplicate start.
  - `degraded` phase exposes a working cleanup-then-open path driven by `sessions[].cleanup_required`/`safe_to_cleanup`.
  - Close escalates only to selected snapshot session ids marked non-terminal/`cleanup_required`.
  - Live events update the redesigned per-assistant frontend event payload, including simultaneous claude+codex active with no suppression.
  - Config ownership classifier routes lifecycle commands only to Studio-managed configs; a workspace-owned config (e.g. this repo's own root `ah.toml`) never receives `start`/`stop`/`kill`.
  - Env clamp prevents an inherited `AH_STATE_DIR`/`CCBD_STATE_DIR`/`XDG_STATE_HOME` from redirecting which ah instance a Windows `wsl.exe` invocation talks to.
- Regression Tests:
  - ahd alive but `active=false` maps to Open.
  - dead master pane plus stale tmux names does not map to Attach.
  - non-Studio default ahd is not cleaned by Studio exit.
  - `degraded` with `cleanup_required=true` maps to a working Open path, not a fully disabled button set.
  - `ah start` against an already-active stack behaves as verified by the pre-implementation check (Requirement 3.4/5.8), not as assumed.

## Supporting References

- [ah v1.4.0 release](https://github.com/SevenX77/ah/releases/tag/v1.4.0)
- [ah v1.4.0 CHANGELOG](https://raw.githubusercontent.com/SevenX77/ah/v1.4.0/CHANGELOG.md)
- [ah v1.4.0 README](https://raw.githubusercontent.com/SevenX77/ah/v1.4.0/README.md)
- `operator-review-findings.md` — F1-F8 real-CLI evidence (1.4.0 and 1.5.0), source of every field/behavior correction in this revision.
- `docs/studio/mvp1/03_regions/copilot/ah-orchestration-design.md` — design body to be updated in the same PR that implements this spec (see tasks.md design-writeback task, F7).
