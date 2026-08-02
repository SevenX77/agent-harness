//! ah v1.4.0+ state-contract test fixtures (studio-ah-state-contract-v1, task 1).
//!
//! These fixtures are the frozen inputs for the RED tests that tasks 2–9 add to
//! `lib.rs`'s `#[cfg(test)] mod tests`. They are raw ah CLI output shapes
//! (schema_version:2, **snake_case** — the typed parser of task 3 maps
//! snake→camel; the CLI emits snake_case, see task0 evidence 附加A note) plus the
//! small descriptor metadata a fixture needs (expected version strings, config
//! ownership class, expected identity verdict). This module deliberately builds
//! NO production types and NO parser — task 3 owns those; here we only stage data.
//!
//! ## Provenance discipline (read before trusting a fixture)
//!
//! Every snapshot/identity fixture carries a [`Provenance`] tag. Task 0 could not
//! safely reproduce every phase on the capture machine (a shared WSL + systemd-user
//! host with a live fleet — see `task0-cli-evidence-2026-07-10.md` §1 and §7), so
//! not everything here is a verbatim capture. The three tiers are:
//!
//! - [`Provenance::Captured`] — verbatim real `ah` output recorded in task 0
//!   (`active` §附加A, `daemon_absent` §2b, the NF1 echo snapshot §4, the
//!   sequence/reason progression §6b, the bare `ah version` string §附加B).
//! - [`Provenance::SpecTranscribed`] — transcribed from a shape the spec itself
//!   recorded (`degraded`, from requirements Req 3.7 / task0 §7), **not**
//!   independently re-captured on this machine. Do not present as "measured".
//! - [`Provenance::SchemaDerived`] — constructed from the real schema_version:2
//!   field set (task0 §附加A) by adjusting state fields; no capture exists for the
//!   phase (`starting`, terminal `CLOSED`/`FAILED`, `inactive`-with-ahd-alive,
//!   `unsupported schema`, the Windows↔WSL identity pair, the codex second stack).
//!   Load-bearing decision fields (session `status`, `active`, `runtime_state`,
//!   `cleanup_required`/`safe_to_cleanup`) use the real vocabulary from the spec /
//!   Req 3.2/3.7; genuinely-uncaptured secondary fields (terminal `master_state`,
//!   `master_last_exit_reason` vocabulary) are set to `null` rather than invented.
//!
//! Field names are anchored to task0 §附加A's confirmed schema_version:2 field
//! list — top-level `schema_version/event/sequence/reason/runtime_state/active/
//! ahd_alive/ahd_has_inventory/config_path(nullable)/workspace_path(nullable)/
//! state_dir/tmux_socket(nullable)/tmux_server_alive/master_tmux_alive/
//! worker_tmux_alive/worker_tmux_expected_count`; `sessions[]`: `session_id/
//! project_id/path/status/master_state/master_tmux_session/master_tmux_alive/
//! master_pane_id/master_pid/master_last_exit_reason/db_tracked_agents/
//! live_agents/cleanup_required/safe_to_cleanup`; `agents[]`: `agent_id/provider/
//! state/sub_state/tmux_alive/tmux_session/session_id/pid`; daemon-absent frames
//! also carry `job_event_cursor`.

/// Where a fixture's shape came from — see the module docs for the taxonomy.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum Provenance {
    /// Verbatim real `ah` CLI output recorded in task 0.
    Captured,
    /// Transcribed from a shape recorded in the spec (Req 3.7), NOT independently
    /// re-captured on the task-0 machine (see task0 §7). Never label as measured.
    SpecTranscribed,
    /// Constructed from the real schema_version:2 field set by adjusting state
    /// fields; no capture exists for this phase on the task-0 machine.
    SchemaDerived,
}

// ───────────────────────────── Version fixtures (Req 1.1, 1.2, 1.8) ─────────────
//
// Req 1.8 (re-verified 2026-07-10 on 1.5.0, task0 §附加B): the version gate reads
// a SINGLE `ah version` command, which prints a BARE version string plus a newline
// (`1.5.0\n`), and trims it — there is no `ah --version` ("ah 1.5.0") second-token
// parse path. These fixtures therefore only model the bare-version format, and
// deliberately keep the trailing newline so the trim is exercised.

/// `ah version` bare output for a supported runtime. CAPTURED — task0 §附加B
/// recorded `ah version` → `1.5.0` (bare + newline) on the only installed binary.
pub(crate) const AH_VERSION_SUPPORTED: &str = "1.5.0\n";

/// `ah version` bare output at exactly the supported floor (Req 1.1: reject `< 1.4.0`).
/// SchemaDerived boundary input — the floor value chosen by the spec, formatted like
/// the real bare-version output.
pub(crate) const AH_VERSION_MIN_SUPPORTED: &str = "1.4.0\n";

/// `ah version` bare output below the floor (Req 1.1 reject). This is the old
/// threshold the launcher templates currently hardcode (`1.3.4`), now unsupported.
/// SchemaDerived boundary input (task 0 had no `< 1.4.0` binary to capture, §头部).
pub(crate) const AH_VERSION_UNSUPPORTED: &str = "1.3.4\n";

/// `ah version` output that cannot be parsed as a version → fail fast (Req 1.2).
/// SchemaDerived boundary input.
pub(crate) const AH_VERSION_UNPARSABLE: &str = "not-a-version\n";

// ───────────────────────────── Snapshot fixtures (bullet 1) ─────────────────────
//
// Single-line JSON on purpose: `ah events --format json` is JSONL (one complete
// snapshot per line) and task 4 parses "每一行" as a full snapshot, so a fixture
// must survive line-splitting. `status --json` consumers can read the same strings.

