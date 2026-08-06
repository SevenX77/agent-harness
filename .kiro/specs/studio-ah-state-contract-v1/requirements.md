---
spec: studio-ah-state-contract-v1
status: Draft (round 1 per operator-review-findings.md F1-F8; round 2 per d1-review.md NF1/NF2 + o1-review.md 坑洞 3.1-3.5, 2026-07-10)
target_goal: "Studio ah 状态检测、打开/附着、关闭清理统一到 ah v1.4.0+ 状态合约"
last_updated: 2026-07-10
revision_source: operator-review-findings.md; d1-review.md; o1-review.md
revision_trace: REVISION-TRACE.md
---

# Requirements Document

## Introduction

Studio 当前 ah 集成需要升级到 ah v1.4.0+ 的状态合约。目标是让 Open/Attach/Close、app 退出清理、状态按钮投影都只依赖 ah 暴露的结构化状态，而不是 Studio 自己解析 `ah ps`、探测 tmux、读取 sqlite 或猜测进程状态。

**第一轮修订**（operator-review-findings.md F1-F8）把三处结构性问题收进本文档：① 一次性 `status --json` 在 daemon 不存在时不返回结构化数据，实时决策必须以 `events` 流为主（F1/F5）；② `runtime_state` 有 `starting`/`degraded` 两个此前未覆盖的相位，`degraded` 必须有可用操作而不是把三个按钮全部锁死（F2）；③ 所有权与身份边界必须显式覆盖 workspace 自带 config、`AH_STATE_DIR` 类环境变量劫持、以及快照身份校验（F4）。

**第二轮修订**（2026-07-10，d1-review.md 实测发现 NF1/NF2 + o1-review.md 对抗审坑洞 3.1/3.2/3.3/3.4/3.5，均经本轮独立 1.5.0 只读实测核实）在此基础上把几处被实测证伪/证不足的承重条款收紧：身份校验以 session 身份为权威（修订 2026-08-05 D-D1：`state_dir` 亦降为诊断）、`config_path` 降级为诊断且路径比对跨平台归一（Req 2.7/4.8）；env clamp 改为 in-string export 并明确它**不**保证 1.5.0 读面 daemon 隔离、承重责任移交身份校验（Req 4.7/4.7a）；`sequence` 仲裁限定在单订阅流/`session_id` 生命周期内、`reason:"initial"` 无条件重置（Req 2.1）；payload 增 `readOnly` 标志、只读 assistant 的 Close 语义改为 Detach（Req 6.1/6.4）；版本探测简化为单一 `ah version`（Req 1.8）。逐条改动位置见 `REVISION-TRACE.md`。

## Requirements

### Requirement 1: ah version gate

**Objective:** As a Studio user, I want Studio to require a supported ah state contract, so that CLI 状态和 UI 状态不会因为旧版本能力缺失而漂移。

#### Acceptance Criteria

1.1 When Studio 检测 ah 可执行文件版本, the Studio ah integration shall reject versions lower than `1.4.0` with an actionable diagnostic.

1.2 When ah version output cannot be parsed, the Studio ah integration shall fail fast before starting, attaching, or cleaning up a runtime.

1.3 The Studio ah integration shall document `ah >= 1.4.0` as the minimum supported runtime for Studio-managed assistants.

1.4 If ah is missing, then the Studio ah integration shall keep the assistant closed and surface the existing installer/provisioning path instead of attempting lifecycle commands.

1.5 The Studio ah integration shall define the minimum-version constant in exactly one place in the Rust adapter layer; the launcher shell script templates (currently four separately embedded `awk`-based `>= 1.3.4` checks) shall reference that single value instead of hardcoding their own threshold, and shall be unified onto the single version command and parse rule of Requirement 1.8. *(F6 — lib.rs:1754/1836/1903/1960 are four independent copies of the same version gate.)*

1.6 The version gate shall also cover the `ah events --format json` subscription: Studio shall not spawn an events reader against an ah binary below `1.4.0`. *(F6 — pre-1.4.0 ah has no `events` subcommand; an unguarded subscription loop respawns the failing process every ~3 seconds, per current lib.rs:1355 behavior.)*

1.7 The Studio ah integration shall cache the version-check result for the lifetime of the app session rather than re-invoking `ah version` before every lifecycle command. *(F6 — on Windows every ah invocation is a `wsl.exe` round-trip.)*