/// `active` — CAPTURED verbatim from task0 §附加A (live fleet; jobs/job_events were
/// trimmed as noise in the doc, restored here as empty for schema completeness).
/// The six agents span providers `claude` (d1/g1/g2) and `antigravity`
/// (g1-m1/g2-m1/o1); note the real dev fleet has no `codex` provider — see
/// [`SNAPSHOT_ACTIVE_CODEX`] for the per-assistant dual-active pairing (Req 5.12).
pub(crate) const SNAPSHOT_ACTIVE: &str = r#"{"schema_version":2,"event":"snapshot","sequence":1,"reason":"initial","runtime_state":"active","active":true,"ahd_alive":true,"ahd_has_inventory":true,"config_path":null,"workspace_path":null,"state_dir":"/root/.local/state/ah/f2647adf","tmux_socket":"ahd-5a709091c406a3fa","tmux_server_alive":true,"master_tmux_alive":true,"worker_tmux_alive":true,"worker_tmux_expected_count":6,"agents":[{"agent_id":"d1","provider":"claude","state":"IDLE","sub_state":"LogEvent","tmux_alive":true,"tmux_session":"agent_d1","session_id":"sess_6ddea78e-0ea9-4f00-9b9a-15226e3cce28","pid":901582},{"agent_id":"g1","provider":"claude","state":"BUSY","sub_state":"Matched","tmux_alive":true,"tmux_session":"agent_g1","session_id":"sess_6ddea78e-0ea9-4f00-9b9a-15226e3cce28","pid":901703},{"agent_id":"g1-m1","provider":"antigravity","state":"IDLE","sub_state":"Matched","tmux_alive":true,"tmux_session":"agent_g1-m1","session_id":"sess_6ddea78e-0ea9-4f00-9b9a-15226e3cce28","pid":901787},{"agent_id":"g2","provider":"claude","state":"IDLE","sub_state":"Matched","tmux_alive":true,"tmux_session":"agent_g2","session_id":"sess_6ddea78e-0ea9-4f00-9b9a-15226e3cce28","pid":901859},{"agent_id":"g2-m1","provider":"antigravity","state":"IDLE","sub_state":"Matched","tmux_alive":true,"tmux_session":"agent_g2-m1","session_id":"sess_6ddea78e-0ea9-4f00-9b9a-15226e3cce28","pid":901922},{"agent_id":"o1","provider":"antigravity","state":"WAITING_FOR_ACK","sub_state":"Matched","tmux_alive":true,"tmux_session":"agent_o1","session_id":"sess_6ddea78e-0ea9-4f00-9b9a-15226e3cce28","pid":903125}],"sessions":[{"session_id":"sess_6ddea78e-0ea9-4f00-9b9a-15226e3cce28","project_id":"feat-studio-ah-state-contract-impl","path":"/root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl","status":"ACTIVE","master_state":"BUSY","master_tmux_session":"master_feat-studio-ah-state-contract-impl","master_tmux_alive":true,"master_pane_id":"%0","master_pid":187349,"master_last_exit_reason":null,"db_tracked_agents":6,"live_agents":6,"cleanup_required":false,"safe_to_cleanup":false}],"jobs":[],"job_events":[],"job_event_cursor":0}"#;

/// `daemon_absent` — CAPTURED verbatim from task0 §2b (via a private mount-ns that
/// masked the state root; `config_path`/`state_dir` are the registry-residual values
/// the real CLI still emitted — a consumer may neutralize them to the requested
/// path, but the decision fields `reason:"daemon_absent"`/`runtime_state:"inactive"`/
/// `ahd_alive:false`/`active:false`/`sessions:[]`/`agents:[]` are faithful). This is
/// the structured shape `ah events` gives while `ah status --json` only exits 1 with
/// human-readable stderr (Req 2.2/2.3/5.11) — Studio must decide off THIS, not stderr.
pub(crate) const SNAPSHOT_DAEMON_ABSENT: &str = r#"{"schema_version":2,"event":"snapshot","sequence":1,"reason":"daemon_absent","runtime_state":"inactive","config_path":"/root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/ah.toml","workspace_path":"/root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl","state_dir":"/root/.local/state/ah/f2647adf","tmux_socket":null,"ahd_alive":false,"active":false,"ahd_has_inventory":false,"tmux_server_alive":false,"master_tmux_alive":false,"worker_tmux_alive":false,"worker_tmux_expected_count":0,"sessions":[],"agents":[],"jobs":[],"job_events":[],"job_event_cursor":0}"#;

/// `inactive` with ahd alive — SchemaDerived from §附加A. ahd is running but no active
/// stack (`active:false`, `runtime_state:"inactive"`, no sessions). Req 3.3/5.1: this
/// is inactive-and-startable, NOT a cleanup failure. Distinct from `daemon_absent`
/// (which has `ahd_alive:false`).
pub(crate) const SNAPSHOT_INACTIVE: &str = r#"{"schema_version":2,"event":"snapshot","sequence":1,"reason":"initial","runtime_state":"inactive","active":false,"ahd_alive":true,"ahd_has_inventory":true,"config_path":null,"workspace_path":null,"state_dir":"/root/.local/state/ah/f2647adf","tmux_socket":null,"tmux_server_alive":true,"master_tmux_alive":false,"worker_tmux_alive":false,"worker_tmux_expected_count":0,"agents":[],"sessions":[],"jobs":[],"job_events":[],"job_event_cursor":0}"#;

/// `starting` — SchemaDerived. NO capture and NO spec-recorded shape exists for this
/// phase (task0 §7: `ah start` could not be safely run on the capture machine), so
/// the whole snapshot is constructed from the schema_version:2 field model. The only
/// load-bearing facts are `runtime_state:"starting"` (Req 3.6 hands-off) and the
/// session's `safe_to_cleanup:false`/`cleanup_required:false` (nothing to clean, must
/// be left alone); secondary fields (`master_state`, exit reason) are `null` rather
/// than invented. Session `status:"STARTING"` is a plausible startup label, not a
/// captured enum value.
pub(crate) const SNAPSHOT_STARTING: &str = r#"{"schema_version":2,"event":"snapshot","sequence":1,"reason":"initial","runtime_state":"starting","active":false,"ahd_alive":true,"ahd_has_inventory":true,"config_path":null,"workspace_path":null,"state_dir":"/root/.local/state/ah/f2647adf","tmux_socket":"ahd-5a709091c406a3fa","tmux_server_alive":true,"master_tmux_alive":false,"worker_tmux_alive":false,"worker_tmux_expected_count":6,"agents":[],"sessions":[{"session_id":"sess_6ddea78e-0ea9-4f00-9b9a-15226e3cce28","project_id":"feat-studio-ah-state-contract-impl","path":"/root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl","status":"STARTING","master_state":null,"master_tmux_session":"master_feat-studio-ah-state-contract-impl","master_tmux_alive":false,"master_pane_id":null,"master_pid":null,"master_last_exit_reason":null,"db_tracked_agents":0,"live_agents":0,"cleanup_required":false,"safe_to_cleanup":false}],"jobs":[],"job_events":[],"job_event_cursor":0}"#;

/// `degraded` — SpecTranscribed from requirements Req 3.7 (via task0 §7): the recorded
/// real shape is `active:false, runtime_state:"degraded"`, one session `status:"ACTIVE"`
/// with `live_agents=10`, dead master tmux, `cleanup_required:true`. NOT independently
/// re-captured on the task-0 machine. `safe_to_cleanup:true` is added (not in the
/// recorded shape) so the Req 3.7 cleanup-then-open path is exercisable; the top-level
/// frame envelope and remaining session fields are schema_version:2-inferred.
pub(crate) const SNAPSHOT_DEGRADED: &str = r#"{"schema_version":2,"event":"snapshot","sequence":1,"reason":"initial","runtime_state":"degraded","active":false,"ahd_alive":true,"ahd_has_inventory":true,"config_path":null,"workspace_path":null,"state_dir":"/root/.local/state/ah/f2647adf","tmux_socket":"ahd-5a709091c406a3fa","tmux_server_alive":true,"master_tmux_alive":false,"worker_tmux_alive":true,"worker_tmux_expected_count":10,"agents":[],"sessions":[{"session_id":"sess_6ddea78e-0ea9-4f00-9b9a-15226e3cce28","project_id":"feat-studio-ah-state-contract-impl","path":"/root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl","status":"ACTIVE","master_state":null,"master_tmux_session":"master_feat-studio-ah-state-contract-impl","master_tmux_alive":false,"master_pane_id":null,"master_pid":null,"master_last_exit_reason":null,"db_tracked_agents":10,"live_agents":10,"cleanup_required":true,"safe_to_cleanup":true}],"jobs":[],"job_events":[],"job_event_cursor":0}"#;

/// Terminal `CLOSED` session — SchemaDerived. ahd alive, `active:false`,
/// `runtime_state:"inactive"`, one session `status:"CLOSED"` (terminal, Req 3.2 lists
/// CLOSED/FAILED/KILLED), cleanly settled (`live_agents:0`, `cleanup_required:false`,
/// `safe_to_cleanup:true`). Req 3.2/5.1/5.3: all-sessions-terminal + active=false → Open.
/// Terminal `master_state`/`master_last_exit_reason` were never captured → `null`.
pub(crate) const SNAPSHOT_TERMINAL_CLOSED: &str = r#"{"schema_version":2,"event":"snapshot","sequence":1,"reason":"initial","runtime_state":"inactive","active":false,"ahd_alive":true,"ahd_has_inventory":true,"config_path":null,"workspace_path":null,"state_dir":"/root/.local/state/ah/f2647adf","tmux_socket":null,"tmux_server_alive":true,"master_tmux_alive":false,"worker_tmux_alive":false,"worker_tmux_expected_count":0,"agents":[],"sessions":[{"session_id":"sess_6ddea78e-0ea9-4f00-9b9a-15226e3cce28","project_id":"feat-studio-ah-state-contract-impl","path":"/root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl","status":"CLOSED","master_state":null,"master_tmux_session":"master_feat-studio-ah-state-contract-impl","master_tmux_alive":false,"master_pane_id":null,"master_pid":null,"master_last_exit_reason":null,"db_tracked_agents":0,"live_agents":0,"cleanup_required":false,"safe_to_cleanup":true}],"jobs":[],"job_events":[],"job_event_cursor":0}"#;

/// Terminal `FAILED` session — SchemaDerived, identical to [`SNAPSHOT_TERMINAL_CLOSED`]
/// but `status:"FAILED"`. Req 3.2/5.1: still terminal → Open. Kept cleanly settled
/// (`cleanup_required:false`) so it stays a pure Req 3.2 terminal case, distinct from
/// the degraded cleanup-then-open fixture.
pub(crate) const SNAPSHOT_TERMINAL_FAILED: &str = r#"{"schema_version":2,"event":"snapshot","sequence":1,"reason":"initial","runtime_state":"inactive","active":false,"ahd_alive":true,"ahd_has_inventory":true,"config_path":null,"workspace_path":null,"state_dir":"/root/.local/state/ah/f2647adf","tmux_socket":null,"tmux_server_alive":true,"master_tmux_alive":false,"worker_tmux_alive":false,"worker_tmux_expected_count":0,"agents":[],"sessions":[{"session_id":"sess_6ddea78e-0ea9-4f00-9b9a-15226e3cce28","project_id":"feat-studio-ah-state-contract-impl","path":"/root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl","status":"FAILED","master_state":null,"master_tmux_session":"master_feat-studio-ah-state-contract-impl","master_tmux_alive":false,"master_pane_id":null,"master_pid":null,"master_last_exit_reason":null,"db_tracked_agents":0,"live_agents":0,"cleanup_required":false,"safe_to_cleanup":true}],"jobs":[],"job_events":[],"job_event_cursor":0}"#;

/// Unsupported schema — SchemaDerived. `schema_version:999` on an otherwise-shaped
/// snapshot; Req 2.5: Studio surfaces an unsupported-contract error and does NOT fall
/// back to local probing. The value 999 stands in for any version the typed parser
/// does not recognize.
pub(crate) const SNAPSHOT_UNSUPPORTED_SCHEMA: &str = r#"{"schema_version":999,"event":"snapshot","sequence":1,"reason":"initial","runtime_state":"active","active":true,"ahd_alive":true,"ahd_has_inventory":true,"config_path":null,"workspace_path":null,"state_dir":"/root/.local/state/ah/f2647adf","tmux_socket":null,"tmux_server_alive":true,"master_tmux_alive":true,"worker_tmux_alive":true,"worker_tmux_expected_count":0,"agents":[],"sessions":[],"jobs":[],"job_events":[],"job_event_cursor":0}"#;