1.8 The Studio ah integration shall detect the ah version by invoking `ah version` (which prints a bare version string, e.g. `1.5.0`) and trimming it — a single command and a single `trim` parse used everywhere, including the four launcher shell templates of Requirement 1.5. It shall NOT additionally parse `ah --version` (which prints `ah 1.5.0` and needs second-token extraction) or maintain two parse formats. *(F6 + o1 质疑 2.3, re-verified 2026-07-10 on 1.5.0: `ah version` returns a bare version on every release at or above the `1.4.0` floor this spec requires, so dual-format parsing is unnecessary complexity — one command, one parse, per KISS/DRY in AGENTS.md. The current launcher templates use `ah --version | awk '{print $2}'`; Requirement 1.5's single-sourcing shall standardize them onto `ah version` too so there is exactly one version-detection rule in the codebase.)*

### Requirement 2: Runtime status source of truth and read-plane arbitration

**Objective:** As a Studio maintainer, I want one authoritative decision surface across the two ah read paths, so that 状态转换有唯一来源，即使某一路径在特定状态下输出不完整。

#### Acceptance Criteria

2.1 The Studio ah integration shall treat `ah --config <path> events --format json` as the primary and default decision surface for open/attach/close/cleanup logic whenever a live subscription for that config is available, applying snapshots in `sequence` order **scoped to a single subscription stream / `session_id` lifetime**: an older-or-equal `sequence` shall not overwrite a newer applied snapshot **only while the stream identity is unchanged**. `sequence` is a per-stream baseline counter, NOT a globally monotonic value: it resets to `1` with `reason:"initial"` on every fresh subscription, every one-shot `status --json` read, and every daemon restart. Studio shall therefore **unconditionally reset** its applied-`sequence` cache — never gating the incoming snapshot on the old value — whenever it observes any of: a newly (re)established events subscription, a snapshot carrying `reason:"initial"`, or a changed `sessions[].session_id`; the monotonic `sequence` guard applies only *after* such a reset, within that stream. *(F5 + o1 坑洞 3.2 — verified 2026-07-10 on 1.5.0: `ah status --json` returns `sequence:1, reason:"initial"` on every call, and the `events` stream's first frame is likewise `sequence:1, reason:"initial"`. A naive global `resourceVersion`-style max would let a stale high `sequence` from a prior stream permanently drop the post-close or post-restart snapshot — the K8s analogy is unsafe here precisely because `sequence` is not monotonic across streams/daemon lifetimes.)*

2.2 When Studio needs a one-shot read and no live events subscription is yet established for that config (e.g. first paint before the subscriber attaches), the Studio ah integration may call `ah --config <path> status --json`, but shall not treat a non-zero exit code or unstructured stderr from that call as an authoritative "no runtime" or "error" signal. *(F1 — verified on 1.4.0 and 1.5.0: with no daemon present, `ah status --json` exits 1 with human-readable stderr `"ahd daemon is not running at ..."` and emits no JSON at all, while `ah events --format json` in the identical situation emits a structured snapshot `{"reason":"daemon_absent","runtime_state":"inactive","ahd_alive":false,...}`. Studio must not sniff that stderr text — doing so re-creates the exact `ah ps` text-parsing problem this spec removes.)*

2.3 When `status --json` fails with a non-structured error and no events subscription result is yet available, the Studio ah integration shall start (or wait for) an events subscription to obtain the structured `daemon_absent` snapshot before making an open/attach/close decision, rather than surfacing the raw CLI error as if it were a decision-grade signal. The wait shall be bounded by a single named timeout constant (default 3 seconds); if no structured snapshot arrives within it, Studio shall fall back to an inconclusive `inactive`-and-startable projection (never an `error` state), and shall still not surface the raw CLI stderr as a decision-grade signal. *(F1 + d1-review A-4 — "briefly" is quantified to a deterministic timeout with a defined fallback state so this criterion is testable; closes the open/close gaps identified: open flow on first launch and close-flow re-check after `ah stop` both hit exactly this daemon-absent case.)*

2.4 The Studio ah integration shall not parse `ah ps` text, inspect tmux sessions, read ah sqlite, or infer liveness from process names for normal status decisions.

2.5 If a runtime snapshot schema version is unsupported, then the Studio ah integration shall surface a clear unsupported-contract error and shall not fall back to local probing.

2.6 The Studio ah integration shall treat ah snapshot fields as read-through replicas of ahd-owned truth, not as Studio-owned truth.

2.7 The Studio ah integration shall validate that a received snapshot belongs to the config Studio actually requested, using the snapshot's **session identity (`sessions[].session_id`, `sessions[].path`, `sessions[].project_id`) as the authoritative identity fields**（修订 2026-08-05，决议 D-D1：requester 侧判定锚只有 session 身份——`state_dir` 是 ah 内部从 config 路径派生的 hash，请求方无法独立形成期望值，不能充当校验条件；降为 advisory 诊断，与 `config_path` 同级。见 `decision-2026-08-05-identity-anchor-and-tmux-server-alive.md`）, and shall reject (not display as authoritative) any snapshot whose identity does not match. `config_path` shall NOT serve as an authoritative identity field, for two verified reasons (2026-07-10, 1.5.0): (a) it is `null` on a daemon started without an explicit config — the real live snapshot was observed with top-level `config_path:null` — so it often cannot match anything; and (b) `ah --config <X> events` echoes the *requested* path `X` straight back into `config_path` while returning a different daemon's real `state_dir`/`sessions`, so a `config_path` match has zero discriminating power (NF1). `config_path` may be kept only as an advisory diagnostic string. All path comparisons (`state_dir`, `sessions[].path`) shall be canonicalized across the Windows↔WSL boundary — never raw string equality — because Studio may run on a Windows host requesting a `C:\...` path while the WSL-side ah returns a `/mnt/c/...` (or `/root/...`) path; the platform-neutral `sessions[].project_id` (derived from the directory basename, e.g. `feat-studio-ah-state-contract-impl`) is the most robust cross-host anchor. Studio shall independently derive the expected identity for the config it requested rather than trusting the snapshot's echoed `config_path`. *(F4b + NF1 + o1 坑洞 3.1 — this is the enforcement mechanism that gives Requirement 2.6 teeth once `AH_STATE_DIR`-style env resolution can silently redirect a request; see Requirement 4.7/4.8.)*

### Requirement 3: Runtime state phase and active-state semantics

**Objective:** As a Studio user, I want the Open/Attach/Close projection to reflect ah's full `runtime_state` phase set — not just an `active` boolean — so that I never end up with a runtime in a state where no action is available, and so that I do not attach to dead panes or start duplicate stacks.

#### Acceptance Criteria

3.1 When snapshot `active` is true for the selected assistant config, the Studio UI shall expose Attach and Close actions.

3.2 When snapshot `active` is false and all relevant sessions are terminal such as `CLOSED`, `FAILED`, or `KILLED`, the Studio UI shall expose Open action.

3.3 When ahd is alive but snapshot `active` is false, the Studio UI shall treat this as inactive rather than as a cleanup failure.

3.4 If another active stack exists for the same assistant config, then the Studio ah integration shall attach to that stack or reject with a conflict based on the ah snapshot rather than starting a duplicate session. This behavior depends on the unverified assumption that `ah start` rejects a start against an already-active stack for the same config; that assumption shall be verified against a real ah CLI before this criterion is implemented (tracked as a pre-implementation verification task in tasks.md). *(F8 — "Req 3.4 防重复启动依赖‘ah start 对已活跃 stack 拒绝’这一未验证假设".)*

3.5 If master tmux or worker tmux is unhealthy in the ah snapshot, then the Studio ah integration shall not override `active=false` using local tmux names or historical session ids.

3.6 When `runtime_state` is `starting`, the Studio ah integration shall treat the runtime as hands-off: it shall not run cleanup, shall not start a duplicate runtime, and shall not report an error; the Studio UI shall display a distinct "starting" state and keep Open/Attach/Close disabled until `runtime_state` transitions away from `starting`. *(F2 — ah 1.3.4 CHANGELOG states verbatim: "Consumers such as Studio should clean up only `degraded` runtimes; `starting` means startup is still in progress and must be left alone." The spec previously named neither `starting` nor `degraded`.)*

3.7 When `runtime_state` is `degraded`, the Studio UI shall expose an Open action that first runs cleanup driven by the snapshot's own cleanup-eligibility fields (`sessions[].cleanup_required` / `sessions[].safe_to_cleanup`, see Requirement 2.6/4.2) and then starts a fresh runtime — degraded shall never leave the user with zero available actions. Any `degraded`-state cleanup shall still only run at the existing user-triggered timing (Open prepare, Attach's CleanupStale branch, Close, app quit) and never as a side effect of the passive events-snapshot handler, consistent with the existing 2026-07-06 diagnostic in `docs/studio/mvp1/03_regions/copilot/ah-orchestration-design.md` about not auto-cleaning on cold-start snapshot shapes. *(F2 — real snapshot observed: `active:false, runtime_state:"degraded"`, one session `status:"ACTIVE"` with `live_agents=10`, dead master tmux, `cleanup_required:true`; under the prior wording of Req 3.1/3.2 all three buttons go dark and the user is stuck — the exact bug this spec exists to fix. The current Tauri `CleanupStale` path, lib.rs:357-368 and lib.rs:2358-2361, already self-heals this case today; implementing the prior spec text literally would be a functional regression.)*

3.8 The Studio ah integration shall derive Open/Attach/Close availability from `runtime_state` phase plus `active`/session-terminal fields together (per 3.1-3.3, 3.6, 3.7), not from a Studio-invented reduction of `runtime_state` back down to a single boolean.

### Requirement 4: Cleanup and ownership safety

**Objective:** As a Studio user, I want Close and app quit cleanup to be safe, so that Studio never kills unrelated ah stacks — including the operator's own ah-orchestrated agent fleet running in this very repository, or a stack whose state directory was silently redirected by an inherited environment variable.

#### Acceptance Criteria

4.1 When the user closes an assistant runtime, the Studio ah integration shall delegate shutdown to ah using the selected config.

4.2 If a runtime remains non-terminal after normal close, then the Studio ah integration shall target only session ids present in the selected config's latest snapshot, and shall prefer the snapshot's own `sessions[].safe_to_cleanup` / `cleanup_required` fields over Studio re-deriving "non-terminal therefore kill" itself. *(F8 — ah already computes per-session cleanup eligibility; re-deriving it in Studio duplicates a judgment ah already owns and can drift from it.)*

4.3 The Studio ah integration shall not directly kill tmux sessions during normal cleanup.

4.4 When Studio exits, the Studio ah integration shall clean only Studio-managed temp configs registered during the app lifetime or discoverable under the Studio temp namespace (`%TEMP%\skill-studio-ah` or platform equivalent).

4.5 If a non-Studio ahd service exists outside Studio-managed configs, then the Studio ah integration shall leave it untouched.

4.6 The Studio ah integration shall classify every ah config it discovers into exactly two ownership classes before taking any lifecycle action: (a) **workspace-owned config** — an `ah.toml` discovered by walking up from the workspace root (`find_ah_config`, lib.rs:203-218), which may belong to a human- or operator-managed ah session already running in that tree; or (b) **Studio-managed temp config** — a config Studio itself generated under the Studio temp namespace. Only class (b) is eligible for lifecycle commands (`start`/`stop`/`kill`); class (a) is eligible only for read-only operations (`status`, `events`, Attach for observation). *(F4a — this repository itself has an `ah.toml` at its root since PR #478; opening Studio anywhere under this tree today lets `find_ah_config` walk up to it and lets Close/quit run `ah stop` + force-kill against the operator's own agent fleet. `ah_config_for_status`, lib.rs:828-833, currently prefers the workspace-owned config over the Studio temp config with no ownership distinction at all.)*

4.7 Before invoking ah through the Windows `wsl.exe -e bash -lc` login-shell path (the ah call sites at lib.rs:858 `run_ah_config_command_output` and lib.rs:879 `spawn_ah_events_command` — note lib.rs:927 is a tmux socket call, not an ah call, though the same login-shell inheritance applies to it), the Studio ah integration shall clamp `AH_STATE_DIR`, `CCBD_STATE_DIR`, and `XDG_STATE_HOME` by **injecting the clamp into the bash `-c` command string itself** (e.g. prefixing `export AH_STATE_DIR=""; export CCBD_STATE_DIR=""; export XDG_STATE_HOME="<pinned>";`), NOT merely through the Rust `Command::env(...)` builder. *(F4b + o1 坑洞 3.5 — verified 2026-07-10: a login shell sources the user's profile AFTER inheriting the process environment, so `export AH_STATE_DIR=...` in `~/.profile`/`~/.bashrc` overrides any value set via `Command::env` (`HOME=<fixture> AH_STATE_DIR=/inherited bash -lc 'echo $AH_STATE_DIR'` printed the profile's value); only an export inside the executed command string — which runs after profile sourcing — reliably wins.)*

4.7a **Scope limit of the clamp (verified, load-bearing).** Requirement 4.7's clamp does NOT guarantee which ah daemon the read plane talks to. On ah 1.5.0, `ah status`/`ah events` ignore `AH_STATE_DIR`/`--config` and resolve to the currently-running daemon through a global mechanism regardless of the clamp — setting `AH_STATE_DIR` to a fresh empty directory still returned the live fleet's `state_dir`. Req 4.7's guarantee is therefore limited to preventing an inherited state dir from cross-contaminating the state directories Studio *itself writes*; it must not be relied on for read-plane daemon selection. The load-bearing control that keeps Studio from ever trusting another daemon's snapshot as its own is the snapshot identity check (Requirement 2.7/4.8), not this clamp. *(NF2 — verified 2026-07-10 on 1.5.0; supersedes any earlier assumption that "clamp ⇒ isolation" on the read plane.)*

4.8 Every snapshot Studio receives shall be identity-checked per Requirement 2.7 (authoritative on session identity; `state_dir` and `config_path` demoted to advisory — 修订 2026-08-05 D-D1, all path comparison canonicalized across the Windows↔WSL boundary) before it is used for any decision, including cleanup targeting. A snapshot that fails identity validation shall be discarded with a diagnostic, not silently applied. *(F4b + NF1 — this is the concrete safety mechanism cleanup must depend on, and per Requirement 4.7a it is the load-bearing read-plane isolation control, not env clamp; also corroborated by 2026-07-10 evidence on ah 1.5.0: in the same cwd containing an `ah.toml`, with no explicit `--config`, `ah status`/`ah ps` resolve against the default state dir while `ah events` resolves via project discovery — the two read paths can legitimately disagree about which state dir they are even talking about, making explicit identity validation mandatory rather than a defensive nicety.)*

### Requirement 5: Tests and regression coverage

**Objective:** As a maintainer, I want reproducible coverage for the broken states, so that future ah upgrades do not reintroduce drift.

#### Acceptance Criteria

5.1 When a fixture contains ahd alive, `active=false`, and terminal sessions, the tests shall verify the UI maps to Open.

5.2 When a fixture contains a dead master pane but stale tmux session names, the tests shall verify Studio does not report active.

5.3 When a fixture uses schema v2 with `CLOSED`, the tests shall verify close/open transitions.

5.4 When ah version is below `1.4.0`, the tests shall verify Studio blocks integration with a clear error, including blocking the events subscription (Requirement 1.6).

5.5 When cleanup is requested for a snapshot containing multiple sessions, the tests shall verify escalation targets only selected-config session ids, driven by `sessions[].safe_to_cleanup`/`cleanup_required` (Requirement 4.2).

5.6 When a fixture has `runtime_state="starting"`, the tests shall verify Studio performs no cleanup, starts no duplicate runtime, and the UI shows a starting state rather than an error or a stale/degraded projection. *(F2)*

5.7 When a fixture has `runtime_state="degraded"` with `cleanup_required=true` on at least one session, the tests shall verify the UI exposes a working Open path (cleanup-then-start), not a fully disabled button set. *(F2)*

5.8 Before implementing Requirement 3.4 (duplicate-stack conflict), a pre-implementation verification step shall run `ah start` against a config with an already-active stack on a real installed ah binary and record the actual exit code / stderr / snapshot shape, and the fixture set shall be built from that recorded evidence rather than from an assumption. *(F8)*

5.9 When Studio discovers a workspace-owned config (Requirement 4.6 class a) versus a Studio temp config (class b) in the same fixture set, the tests shall verify lifecycle commands (`start`/`stop`/`kill`) are only ever issued against class (b), and that class (a) only ever receives read-only commands. *(F4a)*

5.10 The tests shall verify snapshot identity validation per Requirement 2.7/4.8: (a) a snapshot whose `config_path` **matches** the requested path but whose session identity does **not** match is discarded with a diagnostic and used for no UI or cleanup decision (the NF1 failure form — a `config_path`-only check would wrongly accept it); and (b) a Windows-host request (`C:\...`) against a WSL-side snapshot (`/mnt/c/...`) with the same canonical target is accepted after cross-platform path canonicalization, i.e. raw string comparison is not used. *(F4b + NF1 + o1 坑洞 3.1)*

5.11 When `ah status --json` fails with a non-zero exit and unstructured stderr while an events subscription for the same config yields a structured `daemon_absent` snapshot, the tests shall verify Studio's decision follows the events snapshot, not the status error text. *(F1)*

5.12 The tests shall verify the redesigned per-assistant status payload (Requirement 6) reports each of Claude and Codex independently — including both active simultaneously — with no claude-wins suppression of the other assistant's real state, and carries the per-assistant `readOnly` ownership flag (Requirement 6.1). *(F3 + o1 坑洞 3.3)*

5.13 The tests shall verify sequence-arbitration scope (Requirement 2.1): after the events stream has advanced to `sequence > 1`, a subsequent snapshot carrying `reason:"initial"`/`sequence:1` (a fresh subscription, a one-shot `status --json`, or a post-restart stream — including one with a changed `sessions[].session_id`) is applied via an unconditional reset, NOT dropped by the older-or-equal guard; and that within an unchanged stream a genuinely older `sequence` is still dropped. *(F5 + o1 坑洞 3.2)*

5.14 The tests shall verify read-only assistant control semantics (Requirement 6.4): for a workspace-owned (read-only) assistant that is `active`, the Close control resolves to Detach and emits no `ah stop`/`ah kill`; for one that is `inactive`, the Open control is disabled with guidance text and issues no lifecycle command. *(o1 坑洞 3.3/3.4)*

### Requirement 6: Frontend status payload expressiveness

**Objective:** As a Studio frontend developer, I want the Tauri-to-UI status event to carry enough information per assistant, so that the UI can display starting/degraded/error states truthfully instead of being squeezed into a two-boolean shape that cannot represent them.

#### Acceptance Criteria

6.1 The `code-assistant-status-changed` payload shall represent status per assistant (Claude, Codex) as an explicit state enum — at minimum `inactive`, `starting`, `active`, `degraded`, `error` — plus an optional `reason`/diagnostic string **and a `readOnly: boolean` ownership flag** (true for a workspace-owned config, false for a Studio-managed temp config, per Requirement 4.6), replacing the current `{claude: bool, codex: bool}` shape (lib.rs:63-73). The frontend requires `readOnly` in the payload so it can present controls that never trigger a lifecycle command the backend will reject (Requirement 6.4). This is a breaking payload change made directly, per this repository's no-backward-compatibility rule; there is no dual-format reader and no version-sniffing branch. *(F3 + o1 坑洞 3.3)*

6.2 The Studio ah integration shall remove the existing claude-wins suppression (`if status.claude { status.codex = false; }`, lib.rs:1244-1246) and report each assistant's real, independently-derived state. The frontend already supports both assistants active at once (`copilot-panel.tsx:303-306`, "Close assistants" plural branch); the backend payload shall stop lying to it. *(F3)*

6.3 The Studio ah integration shall retain the existing product invariant that a given workspace has at most one Studio-managed ahd at a time (`ah-orchestration-design.md:12`): Requirement 6.1's richer per-assistant enum changes how truthfully Studio *displays* Claude/Codex state, not whether it *starts* a second concurrent ahd for the same workspace. Opening a second assistant while one is already active continues to attach-or-reject per Requirement 3.4, not spawn a second ahd. *(F3 — this is the explicit answer the finding required; allowing genuinely concurrent per-workspace ahd instances would be a materially larger change than this spec's scope and is out of scope here.)*

6.4 The Studio UI shall map a read-only (workspace-owned, Requirement 4.6 class a) assistant's controls so that no rendered control triggers a lifecycle command the backend will reject: when such an assistant is `active` (attached for observation), the Close control shall be presented as **Detach** — closing only the local terminal/observation tab and unloading Studio's UI state, and never sending `ah stop`/`ah kill`; when it is `inactive`, the Open control shall be disabled with guidance text (e.g. "This config is provided by the workspace and is read-only — start it from a terminal with `ah start`"). A Studio-managed (class b) assistant retains the normal Open/Attach/Close controls. This depends on the `readOnly` flag carried by Requirement 6.1's payload. *(o1 坑洞 3.3/3.4 — without this, a read-only active assistant's Close is a no-op that the events stream immediately re-renders as `active` — an inescapable UI deadlock — and a read-only inactive Open renders a clickable button that always errors. Because Requirement 4.7a establishes that env clamp does not isolate the read plane, the read-only ownership boundary is load-bearing safety and cannot be removed; these control semantics live inside that boundary rather than relaxing it.)*