/// Second active stack owned by the `codex` assistant — SchemaDerived. In Studio each
/// assistant (Claude, Codex) is a separate ah config → separate snapshot, so the
/// "both active simultaneously" case of Req 5.12/6.2 is this fixture paired with
/// [`SNAPSHOT_ACTIVE`] (Claude's stack). The task-0 dev fleet had no `codex` provider,
/// so this stack (distinct `state_dir`/`session_id`/`project_id`/path, one `codex`
/// agent) is constructed to model a Studio-managed codex workspace.
pub(crate) const SNAPSHOT_ACTIVE_CODEX: &str = r#"{"schema_version":2,"event":"snapshot","sequence":1,"reason":"initial","runtime_state":"active","active":true,"ahd_alive":true,"ahd_has_inventory":true,"config_path":null,"workspace_path":null,"state_dir":"/root/.local/state/ah/c0dec0de","tmux_socket":"ahd-codexsocket00000001","tmux_server_alive":true,"master_tmux_alive":true,"worker_tmux_alive":true,"worker_tmux_expected_count":1,"agents":[{"agent_id":"m1","provider":"codex","state":"IDLE","sub_state":"Matched","tmux_alive":true,"tmux_session":"agent_m1","session_id":"sess_c0dec0de-0000-4000-8000-000000000001","pid":424242}],"sessions":[{"session_id":"sess_c0dec0de-0000-4000-8000-000000000001","project_id":"studio-codex-workspace","path":"/root/agent-harness/.worktrees/studio-codex-workspace","status":"ACTIVE","master_state":"IDLE","master_tmux_session":"master_studio-codex-workspace","master_tmux_alive":true,"master_pane_id":"%0","master_pid":424200,"master_last_exit_reason":null,"db_tracked_agents":1,"live_agents":1,"cleanup_required":false,"safe_to_cleanup":false}],"jobs":[],"job_events":[],"job_event_cursor":0}"#;

/// Every standalone snapshot fixture with its provenance, for iteration in the
/// self-validation tests (and as the single machine-readable provenance registry).
pub(crate) const ALL_SNAPSHOT_FIXTURES: &[(&str, &str, Provenance)] = &[
    ("SNAPSHOT_ACTIVE", SNAPSHOT_ACTIVE, Provenance::Captured),
    (
        "SNAPSHOT_DAEMON_ABSENT",
        SNAPSHOT_DAEMON_ABSENT,
        Provenance::Captured,
    ),
    ("SNAPSHOT_INACTIVE", SNAPSHOT_INACTIVE, Provenance::SchemaDerived),
    ("SNAPSHOT_STARTING", SNAPSHOT_STARTING, Provenance::SchemaDerived),
    ("SNAPSHOT_DEGRADED", SNAPSHOT_DEGRADED, Provenance::SpecTranscribed),
    (
        "SNAPSHOT_TERMINAL_CLOSED",
        SNAPSHOT_TERMINAL_CLOSED,
        Provenance::SchemaDerived,
    ),
    (
        "SNAPSHOT_TERMINAL_FAILED",
        SNAPSHOT_TERMINAL_FAILED,
        Provenance::SchemaDerived,
    ),
    (
        "SNAPSHOT_UNSUPPORTED_SCHEMA",
        SNAPSHOT_UNSUPPORTED_SCHEMA,
        Provenance::SchemaDerived,
    ),
    (
        "SNAPSHOT_ACTIVE_CODEX",
        SNAPSHOT_ACTIVE_CODEX,
        Provenance::SchemaDerived,
    ),
];

// ───────────────────────── Sequence-reset fixture (bullet 3, Req 2.1/5.13) ──────
//
// task0 §6: `ah status --json` one-shot is ALWAYS `sequence:1/reason:"initial"`; the
// `ah events` stream's FIRST frame is likewise `1/initial`, then it advances
// monotonically WITHIN that stream (§6b recorded 2:tmux_changed, 3:job_changed, …,
// up to 311). `sequence` is therefore a per-stream baseline, NOT globally monotonic:
// a naive global-max guard would let a stale high `sequence` permanently drop the
// post-close / post-restart snapshot. These frames stage the exact reset scenario.
//
// The sequence/reason progression is CAPTURED (§6b); the full snapshot bodies are a
// compact schema-valid active snapshot (SchemaDerived) because the §6b capture logged
// only seq/reason/runtime_state per frame.

/// Stream frame 1: fresh baseline `sequence:1, reason:"initial"`, active.
pub(crate) const SEQUENCE_FRAME_1_INITIAL: &str = r#"{"schema_version":2,"event":"snapshot","sequence":1,"reason":"initial","runtime_state":"active","active":true,"ahd_alive":true,"state_dir":"/root/.local/state/ah/f2647adf","sessions":[{"session_id":"sess_6ddea78e-0ea9-4f00-9b9a-15226e3cce28","project_id":"feat-studio-ah-state-contract-impl","path":"/root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl","status":"ACTIVE","live_agents":6,"db_tracked_agents":6,"cleanup_required":false,"safe_to_cleanup":false}],"agents":[]}"#;

/// Stream frame 2: `sequence:2, reason:"tmux_changed"` (§6b), same stream/session.
pub(crate) const SEQUENCE_FRAME_2_TMUX_CHANGED: &str = r#"{"schema_version":2,"event":"snapshot","sequence":2,"reason":"tmux_changed","runtime_state":"active","active":true,"ahd_alive":true,"state_dir":"/root/.local/state/ah/f2647adf","sessions":[{"session_id":"sess_6ddea78e-0ea9-4f00-9b9a-15226e3cce28","project_id":"feat-studio-ah-state-contract-impl","path":"/root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl","status":"ACTIVE","live_agents":6,"db_tracked_agents":6,"cleanup_required":false,"safe_to_cleanup":false}],"agents":[]}"#;

/// Stream frame 3: `sequence:3, reason:"job_changed"` (§6b), same stream/session.
pub(crate) const SEQUENCE_FRAME_3_JOB_CHANGED: &str = r#"{"schema_version":2,"event":"snapshot","sequence":3,"reason":"job_changed","runtime_state":"active","active":true,"ahd_alive":true,"state_dir":"/root/.local/state/ah/f2647adf","sessions":[{"session_id":"sess_6ddea78e-0ea9-4f00-9b9a-15226e3cce28","project_id":"feat-studio-ah-state-contract-impl","path":"/root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl","status":"ACTIVE","live_agents":6,"db_tracked_agents":6,"cleanup_required":false,"safe_to_cleanup":false}],"agents":[]}"#;

/// The in-order stream after it has advanced past `sequence:1` (frames 1→2→3, same
/// stream / same `session_id`). Replaying an earlier index (e.g. frame 2 after frame 3)
/// simulates a genuinely-stale in-stream frame the monotonic guard must still drop
/// (`test_sequence_guard_within_stream`, Req 5.13 second half).
pub(crate) const SEQUENCE_STREAM_FRAMES: &[&str] = &[
    SEQUENCE_FRAME_1_INITIAL,
    SEQUENCE_FRAME_2_TMUX_CHANGED,
    SEQUENCE_FRAME_3_JOB_CHANGED,
];

/// The reset frame for a SAME-session lifetime: after the stream advanced to
/// `sequence:3`, a new `sequence:1, reason:"initial"` frame arrives (a fresh
/// subscription, a one-shot `status --json`, or a daemon restart on the same session)
/// carrying a genuinely newer state — here the stack has CLOSED (`active:false`,
/// `status:"CLOSED"`). Req 2.1/5.13: this MUST be applied via an unconditional reset,
/// NOT dropped by the older-or-equal guard (naive global-max would wrongly drop it and
/// leave the UI stuck "active" forever). Same `session_id` as the stream.
pub(crate) const SEQUENCE_RESET_FRAME_SAME_SESSION: &str = r#"{"schema_version":2,"event":"snapshot","sequence":1,"reason":"initial","runtime_state":"inactive","active":false,"ahd_alive":true,"state_dir":"/root/.local/state/ah/f2647adf","sessions":[{"session_id":"sess_6ddea78e-0ea9-4f00-9b9a-15226e3cce28","project_id":"feat-studio-ah-state-contract-impl","path":"/root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl","status":"CLOSED","live_agents":0,"db_tracked_agents":0,"cleanup_required":false,"safe_to_cleanup":true}],"agents":[]}"#;

/// The reset frame for a CHANGED-session lifetime: `sequence:1, reason:"initial"` with
/// a DIFFERENT `sessions[].session_id` (a post-restart stack). Req 2.1/5.13 names a
/// changed `session_id` as an independent unconditional-reset trigger; SchemaDerived
/// (the new session id is a fresh constructed identity).
pub(crate) const SEQUENCE_RESET_FRAME_NEW_SESSION: &str = r#"{"schema_version":2,"event":"snapshot","sequence":1,"reason":"initial","runtime_state":"active","active":true,"ahd_alive":true,"state_dir":"/root/.local/state/ah/f2647adf","sessions":[{"session_id":"sess_11111111-2222-4333-8444-555555555555","project_id":"feat-studio-ah-state-contract-impl","path":"/root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl","status":"ACTIVE","live_agents":6,"db_tracked_agents":6,"cleanup_required":false,"safe_to_cleanup":false}],"agents":[]}"#;

// ─────────────────── Config ownership fixture (bullet 4, Req 4.6/5.9/6.1) ───────

/// A discovered ah config together with its ownership class and the `readOnly` flag
/// the Req 6.1 payload must carry for it. `read_only == true` ⇔ workspace-owned
/// (lifecycle commands forbidden); `read_only == false` ⇔ Studio-managed temp config
/// (full lifecycle allowed).
pub(crate) struct ConfigOwnershipFixture {
    /// The ah config path SHAPE this class is defined by (frozen, authored on
    /// Linux). Classifier/guard assertions must go through
    /// `resolved_config_path()` instead: the Studio-managed class means "under
    /// the RUNTIME `{temp}/skill-studio-ah` namespace", and no static string
    /// can satisfy that on every platform (Windows temp is per-user).
    pub config_path: &'static str,
    /// Req 6.1 `readOnly` flag: true = workspace-owned, false = Studio-managed temp.
    pub read_only: bool,
    /// Human note on WHY this is the class it is.
    pub note: &'static str,
}

impl ConfigOwnershipFixture {
    /// Platform-resolved path carrying this fixture's ownership class on the
    /// machine actually running the tests. Studio-managed: the frozen shape's
    /// suffix rebased onto the single temp-namespace authority
    /// (`studio_ah_temp_root`). Workspace-owned: the frozen path as-is — an
    /// absolute path outside the temp namespace classifies workspace-owned on
    /// every platform.
    pub fn resolved_config_path(&self) -> std::path::PathBuf {
        if self.read_only {
            return std::path::PathBuf::from(self.config_path);
        }
        let suffix = self
            .config_path
            .split_once("skill-studio-ah/")
            .map(|(_, rest)| rest)
            .expect("Studio-managed fixture path contains the temp namespace segment");
        suffix
            .split('/')
            .fold(crate::studio_ah_temp_root(), |acc, seg| acc.join(seg))
    }
}

/// Workspace-owned config: an `ah.toml` reachable by walking up from the workspace
/// root (`find_ah_config`, lib.rs:203). This repository's own root `ah.toml` (present
/// since PR #478) is the canonical live example — opening Studio anywhere under this
/// tree would let a naive integration run `ah stop`/`kill` against the operator's own
/// fleet. Req 4.6 class (a): read-only; Req 6.1 `readOnly:true`.
pub(crate) const CONFIG_WORKSPACE_OWNED: ConfigOwnershipFixture = ConfigOwnershipFixture {
    config_path: "/root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl/ah.toml",
    read_only: true,
    note: "walked-up ah.toml (find_ah_config) → workspace-owned → lifecycle forbidden",
};

/// Studio-managed temp config: the config Studio itself generates under the Studio
/// temp namespace `{temp}/skill-studio-ah/{workspace_hash}/{assistant}/ah.toml`
/// (`transient_ah_config_path`, lib.rs:233). Req 4.6 class (b): eligible for
/// `start`/`stop`/`kill`; Req 6.1 `readOnly:false`. The hash/slug segments below are
/// illustrative of the real path shape (a 16-hex `workspace_hash` + assistant slug).
pub(crate) const CONFIG_STUDIO_MANAGED: ConfigOwnershipFixture = ConfigOwnershipFixture {
    config_path: "/tmp/skill-studio-ah/0123456789abcdef/claude/ah.toml",
    read_only: false,
    note: "generated under {temp}/skill-studio-ah → Studio-managed → full lifecycle",
};

/// Both ownership fixtures, for iteration in the self-validation tests.
pub(crate) const ALL_CONFIG_OWNERSHIP_FIXTURES: &[&ConfigOwnershipFixture] =
    &[&CONFIG_WORKSPACE_OWNED, &CONFIG_STUDIO_MANAGED];

// ─────────────────── Identity-validation fixtures (bullet 5, Req 2.7/4.8/5.10) ──

/// A snapshot paired with the config identity Studio actually requested, plus the
/// expected verdict of the Req 2.7/4.8 identity check (authoritative on `state_dir` +
/// session identity; `config_path` advisory; all path comparison canonicalized across
/// the Windows↔WSL boundary, never raw string).
pub(crate) struct IdentityFixture {
    /// The `--config` path Studio requested (may be a Windows `C:\...` path).
    pub requested_config_path: &'static str,
    /// The workspace directory Studio requested; its basename is the expected
    /// `project_id` (the platform-neutral cross-host anchor, Req 2.7).
    pub requested_workspace_dir: &'static str,
    /// The `project_id` Studio independently derives from `requested_workspace_dir`.
    pub expected_project_id: &'static str,
    /// The raw snapshot the daemon returned for that request.
    pub snapshot_json: &'static str,
    /// Expected verdict: does the snapshot's authoritative identity match the request
    /// after cross-platform canonicalization?
    pub expect_identity_match: bool,
    pub provenance: Provenance,
    pub note: &'static str,
}

/// NF1 echo-through mismatch — CAPTURED from task0 §4. `ah --config
/// /tmp/ah-fixture-nf1/ah.toml events` echoed the REQUESTED path straight into
/// `config_path`, yet returned the live fleet's `state_dir` (f2647adf) and session
/// identity (`sess_6ddea78e…`, project `feat-studio-ah-state-contract-impl`). Req
/// 5.10(a): a `config_path`-only check would WRONGLY accept this; the authoritative
/// `state_dir`/session identity does not match the requested `ah-fixture-nf1`, so it
/// MUST be discarded with a diagnostic. `expect_identity_match: false`.
pub(crate) const IDENTITY_NF1_ECHO_MISMATCH: IdentityFixture = IdentityFixture {
    requested_config_path: "/tmp/ah-fixture-nf1/ah.toml",
    requested_workspace_dir: "/tmp/ah-fixture-nf1",
    expected_project_id: "ah-fixture-nf1",
    snapshot_json: r#"{"schema_version":2,"event":"snapshot","sequence":1,"reason":"initial","runtime_state":"active","active":true,"ahd_alive":true,"config_path":"/tmp/ah-fixture-nf1/ah.toml","workspace_path":null,"state_dir":"/root/.local/state/ah/f2647adf","tmux_socket":"ahd-5a709091c406a3fa","sessions":[{"session_id":"sess_6ddea78e-0ea9-4f00-9b9a-15226e3cce28","project_id":"feat-studio-ah-state-contract-impl","path":"/root/agent-harness/.worktrees/feat-studio-ah-state-contract-impl","status":"ACTIVE","live_agents":6,"db_tracked_agents":6,"cleanup_required":false,"safe_to_cleanup":false,"master_tmux_alive":true}],"agents":[]}"#,
    expect_identity_match: false,
    provenance: Provenance::Captured,
    note: "config_path matches request but state_dir/session identity is another live daemon (NF1) → discard",
};

/// Windows↔WSL canonical match — SchemaDerived. A Windows host requests
/// `C:\Users\dev\myproj` while the WSL-side ah returns `/mnt/c/Users/dev/myproj` for
/// the same target. Req 5.10(b): raw string comparison (`C:\Users\dev\myproj` vs
/// `/mnt/c/Users/dev/myproj`) FAILS, but canonicalizing the request across the
/// Windows↔WSL boundary (`windows_path_to_wsl`, lib.rs:1609) plus the platform-neutral
/// `project_id` basename (`myproj`) matches → accept. `expect_identity_match: true`.
/// (Constructed: task 0 ran only on Linux, so no Windows-host capture exists; the
/// `/mnt/c/...` mount convention is real.)
pub(crate) const IDENTITY_WINDOWS_WSL_CANONICAL_MATCH: IdentityFixture = IdentityFixture {
    requested_config_path: r"C:\Users\dev\myproj\ah.toml",
    requested_workspace_dir: r"C:\Users\dev\myproj",
    expected_project_id: "myproj",
    snapshot_json: r#"{"schema_version":2,"event":"snapshot","sequence":1,"reason":"initial","runtime_state":"active","active":true,"ahd_alive":true,"config_path":"/mnt/c/Users/dev/myproj/ah.toml","workspace_path":"/mnt/c/Users/dev/myproj","state_dir":"/mnt/c/Users/dev/myproj/.ah-state","tmux_socket":"ahd-winwslcanonical0001","sessions":[{"session_id":"sess_windows-wsl-canonical-0001","project_id":"myproj","path":"/mnt/c/Users/dev/myproj","status":"ACTIVE","live_agents":1,"db_tracked_agents":1,"cleanup_required":false,"safe_to_cleanup":false,"master_tmux_alive":true}],"agents":[]}"#,
    expect_identity_match: true,
    provenance: Provenance::SchemaDerived,
    note: "C:\\ request vs /mnt/c WSL snapshot: raw compare fails, canonical path + project_id match → accept",
};

/// Both identity fixtures, for iteration in the self-validation tests.
pub(crate) const ALL_IDENTITY_FIXTURES: &[&IdentityFixture] =
    &[&IDENTITY_NF1_ECHO_MISMATCH, &IDENTITY_WINDOWS_WSL_CANONICAL_MATCH];

// ───────────────────────────── Fixture self-validation ─────────────────────────
//
// These tests do NOT exercise production logic (task 1 builds no production code —
// the typed parser is task 3). They validate the FIXTURE DATA itself: that every raw
// snapshot is well-formed JSON carrying the documented decision fields, that the
// sequence stream really advances then resets, and that the identity pair's Windows/WSL
// strings are a genuine canonical pair per the existing `windows_path_to_wsl` helper.
// This is what keeps the frozen fixtures honest and keeps every const referenced.

#[cfg(test)]
mod self_validation {
    use super::*;
    use serde_json::Value;
    use std::path::Path;

    fn parse(json: &str) -> Value {
        serde_json::from_str(json).expect("fixture must be well-formed JSON")
    }

    /// Every standalone snapshot must be single-line (safe for JSONL/`ah events`
    /// line-splitting) well-formed JSON with a `schema_version` and `runtime_state`.
    #[test]
    fn all_snapshots_are_single_line_well_formed_json() {
        for (name, json, _prov) in ALL_SNAPSHOT_FIXTURES {
            assert!(
                !json.contains('\n'),
                "{name} must be single-line so it survives JSONL line-splitting"
            );
            let v = parse(json);
            assert!(
                v.get("schema_version").is_some(),
                "{name} must carry schema_version"
            );
            assert!(
                v.get("runtime_state").is_some(),
                "{name} must carry runtime_state"
            );
        }
    }

    /// Provenance registry sanity: exactly the two verbatim captures are tagged
    /// `Captured`; `degraded` is the sole `SpecTranscribed`; the rest are
    /// `SchemaDerived`. Guards against a fixture silently mislabelling its origin.
    #[test]
    fn snapshot_provenance_matches_task0_evidence() {
        let captured: Vec<&str> = ALL_SNAPSHOT_FIXTURES
            .iter()
            .filter(|(_, _, p)| *p == Provenance::Captured)
            .map(|(n, _, _)| *n)
            .collect();
        assert_eq!(captured, vec!["SNAPSHOT_ACTIVE", "SNAPSHOT_DAEMON_ABSENT"]);

        let transcribed: Vec<&str> = ALL_SNAPSHOT_FIXTURES
            .iter()
            .filter(|(_, _, p)| *p == Provenance::SpecTranscribed)
            .map(|(n, _, _)| *n)
            .collect();
        assert_eq!(transcribed, vec!["SNAPSHOT_DEGRADED"]);
    }

    #[test]
    fn active_snapshot_reports_live_fleet_across_providers() {
        let v = parse(SNAPSHOT_ACTIVE);
        assert_eq!(v["runtime_state"], "active");
        assert_eq!(v["active"], true);
        assert_eq!(v["ahd_alive"], true);
        // Six agents spanning claude + antigravity providers (task0 §附加A).
        let agents = v["agents"].as_array().expect("agents array");
        assert_eq!(agents.len(), 6);
        assert!(agents.iter().any(|a| a["provider"] == "claude"));
        assert!(agents.iter().any(|a| a["provider"] == "antigravity"));
        let session = &v["sessions"][0];
        assert_eq!(session["status"], "ACTIVE");
        assert_eq!(session["live_agents"], 6);
        assert_eq!(session["project_id"], "feat-studio-ah-state-contract-impl");
    }

    #[test]
    fn daemon_absent_snapshot_is_structured_not_stderr() {
        let v = parse(SNAPSHOT_DAEMON_ABSENT);
        assert_eq!(v["reason"], "daemon_absent");
        assert_eq!(v["runtime_state"], "inactive");
        assert_eq!(v["ahd_alive"], false);
        assert_eq!(v["active"], false);
        assert!(v["sessions"].as_array().expect("sessions").is_empty());
        assert!(v["agents"].as_array().expect("agents").is_empty());
    }

    #[test]
    fn inactive_snapshot_has_ahd_alive_but_not_active() {
        let v = parse(SNAPSHOT_INACTIVE);
        assert_eq!(v["runtime_state"], "inactive");
        assert_eq!(v["ahd_alive"], true, "ahd alive distinguishes this from daemon_absent");
        assert_eq!(v["active"], false);
    }

    #[test]
    fn starting_snapshot_is_hands_off() {
        let v = parse(SNAPSHOT_STARTING);
        assert_eq!(v["runtime_state"], "starting");
        assert_eq!(v["active"], false);
        let session = &v["sessions"][0];
        // hands-off: not marked cleanup-eligible, must be left alone (Req 3.6).
        assert_eq!(session["cleanup_required"], false);
        assert_eq!(session["safe_to_cleanup"], false);
    }

    #[test]
    fn degraded_snapshot_matches_req_3_7_recorded_shape() {
        let v = parse(SNAPSHOT_DEGRADED);
        assert_eq!(v["runtime_state"], "degraded");
        assert_eq!(v["active"], false);
        let session = &v["sessions"][0];
        // Req 3.7 recorded shape: session ACTIVE, live_agents=10, master tmux dead,
        // cleanup_required=true → the cleanup-then-open path (Req 3.7/5.7).
        assert_eq!(session["status"], "ACTIVE");
        assert_eq!(session["live_agents"], 10);
        assert_eq!(session["master_tmux_alive"], false);
        assert_eq!(session["cleanup_required"], true);
    }

    #[test]
    fn terminal_snapshots_expose_closed_and_failed_statuses() {
        let closed = parse(SNAPSHOT_TERMINAL_CLOSED);
        assert_eq!(closed["active"], false);
        assert_eq!(closed["ahd_alive"], true);
        assert_eq!(closed["sessions"][0]["status"], "CLOSED");

        let failed = parse(SNAPSHOT_TERMINAL_FAILED);
        assert_eq!(failed["active"], false);
        assert_eq!(failed["sessions"][0]["status"], "FAILED");
    }

    #[test]
    fn unsupported_schema_snapshot_carries_unknown_version() {
        let v = parse(SNAPSHOT_UNSUPPORTED_SCHEMA);
        let schema = v["schema_version"].as_u64().expect("schema_version int");
        assert!(schema > 2, "must be an unrecognized schema version (Req 2.5)");
    }

    #[test]
    fn codex_active_snapshot_is_an_independent_second_stack() {
        let claude = parse(SNAPSHOT_ACTIVE);
        let codex = parse(SNAPSHOT_ACTIVE_CODEX);
        // Distinct identity from the Claude stack so the two can be paired as a
        // simultaneously-active fixture (Req 5.12/6.2) without collision.
        assert_ne!(claude["state_dir"], codex["state_dir"]);
        assert_ne!(
            claude["sessions"][0]["session_id"],
            codex["sessions"][0]["session_id"]
        );
        assert_eq!(codex["active"], true);
        assert_eq!(codex["agents"][0]["provider"], "codex");
    }

    #[test]
    fn version_fixtures_trim_to_expected_tokens() {
        assert_eq!(AH_VERSION_SUPPORTED.trim(), "1.5.0");
        assert_eq!(AH_VERSION_MIN_SUPPORTED.trim(), "1.4.0");
        assert_eq!(AH_VERSION_UNSUPPORTED.trim(), "1.3.4");
        // Unparsable stays non-empty garbage after trim → fail-fast input (Req 1.2).
        assert_eq!(AH_VERSION_UNPARSABLE.trim(), "not-a-version");
        // All are the bare format (no "ah " prefix / second token) per Req 1.8.
        for raw in [
            AH_VERSION_SUPPORTED,
            AH_VERSION_MIN_SUPPORTED,
            AH_VERSION_UNSUPPORTED,
        ] {
            assert!(
                !raw.trim().contains(' '),
                "bare `ah version` output has no space/second token (Req 1.8)"
            );
        }
    }

    #[test]
    fn sequence_stream_advances_then_reset_returns_to_one() {
        let seqs: Vec<u64> = SEQUENCE_STREAM_FRAMES
            .iter()
            .map(|f| parse(f)["sequence"].as_u64().expect("sequence int"))
            .collect();
        assert_eq!(seqs, vec![1, 2, 3], "stream advances monotonically in one stream");
        assert_eq!(parse(SEQUENCE_STREAM_FRAMES[0])["reason"], "initial");
        assert_eq!(parse(SEQUENCE_STREAM_FRAMES[1])["reason"], "tmux_changed");
        assert_eq!(parse(SEQUENCE_STREAM_FRAMES[2])["reason"], "job_changed");

        // Same-session reset: back to sequence 1 / reason "initial", same session id,
        // but a genuinely newer state (stack CLOSED) that a naive max-guard would drop.
        let reset = parse(SEQUENCE_RESET_FRAME_SAME_SESSION);
        assert_eq!(reset["sequence"], 1);
        assert_eq!(reset["reason"], "initial");
        assert_eq!(reset["active"], false);
        assert_eq!(reset["sessions"][0]["status"], "CLOSED");
        assert_eq!(
            reset["sessions"][0]["session_id"],
            parse(SEQUENCE_STREAM_FRAMES[2])["sessions"][0]["session_id"],
            "same-session reset keeps the session id"
        );
    }

    #[test]
    fn sequence_new_session_reset_changes_session_id() {
        let stream_session = parse(SEQUENCE_STREAM_FRAMES[2])["sessions"][0]["session_id"].clone();
        let reset = parse(SEQUENCE_RESET_FRAME_NEW_SESSION);
        assert_eq!(reset["sequence"], 1);
        assert_eq!(reset["reason"], "initial");
        assert_ne!(
            reset["sessions"][0]["session_id"], stream_session,
            "changed session_id is an independent reset trigger (Req 2.1/5.13)"
        );
    }

    #[test]
    fn config_ownership_fixtures_split_read_only_correctly() {
        assert!(
            CONFIG_WORKSPACE_OWNED.read_only,
            "workspace-owned config is read-only (Req 4.6 class a / readOnly:true)"
        );
        assert!(CONFIG_WORKSPACE_OWNED.config_path.ends_with("/ah.toml"));
        assert!(!CONFIG_WORKSPACE_OWNED.note.is_empty());

        assert!(
            !CONFIG_STUDIO_MANAGED.read_only,
            "Studio-managed temp config allows lifecycle (Req 4.6 class b / readOnly:false)"
        );
        assert!(
            CONFIG_STUDIO_MANAGED.config_path.contains("skill-studio-ah"),
            "Studio-managed config lives under the Studio temp namespace"
        );

        // Exactly one of each class in the registry.
        let read_only_count = ALL_CONFIG_OWNERSHIP_FIXTURES
            .iter()
            .filter(|c| c.read_only)
            .count();
        assert_eq!(read_only_count, 1);
    }

    #[test]
    fn identity_fixtures_registered_with_one_match_and_one_mismatch() {
        for f in ALL_IDENTITY_FIXTURES {
            assert!(!f.note.is_empty(), "each identity fixture documents its verdict");
            parse(f.snapshot_json); // every identity snapshot must be well-formed JSON
            assert!(!f.expected_project_id.is_empty());
        }
        let matches = ALL_IDENTITY_FIXTURES
            .iter()
            .filter(|f| f.expect_identity_match)
            .count();
        assert_eq!(matches, 1, "exactly one accept case + one discard case");
    }

    #[test]
    fn nf1_identity_fixture_is_config_path_echo_with_mismatched_identity() {
        let f = &IDENTITY_NF1_ECHO_MISMATCH;
        assert!(!f.expect_identity_match, "NF1 echo must be discarded");
        let v = parse(f.snapshot_json);
        // config_path echoes the request (the trap a config_path-only check falls into)…
        assert_eq!(v["config_path"], f.requested_config_path);
        // …but the authoritative session project_id is a DIFFERENT project.
        assert_ne!(v["sessions"][0]["project_id"], f.expected_project_id);
        assert_eq!(f.provenance, Provenance::Captured);
    }

    #[test]
    fn windows_wsl_identity_fixture_is_a_genuine_canonical_pair() {
        let f = &IDENTITY_WINDOWS_WSL_CANONICAL_MATCH;
        assert!(f.expect_identity_match, "canonical pair must be accepted");
        let v = parse(f.snapshot_json);
        let snapshot_path = v["sessions"][0]["path"].as_str().expect("session path");

        // Raw string comparison FAILS (this is why Req 2.7 forbids raw compare)…
        assert_ne!(f.requested_workspace_dir, snapshot_path);
        // …but Studio's own Windows→WSL canonicalization makes them equal.
        assert_eq!(
            crate::windows_path_to_wsl(Path::new(f.requested_workspace_dir)),
            snapshot_path,
            "requested C:\\ path canonicalizes to the WSL snapshot path"
        );
        // project_id (directory basename) is the platform-neutral anchor and matches.
        assert_eq!(v["sessions"][0]["project_id"], f.expected_project_id);
    }
}
