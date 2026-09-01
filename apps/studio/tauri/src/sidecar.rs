use command_group::{CommandGroup, GroupChild};
use rand::{distr::Alphanumeric, Rng};
use serde::{Deserialize, Serialize};
use std::{
    collections::VecDeque,
    ffi::OsString,
    io::{BufRead, BufReader},
    net::TcpListener,
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::{Arc, Mutex},
    thread,
    time::{Duration, Instant},
};

const MAX_STARTUP_ATTEMPTS: usize = 3;
const STDERR_RING_LINES: usize = 50;
const HEALTH_POLL_INTERVAL: Duration = Duration::from_millis(200);
/// Per-request budget for one poll of the startup health wait. Short on
/// purpose: `wait_for_health` is a LOOP, so a request that hangs costs the loop
/// its cadence, and the next poll a moment later is a better use of the
/// remaining time than waiting out one slow attempt.
const HEALTH_POLL_REQUEST_TIMEOUT: Duration = Duration::from_millis(500);
/// Per-request budget for the destruction gate (`confirm_serving`), which asks
/// ONCE and lets the caller's own retry schedule provide the repetition.
///
/// Deliberately more patient than `HEALTH_POLL_REQUEST_TIMEOUT`, because the
/// two ask under opposite stakes. A slow poll during startup costs nothing — the
/// loop asks again in 200ms. A slow answer HERE is read as "not serving", and
/// the consequence is killing a sidecar that may have a run in flight; a busy
/// interpreter that would have answered in 700ms must not be destroyed for
/// being busy. Two seconds is long enough that only a genuinely wedged event
/// loop misses it, and short enough that recovery from a real death is not
/// visibly stalled by the confirmation.
const CONFIRM_SERVING_REQUEST_TIMEOUT: Duration = Duration::from_secs(2);

#[derive(Debug)]
pub enum SidecarError {
    Io(std::io::Error),
    HealthTimeout { port: u16, stderr: Vec<String> },
    SpawnFailed(String),
}

impl std::fmt::Display for SidecarError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Io(err) => write!(f, "{err}"),
            Self::HealthTimeout { port, stderr } => {
                write!(f, "sidecar health check timed out on port {port}")?;
                if !stderr.is_empty() {
                    write!(f, ": {}", stderr.join("\n"))?;
                }
                Ok(())
            }
            Self::SpawnFailed(message) => write!(f, "{message}"),
        }
    }
}

impl std::error::Error for SidecarError {}

impl From<std::io::Error> for SidecarError {
    fn from(value: std::io::Error) -> Self {
        Self::Io(value)
    }
}

#[derive(Debug, Clone)]
pub struct SidecarLaunchConfig {
    pub python: PathBuf,
    pub backend_dir: PathBuf,
    pub site_packages: PathBuf,
    pub resource_dir: PathBuf,
    pub config_dir: PathBuf,
    pub startup_attempts: usize,
    pub health_timeout: Duration,
    pub shutdown_timeout: Duration,
}

impl SidecarLaunchConfig {
    pub fn from_resource_root(resource_root: impl AsRef<Path>) -> Self {
        let resource_root = resource_root.as_ref();
        Self {
            python: python_executable_path(resource_root),
            backend_dir: backend_dir_for_resource_root(resource_root),
            site_packages: resource_root.join("vendor").join("site-packages"),
            resource_dir: resource_root.join("vendor").join("resources"),
            config_dir: resource_root
                .join("vendor")
                .join("resources")
                .join("config"),
            startup_attempts: MAX_STARTUP_ATTEMPTS,
            // Cold start (first launch after a vendor rebuild compiles .pyc for
            // the engine + gateway import tree) routinely exceeds 5s under load;
            // a warm start returns in ~1-2s so this only matters on a cold boot.
            // 5s caused intermittent "sidecar health check timed out" failures.
            health_timeout: Duration::from_secs(30),
            shutdown_timeout: Duration::from_secs(2),
        }
    }

    pub fn with_config_dir(mut self, config_dir: PathBuf) -> Self {
        self.config_dir = config_dir;
        self
    }
}

fn backend_dir_for_resource_root(resource_root: &Path) -> PathBuf {
    if cfg!(debug_assertions) {
        let live_backend = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .map(|studio_dir| studio_dir.join("backend"));
        if let Some(live_backend) = live_backend {
            if live_backend.join("app").join("main.py").exists() {
                return live_backend;
            }
        }
    }
    resource_root.join("vendor").join("backend")
}

#[derive(Debug, Clone, Serialize)]
pub struct SidecarRuntimeConfig {
    pub port: u16,
    #[serde(rename = "baseURL")]
    pub base_url: String,
    #[serde(rename = "wsURL")]
    pub ws_url: String,
    #[serde(rename = "resourceDir")]
    pub resource_dir: String,
    #[serde(rename = "configDir")]
    pub config_dir: String,
    pub api_token: String,
}

impl SidecarRuntimeConfig {
    fn new(port: u16, resource_dir: &Path, config_dir: &Path, api_token: &str) -> Self {
        Self {
            port,
            base_url: format!("http://127.0.0.1:{port}/api"),
            ws_url: format!("ws://127.0.0.1:{port}/ws"),
            resource_dir: resource_dir.display().to_string(),
            config_dir: config_dir.display().to_string(),
            api_token: api_token.to_string(),
        }
    }
}

/// Name of the Tauri event emitted to the webview after a successful sidecar
/// (re)start. The payload is a `SidecarRuntimeConfig` (same shape returned by
/// `get_sidecar_config`) — the frontend listens for this event and calls
/// `configureApiToken` / `configureApiBaseURL` so an in-flight `useStudioEventStream`
/// reconnect picks up the fresh bearer token instead of looping on 4401 (R-F13).
pub const SIDECAR_RESTARTED_EVENT: &str = "sidecar-restarted";

pub struct SidecarManager {
    state: Mutex<SidecarState>,
}

struct SidecarState {
    child: Option<GroupChild>,
    token: String,
    runtime_config: SidecarRuntimeConfig,
    stderr_lines: Arc<Mutex<VecDeque<String>>>,
    shutdown_timeout: Duration,
    /// Kept on the state so `restart` can rebuild a fresh process tree using
    /// the same resource/config layout the manager was originally bootstrapped
    /// with — without re-deriving paths from scratch.
    launch_config: SidecarLaunchConfig,
}

impl SidecarManager {
    pub fn start(config: SidecarLaunchConfig) -> Result<Self, SidecarError> {
        let attempts = config.startup_attempts.max(1);
        let mut last_error = None;

        for _ in 0..attempts {
            let port = allocate_loopback_port()?;
            let api_token = generate_api_token();
            let stderr_lines = Arc::new(Mutex::new(VecDeque::with_capacity(STDERR_RING_LINES)));
            let mut child =
                spawn_sidecar_process(&config, port, &api_token, Arc::clone(&stderr_lines))?;
            let child_pid = child.inner().id();

            if wait_for_health(port, config.health_timeout, child_pid) {
                return Ok(Self {
                    state: Mutex::new(SidecarState {
                        child: Some(child),
                        token: api_token.clone(),
                        runtime_config: SidecarRuntimeConfig::new(
                            port,
                            &config.resource_dir,
                            &config.config_dir,
                            &api_token,
                        ),
                        stderr_lines,
                        shutdown_timeout: config.shutdown_timeout,
                        launch_config: config.clone(),
                    }),
                });
            }

            let stderr = recent_stderr(&stderr_lines);
            let _ = kill_process_group(&mut child);
            last_error = Some(SidecarError::HealthTimeout { port, stderr });
        }

        Err(last_error.unwrap_or_else(|| SidecarError::SpawnFailed("sidecar did not start".into())))
    }

    pub fn runtime_config(&self) -> SidecarRuntimeConfig {
        self.state
            .lock()
            .expect("sidecar state poisoned")
            .runtime_config
            .clone()
    }

    pub fn recent_stderr(&self) -> Vec<String> {
        recent_stderr(
            &self
                .state
                .lock()
                .expect("sidecar state poisoned")
                .stderr_lines,
        )
    }

    /// Whether THIS instance is still present and still serving — as ONE fact
    /// about ONE process, not two facts that happen to both hold.
    ///
    /// 1. The process handle says the child has not exited (`try_wait`). This is
    ///    also the cheap half, and on the primary platform that is not a
    ///    rounding error: a connect to a closed loopback port on Windows takes
    ///    ~2.04s to come back refused (measured 2026-09-01, pinned by
    ///    `health_probe_once_is_bounded_by_the_timeout_it_was_given`), so asking
    ///    the network first would stall recovery from the ORDINARY case — the
    ///    sidecar really died — by two seconds every time.
    /// 2. `/health` on the recorded port answers successfully AND reports the
    ///    pid of THAT child (`health_probe_once`).
    ///
    /// Step 2 must name the process, or the two steps are about different
    /// things. "The child is alive" and "somebody answers on the port" can both
    /// be true while the child's listener is dead and an unrelated process holds
    /// the port — the child alive for its own reasons, the answer coming from a
    /// stranger. Sparing a sidecar on that evidence hands the frontend a config
    /// for a process that cannot serve it, and the frontend, told this is
    /// recovery, clears the banner and stops retrying: a silent dead end, worse
    /// than the spurious restart this gate exists to prevent. Requiring the
    /// answer to carry the child's pid collapses both steps onto one process.
    ///
    /// A child that is alive but whose `/health` does not name it is therefore
    /// treated exactly like a wedged one: restart. That is the recoverable
    /// direction, and it is the only direction available — there is no third
    /// answer for "something else lives on my port".
    ///
    /// The manager's own lock is released before the probe. Exclusion for the
    /// restart decision is the SUPERVISOR's lock (which the caller holds); this
    /// lock only guards this manager's fields, and holding it across a network
    /// wait would block `runtime_config()` readers — the frontend's
    /// `get_sidecar_config` among them — for no benefit. The pid and port are
    /// read together under it, so they describe the same recorded instance.
    fn confirm_serving(&self, probe_timeout: Duration) -> bool {
        let (port, child_pid) = {
            let mut state = self.state.lock().expect("sidecar state poisoned");
            let port = state.runtime_config.port;
            let Some(child) = state.child.as_mut() else {
                return false;
            };
            // An Err from try_wait is not evidence of exit, so it falls through
            // to the probe rather than authorising a kill.
            if child.try_wait().is_ok_and(|status| status.is_some()) {
                return false;
            }
            (port, child.inner().id())
        };
        health_probe_once(
            &reqwest::blocking::Client::new(),
            port,
            probe_timeout,
            child_pid,
        )
    }

    pub fn shutdown_blocking(&self) {
        let mut state = self.state.lock().expect("sidecar state poisoned");
        if let Some(mut child) = state.child.take() {
            let _ = post_shutdown(state.runtime_config.port, &state.token);
            if wait_for_child_exit(&mut child, state.shutdown_timeout) {
                return;
            }
            let _ = kill_process_group(&mut child);
        }
    }

    /// R-F13: tear down the current sidecar process and spawn a fresh one with
    /// a new bearer token and (if the env now pins a different value) port. The
    /// caller is expected to emit `SIDECAR_RESTARTED_EVENT` with the returned
    /// runtime config so the frontend can rotate `currentApiToken` and the
    /// `useStudioEventStream` reconnect picks up the new token automatically
    /// instead of looping on 4401 closes.
    pub fn restart(&self) -> Result<SidecarRuntimeConfig, SidecarError> {
        let launch_config = {
            let mut state = self.state.lock().expect("sidecar state poisoned");
            if let Some(mut child) = state.child.take() {
                let _ = post_shutdown(state.runtime_config.port, &state.token);
                if !wait_for_child_exit(&mut child, state.shutdown_timeout) {
                    let _ = kill_process_group(&mut child);
                }
            }
            state.launch_config.clone()
        };

        let attempts = launch_config.startup_attempts.max(1);
        let mut last_error = None;

        for _ in 0..attempts {
            let port = allocate_loopback_port()?;
            let api_token = generate_api_token();
            let stderr_lines = Arc::new(Mutex::new(VecDeque::with_capacity(STDERR_RING_LINES)));
            let mut child =
                spawn_sidecar_process(&launch_config, port, &api_token, Arc::clone(&stderr_lines))?;
            let child_pid = child.inner().id();

            if wait_for_health(port, launch_config.health_timeout, child_pid) {
                let runtime_config = SidecarRuntimeConfig::new(
                    port,
                    &launch_config.resource_dir,
                    &launch_config.config_dir,
                    &api_token,
                );
                let mut state = self.state.lock().expect("sidecar state poisoned");
                state.child = Some(child);
                state.token = api_token;
                state.runtime_config = runtime_config.clone();
                state.stderr_lines = stderr_lines;
                state.shutdown_timeout = launch_config.shutdown_timeout;
                // launch_config unchanged — keep the original layout.
                log::info!(
                    "sidecar: restart succeeded on port {port}; emitting {} to webview",
                    SIDECAR_RESTARTED_EVENT
                );
                return Ok(runtime_config);
            }

            let stderr = recent_stderr(&stderr_lines);
            let _ = kill_process_group(&mut child);
            last_error = Some(SidecarError::HealthTimeout { port, stderr });
        }

        Err(last_error
            .unwrap_or_else(|| SidecarError::SpawnFailed("sidecar did not restart".into())))
    }
}

/// Owns the *recipe* for a Python sidecar, and at most one sidecar made from it.
///
/// The separation is the entire point. An Erlang/OTP supervisor holds the child
/// spec, and systemd holds the unit file — in both cases outside the process
/// being supervised, which is exactly why `restart_child` and `systemctl
/// restart` work on a child that is not currently running. Before this type,
/// the launch recipe lived inside `SidecarManager`, and a `SidecarManager` can
/// only be constructed by a start that SUCCEEDED; a failed first boot therefore
/// destroyed the only means of trying again, and the app's Retry button had
/// nothing to call (problem ledger P2).
///
/// Corrected 2026-08-24 (dead-sidecar-says-so): this comment used to read
/// "Deliberately NOT borrowed from those systems: automatic restart policies
/// (`Restart=always`, restart intensity limits)." That was too broad. The
/// reasoning it gave — "the trigger here is a person pressing Retry; a
/// permanent failure would only get buried" — is a real objection to
/// `Restart=always` (retry forever, silently, hiding the error). It is NOT an
/// objection to an intensity limit, because a limit does the opposite of
/// hiding a permanent failure: it runs out and lands on a VISIBLE terminal
/// state with the failure's own text still attached. That is exactly what
/// `StartLimitBurst`/`StartLimitIntervalSec` (systemd) and `max_restarts`/
/// `max_seconds` (Erlang/OTP) are for — let a transient blip heal itself, then
/// stop and surface a permanent one instead of retrying it forever.
///
/// So `restart_automatic` below DOES borrow that half: at most
/// `AUTO_RESTART_MAX_ATTEMPTS` attempts inside `AUTO_RESTART_WINDOW`, then it
/// refuses outright until something resets the budget — no unbounded retry
/// loop ever runs, and RuntimeGate's persistent banner keeps showing the last
/// attempt's real error the whole time.
///
/// One thing is still deliberately NOT borrowed, and this is a genuine
/// departure from both reference systems rather than an oversight: systemd's
/// `StartLimitBurst` also blocks a subsequent MANUAL `systemctl restart` until
/// an operator runs `systemctl reset-failed`, and OTP escalates a spent budget
/// to the supervisor's own supervisor. Neither fits here — there is no second
/// operator and no supervisor above this one, only the same person looking at
/// the same Retry button that is on screen precisely so pressing it does
/// something. A manual `restart()` is therefore ALWAYS attempted (never
/// refused by the automatic budget) and resets that budget for a fresh
/// episode, so pressing Retry is never a dead click.
///
/// confirm-before-you-kill (2026-09-01): `restart_automatic` also CONFIRMS,
/// before it destroys anything, that the instance it is about to replace is
/// not still working (`SidecarManager::confirm_serving`). The confirmation
/// lives here, and could not live anywhere else, for two reasons that are
/// really one reason:
///
/// - **The check and the kill must be one indivisible step.** They are
///   performed under the same `state` lock, in the same critical section, so
///   nothing can swap the instance in between. The first attempt at this check
///   was in the frontend (`RuntimeGate`, deleted with this change), where the
///   two halves sat on opposite sides of a process boundary: a Tauri command
///   already sent cannot be recalled, so a manual Retry landing in that window
///   left the automatic path killing the healthy replacement it had never
///   examined.
/// - **A verdict has to be about a particular instance.** A port identifies
///   nobody — any local process can occupy one — so "something answered on that
///   port" was never "our sidecar answered", and being inside the supervisor
///   does not fix that by itself. `/health` therefore reports the answering
///   process's own pid (`apps/studio/backend/app/routers/system.py`), and the
///   gate requires it to equal the pid of the child this supervisor holds a
///   handle to. Three things then bind the verdict to one instance: the state
///   lock (nothing else may swap it), the process handle (`try_wait` asks the
///   OS about THIS child), and the answer naming that same child.
///
/// A refusal is not an error. It is `AutoRestartOutcome::Declined`, carrying
/// the live instance's own runtime config — see that variant for why the
/// distinction matters to the caller.
pub struct SidecarSupervisor {
    launch: SidecarLaunchConfig,
    state: Mutex<SupervisorState>,
}

/// Everything one restart decision reads or writes, behind ONE lock.
///
/// The budget used to have a lock of its own. That is a lock-order inversion
/// waiting to be written: a manual restart naturally resets the budget and then
/// touches the sidecar, while an automatic one must inspect the sidecar before
/// spending budget — opposite orders, two locks, and a deadlock the day both
/// run at once. Merging them removes the ordering question instead of
/// documenting an answer to it, and it is also what makes "confirm, decide,
/// act" a single critical section rather than three that happen to be adjacent.
struct SupervisorState {
    sidecar: SupervisedSidecar,
    /// Bookkeeping for `restart_automatic` ONLY — a manual `restart()` always
    /// attempts and resets this (see the `SidecarSupervisor` doc above).
    auto_restart_budget: AutoRestartBudget,
}

/// At most this many AUTOMATIC restart attempts (see `restart_automatic`)
/// inside `AUTO_RESTART_WINDOW`. Fixed backoff delays between attempts
/// (1s/4s/16s) are the CALLER's concern (RuntimeGate, in TypeScript) — this
/// module only enforces the count/window ceiling, independent of how fast or
/// slow the caller asks, exactly like a systemd unit's own start-limit is
/// independent of what is asking for the restart.
const AUTO_RESTART_MAX_ATTEMPTS: usize = 3;
/// Rolling ceiling on one automatic-restart episode. This does NOT renew once
/// spent — see `AutoRestartBudget::record_attempt_if_allowed` — so a sidecar
/// that is permanently broken gets exactly `AUTO_RESTART_MAX_ATTEMPTS` quiet
/// attempts and then stays in a visible failed state for good, until a person
/// presses Retry.
const AUTO_RESTART_WINDOW: Duration = Duration::from_secs(120);

/// Tracks one automatic-restart episode. `record_attempt_if_allowed` is the
/// only mutator: it either admits the attempt (incrementing the counter, and
/// opening the window on the first admitted attempt) or refuses outright,
/// leaving the counter untouched — a caller that keeps asking after being
/// refused keeps getting refused, it can never sneak in "one more" by asking
/// again immediately.
#[derive(Debug, Clone, Copy, Default)]
struct AutoRestartBudget {
    attempts_used: usize,
    window_started_at: Option<Instant>,
}

impl AutoRestartBudget {
    /// Admits the attempt and returns `true`, or refuses and returns `false`.
    /// Refusal is permanent for this episode: once the attempt cap or the
    /// window is hit, EVERY later call (even long after the window would have
    /// "reset") keeps refusing. The window is an early-exit on top of the
    /// attempt cap, not a rate limiter that reopens on a timer — reopening on
    /// a timer is exactly the quiet-forever-retry shape the struct doc above
    /// rejects. Only `SidecarSupervisor::restart` (a manual retry) resets it.
    fn record_attempt_if_allowed(&mut self, now: Instant) -> bool {
        if self.attempts_used >= AUTO_RESTART_MAX_ATTEMPTS {
            return false;
        }
        let window_start = *self.window_started_at.get_or_insert(now);
        if now.duration_since(window_start) >= AUTO_RESTART_WINDOW {
            return false;
        }
        self.attempts_used += 1;
        true
    }
}

/// What one `restart_automatic` call produced, for the Tauri command layer to
/// translate into whatever the frontend contract needs.
#[derive(Debug)]
pub enum AutoRestartOutcome {
    /// A real attempt was made and it produced a running sidecar.
    Restarted(SidecarRuntimeConfig),
    /// The confirmation found the supervised instance still alive and serving,
    /// so nothing was touched. Carries THAT instance's runtime config — the
    /// one read under the lock at the moment of the decision.
    ///
    /// Why a distinct outcome rather than an `Err`. The caller asked for a
    /// restart because its connection to the sidecar broke, and the honest
    /// answer is not "your request failed" but "the sidecar is fine; your
    /// connection is what needs repairing, and here is where it is". An `Err`
    /// would be rendered by the frontend as the failed-attempt banner and would
    /// schedule the next attempt on the backoff — treating a healthy sidecar as
    /// a failure, which is the whole class of behaviour this gate exists to
    /// stop. Shipping the config with the refusal is also what makes the
    /// caller's repair one step: applying it rotates the bearer token, which is
    /// the single most likely reason a live sidecar looks dead from the UI
    /// (`/health` needs no token; every other call does).
    Declined(SidecarRuntimeConfig),
    /// The budget was already spent — no process was touched at all.
    BudgetExhausted,
    /// A real attempt was made (the budget admitted it) and it failed.
    Failed(String),
}

/// Either there is a sidecar, or there isn't and this is what the last attempt
/// to have one said. Never both, never neither.
enum SupervisedSidecar {
    Running(SidecarManager),
    Absent(String),
}

/// What `restart` produced, before it is committed to the state.
enum Attempt {
    /// The live sidecar rebuilt its own process group; the manager stays put.
    InPlace(SidecarRuntimeConfig),
    /// A sidecar was started from scratch and still has to be installed.
    Fresh(SidecarManager),
}

impl SidecarSupervisor {
    /// Attempt a first sidecar. Never fails: a failure to start is a state the
    /// supervisor can be in and recover from, not a reason to have no supervisor.
    pub fn start(launch: SidecarLaunchConfig) -> Self {
        let sidecar = match SidecarManager::start(launch.clone()) {
            Ok(manager) => SupervisedSidecar::Running(manager),
            Err(error) => {
                SupervisedSidecar::Absent(format!("failed to start Python sidecar: {error}"))
            }
        };
        Self {
            launch,
            state: Mutex::new(SupervisorState {
                sidecar,
                auto_restart_budget: AutoRestartBudget::default(),
            }),
        }
    }

    pub fn runtime_config(&self) -> Result<SidecarRuntimeConfig, String> {
        match &self.state.lock().expect("sidecar state poisoned").sidecar {
            SupervisedSidecar::Running(manager) => Ok(manager.runtime_config()),
            SupervisedSidecar::Absent(error) => Err(error.clone()),
        }
    }

    /// Get a sidecar, whether or not one is running — restart the live one, or
    /// start the first one. Either way the outcome REPLACES what is recorded,
    /// so whatever a caller reads afterwards is this attempt's own result and
    /// not a verdict frozen at boot.
    ///
    /// A person pressing Retry. ALWAYS attempts — never refused by the
    /// automatic budget (struct doc above), and never refused by the
    /// confirmation either: someone who can see the app is asking for this
    /// sidecar to be replaced, and "but it answers `/health`" is not an answer
    /// to a person who has already concluded otherwise. The confirmation exists
    /// to keep the app from destroying a working sidecar on evidence it cannot
    /// interpret; a human pressing a button is not that. It also resets the
    /// automatic budget, so this is how a fresh automatic episode begins after
    /// one ran out.
    pub fn restart(&self) -> Result<SidecarRuntimeConfig, String> {
        let mut state = self.state.lock().expect("sidecar state poisoned");
        state.auto_restart_budget = AutoRestartBudget::default();
        self.perform_restart(&mut state.sidecar)
    }

    /// Studio's OWN bounded recovery attempt after the sidecar goes down
    /// without anyone touching Retry (RuntimeGate's WS-drop / HTTP-failure
    /// liveness signals — `apps/studio/frontend/src/components/RuntimeGate.tsx`).
    /// The frontend already paces these with its own 1s/4s/16s backoff and
    /// stops asking after `AUTO_RESTART_MAX_ATTEMPTS`; this method enforces the
    /// SAME ceiling independently of that caller, exactly like a systemd unit's
    /// start-limit is enforced by the unit rather than by whoever asked for the
    /// restart — see the struct doc for why that borrowing stops at the count/
    /// window ceiling and does not extend to blocking a manual retry.
    ///
    /// The caller's evidence for "the sidecar died" is weak — a websocket that
    /// dropped, or an HTTP call that got no response, neither of which can tell
    /// a dead process apart from a rotated token or a discarded CORS reply — so
    /// this method does not take it on trust. It CONFIRMS first, and the whole
    /// decision (confirm, budget, act) happens inside ONE hold of the state
    /// lock, which is what makes "the sidecar I examined" and "the sidecar I
    /// replaced" provably the same instance (struct doc above).
    ///
    /// The price is that the lock is held across the confirmation's network
    /// wait, so a concurrent `get_sidecar_config` or a manual `restart` waits
    /// up to `CONFIRM_SERVING_REQUEST_TIMEOUT` for it. That is the same lock a
    /// restart already holds for as long as a sidecar takes to boot, and the
    /// alternative — releasing it between the check and the act — is precisely
    /// the defect being fixed.
    pub fn restart_automatic(&self) -> AutoRestartOutcome {
        let mut state = self.state.lock().expect("sidecar state poisoned");

        if let SupervisedSidecar::Running(manager) = &state.sidecar {
            if manager.confirm_serving(CONFIRM_SERVING_REQUEST_TIMEOUT) {
                return AutoRestartOutcome::Declined(manager.runtime_config());
            }
        }

        // Budget AFTER the confirmation, so a refusal costs nothing. The budget
        // bounds ATTEMPTS — restarts that actually happened — and a decline is
        // the absence of one. Charging for it would let a healthy sidecar the
        // UI keeps mistrusting (a rotated token does exactly that) drain the
        // budget it never used, and the next REAL death would then find nothing
        // left and refuse to recover.
        if !state
            .auto_restart_budget
            .record_attempt_if_allowed(Instant::now())
        {
            return AutoRestartOutcome::BudgetExhausted;
        }
        match self.perform_restart(&mut state.sidecar) {
            Ok(runtime_config) => AutoRestartOutcome::Restarted(runtime_config),
            Err(error) => AutoRestartOutcome::Failed(error),
        }
    }

    /// The actual restart-or-start attempt, shared by `restart` and
    /// `restart_automatic` — everything above this line is only about WHETHER
    /// an attempt is allowed, never about how the attempt itself works.
    ///
    /// Takes the already-locked state rather than locking: both callers have
    /// decided something about the instance in `state` and must act on THAT
    /// instance, which is only guaranteed while the lock they made the decision
    /// under is still held.
    fn perform_restart(
        &self,
        state: &mut SupervisedSidecar,
    ) -> Result<SidecarRuntimeConfig, String> {
        let attempt = match &*state {
            SupervisedSidecar::Running(manager) => manager
                .restart()
                .map(Attempt::InPlace)
                .map_err(|error| format!("failed to restart Python sidecar: {error}")),
            SupervisedSidecar::Absent(_) => SidecarManager::start(self.launch.clone())
                .map(Attempt::Fresh)
                .map_err(|error| format!("failed to start Python sidecar: {error}")),
        };
        match attempt {
            Ok(Attempt::InPlace(runtime_config)) => Ok(runtime_config),
            Ok(Attempt::Fresh(manager)) => {
                let runtime_config = manager.runtime_config();
                *state = SupervisedSidecar::Running(manager);
                Ok(runtime_config)
            }
            Err(error) => {
                *state = SupervisedSidecar::Absent(error.clone());
                Err(error)
            }
        }
    }

    /// Recent sidecar stderr, or — with no sidecar to have written any — the
    /// reason there isn't one. Both answer the same operator question.
    pub fn recent_stderr(&self) -> Vec<String> {
        match &self.state.lock().expect("sidecar state poisoned").sidecar {
            SupervisedSidecar::Running(manager) => manager.recent_stderr(),
            SupervisedSidecar::Absent(error) => error.lines().map(str::to_string).collect(),
        }
    }

    pub fn shutdown_blocking(&self) {
        let mut state = self.state.lock().expect("sidecar state poisoned");
        if let SupervisedSidecar::Running(manager) = &state.sidecar {
            manager.shutdown_blocking();
        }
        state.sidecar = SupervisedSidecar::Absent("Python sidecar was shut down".to_string());
    }
}

pub fn default_tauri_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

pub fn default_user_config_dir() -> PathBuf {
    if cfg!(target_os = "macos") {
        if let Some(home) = std::env::var_os("HOME") {
            return PathBuf::from(home)
                .join("Library")
                .join("Application Support")
                .join("AgentStudio");
        }
    }
    if cfg!(target_os = "windows") {
        if let Some(appdata) = std::env::var_os("APPDATA") {
            return PathBuf::from(appdata).join("AgentStudio");
        }
    }
    if let Some(home) = std::env::var_os("HOME") {
        return PathBuf::from(home)
            .join(".local")
            .join("share")
            .join("AgentStudio");
    }
    default_tauri_dir()
        .join("vendor")
        .join("resources")
        .join("config")
}

pub fn resource_root_for_runtime(resolved_resource_root: PathBuf) -> PathBuf {
    resource_root_for_runtime_mode(resolved_resource_root, cfg!(debug_assertions))
}

fn resource_root_for_runtime_mode(
    resolved_resource_root: PathBuf,
    debug_assertions: bool,
) -> PathBuf {
    if debug_assertions {
        return default_tauri_dir();
    }
    if resolved_resource_root.join("vendor").exists() {
        resolved_resource_root
    } else {
        default_tauri_dir()
    }
}

pub fn allocate_loopback_port() -> std::io::Result<u16> {
    // Honor STUDIO_SIDECAR_PORT if the launcher (or apps/studio/frontend/.env.local
    // sourced via the dev shell) pinned a port. This lets the vite proxy target
    // (which is bound at vite startup, before the sidecar has even spawned) line
    // up with the sidecar's actual listening port — fixing the 502s when the
    // browser opens 127.0.0.1:5173 in dev tunnel mode (R-F2).
    allocate_loopback_port_from(std::env::var("STUDIO_SIDECAR_PORT").ok().as_deref())
}

// The env read stays in the one-line wrapper above so this decision logic is a
// pure function of its input: process env is global mutable state, and tests
// mutating it raced each other under cargo's parallel runner (the pinned-port
// test saw another test's remove_var and got a dynamic port instead).
fn allocate_loopback_port_from(pinned_env: Option<&str>) -> std::io::Result<u16> {
    if let Some(value) = pinned_env {
        let trimmed = value.trim();
        if !trimmed.is_empty() {
            match trimmed.parse::<u16>() {
                Ok(pinned) if pinned > 0 => {
                    log::info!(
                        "sidecar: using pinned STUDIO_SIDECAR_PORT={} from env",
                        pinned
                    );
                    return Ok(pinned);
                }
                Ok(_) => {
                    log::warn!(
                        "sidecar: ignoring STUDIO_SIDECAR_PORT=0; falling back to dynamic port"
                    );
                }
                Err(err) => {
                    log::warn!(
                        "sidecar: invalid STUDIO_SIDECAR_PORT={:?} ({}); falling back to dynamic port",
                        value,
                        err
                    );
                }
            }
        }
    }
    let listener = TcpListener::bind(("127.0.0.1", 0))?;
    Ok(listener.local_addr()?.port())
}

/// `--workers 1` is load-bearing, not decoration. The supervisor attributes a
/// `/health` answer by comparing the pid in it against the pid of the child it
/// spawned (`health_probe_once`), and that only holds while the process serving
/// the app IS that child. Uvicorn runs the server in a SEPARATE process as soon
/// as workers exceed one, and — this is the part that made the old code wrong —
/// leaving the flag off does not mean one worker, it means *the environment
/// decides*: `Config` falls back to `WEB_CONCURRENCY` when `--workers` was not
/// passed. A single inherited variable was therefore enough to make every
/// startup health wait time out. Passing the flag makes the premise a property
/// of the launch rather than of whatever shell happened to start the app;
/// command-line arguments also beat click's env lookups, so this cannot be
/// overridden by `UVICORN_WORKERS` either (and `sidecar_command` strips those
/// anyway — belt and braces, because each guards a different way in).
///
/// Verified against uvicorn 0.46.0's dispatch: `workers == 1` and no reload
/// takes the plain `server.run()` path, i.e. no supervisor process at all.
pub fn uvicorn_args(port: u16) -> Vec<String> {
    [
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        &port.to_string(),
        "--workers",
        "1",
    ]
    .into_iter()
    .map(String::from)
    .collect()
}

pub fn python_executable_path(tauri_dir: &Path) -> PathBuf {
    let runtime_dir = python_runtime_dir(tauri_dir);
    if cfg!(windows) {
        runtime_dir.join("python.exe")
    } else {
        let python = runtime_dir.join("bin").join("python3.12");
        if python.exists() {
            python
        } else {
            runtime_dir.join("bin").join("python")
        }
    }
}

/// Where the portable CPython lives, under a dev tree and inside a packaged app
/// alike. `scripts/download_runtime.js` unpacks it to `vendor/python/<triple>`
/// and `tauri.conf.json` ships `vendor/**/*`, so one name covers both.
///
/// Deliberately not a search over alternatives. Two other names — `vendor/
/// python_runtime` and a bare `python_runtime` — were tried first and probed
/// here for years after nothing produced them any more, which made a leftover
/// directory at either name outrank the real runtime whenever the real one was
/// missing: the sidecar would then start from whatever a stale tree held
/// instead of failing with the path it actually wanted.
pub fn python_runtime_dir(resource_root: &Path) -> PathBuf {
    resource_root
        .join("vendor")
        .join("python")
        .join(host_target_triple())
}

fn host_target_triple() -> &'static str {
    match (std::env::consts::OS, std::env::consts::ARCH) {
        ("macos", "x86_64") => "x86_64-apple-darwin",
        ("macos", "aarch64") => "aarch64-apple-darwin",
        ("linux", "x86_64") => "x86_64-unknown-linux-gnu",
        ("linux", "aarch64") => "aarch64-unknown-linux-gnu",
        ("windows", "x86_64") => "x86_64-pc-windows-msvc",
        _ => "x86_64-unknown-linux-gnu",
    }
}

/// Env switches that let the ambient shell rewrite the sidecar's launch, and so
/// must not be inherited.
///
/// Checked against uvicorn 0.46.0's own source rather than assumed:
/// `config.py` reads `WEB_CONCURRENCY` whenever `--workers` was not passed
/// (`if workers is None and "WEB_CONCURRENCY" in os.environ`), and `main.py`
/// declares its CLI with `auto_envvar_prefix="UVICORN"`, which makes EVERY
/// option settable as `UVICORN_<OPTION>` — `UVICORN_WORKERS`, `UVICORN_RELOAD`,
/// `UVICORN_FACTORY` included.
///
/// Two of those change the PROCESS MODEL, which is what this supervisor's whole
/// identity story rests on: with workers > 1 or reload on, uvicorn runs a
/// supervisor process that spawns the server elsewhere (`main.py`:
/// `if config.should_reload: ChangeReload(...) elif config.workers > 1:
/// Multiprocess(...) else: server.run()`). The child handle would then point at
/// that supervisor while `/health` answered with a worker's pid — the pid could
/// never match, so startup would time out three times over and the app would
/// simply not come up.
///
/// Command-line arguments beat click's env lookups, so the switches we DO pass
/// explicitly are already safe; the residue is the ones we do not pass. Rather
/// than maintain a list of those and re-audit it at every uvicorn upgrade, this
/// strips the whole `UVICORN_` namespace plus `WEB_CONCURRENCY` (which does not
/// carry the prefix). The launch is then a function of `SidecarLaunchConfig`
/// alone, which is the property worth having independent of any one option.
fn env_key_rewrites_uvicorn_launch(key: &str) -> bool {
    let key = key.to_ascii_uppercase();
    key == "WEB_CONCURRENCY" || key.starts_with("UVICORN_")
}

/// Removed unconditionally, so the guarantee does not depend on what happened to
/// be set in the parent when the command was built — and so a test can observe
/// it without mutating process-global env (which races cargo's parallel runner;
/// see the note above `python_runtime_dir_names_one_place_and_ignores_retired_names`).
const UVICORN_ENV_OVERRIDES_ALWAYS_STRIPPED: [&str; 4] = [
    "WEB_CONCURRENCY",
    "UVICORN_WORKERS",
    "UVICORN_RELOAD",
    "UVICORN_FACTORY",
];

/// The sidecar's launch, as a value. Separated from the spawn so the recipe can
/// be asserted without starting a Python interpreter.
fn sidecar_command(config: &SidecarLaunchConfig, port: u16, api_token: &str) -> Command {
    let mut command = Command::new(&config.python);
    command
        .args(uvicorn_args(port))
        .current_dir(&config.backend_dir)
        .env(
            "PYTHONPATH",
            python_path_env(&config.site_packages, &config.backend_dir),
        )
        .env("PATH", sidecar_path_env(&config.site_packages))
        .env("STUDIO_RESOURCE_DIR", &config.resource_dir)
        .env("STUDIO_CONFIG_DIR", &config.config_dir)
        .env("STUDIO_API_TOKEN", api_token)
        .env("STUDIO_CORS_EXTRA_ORIGINS", sidecar_cors_extra_origins())
        .env("STUDIO_EXIT_ON_ORPHAN", "1")
        // Cross-platform bottom line (docs/development/CROSS_PLATFORM.md):
        // the sidecar writes UTF-8 stdout/stderr on every host locale, so the
        // from_utf8_lossy readers below never mangle non-ASCII log lines.
        .env("PYTHONUTF8", "1")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    for key in UVICORN_ENV_OVERRIDES_ALWAYS_STRIPPED {
        command.env_remove(key);
    }
    for (key, _) in std::env::vars_os() {
        if env_key_rewrites_uvicorn_launch(&key.to_string_lossy()) {
            command.env_remove(&key);
        }
    }

    command
}

fn spawn_sidecar_process(
    config: &SidecarLaunchConfig,
    port: u16,
    api_token: &str,
    stderr_lines: Arc<Mutex<VecDeque<String>>>,
) -> Result<GroupChild, SidecarError> {
    let mut command = sidecar_command(config, port, api_token);

    let mut child = command.group_spawn().map_err(|err| {
        SidecarError::SpawnFailed(format!("failed to spawn Python sidecar: {err}"))
    })?;

    if let Some(stderr) = child.inner().stderr.take() {
        capture_lines(stderr, stderr_lines);
    }
    if let Some(stdout) = child.inner().stdout.take() {
        capture_stdout(stdout);
    }

    Ok(child)
}

fn python_path_env(site_packages: &Path, backend_dir: &Path) -> OsString {
    let mut entries = vec![site_packages.to_path_buf()];
    if cfg!(windows) {
        entries.extend(pywin32_python_path_entries(site_packages));
    }
    entries.push(backend_dir.to_path_buf());
    if let Some(existing) = std::env::var_os("PYTHONPATH") {
        entries.extend(std::env::split_paths(&existing));
    }
    std::env::join_paths(entries).expect("PYTHONPATH entries must be valid")
}

fn pywin32_python_path_entries(site_packages: &Path) -> Vec<PathBuf> {
    [
        site_packages.join("win32"),
        site_packages.join("win32").join("lib"),
    ]
    .into_iter()
    .filter(|path| path.exists())
    .collect()
}

fn sidecar_path_env(site_packages: &Path) -> OsString {
    let mut entries = Vec::new();
    if cfg!(windows) {
        let pywin32_system32 = site_packages.join("pywin32_system32");
        if pywin32_system32.exists() {
            entries.push(pywin32_system32);
        }
    }
    if let Some(existing) = std::env::var_os("PATH") {
        entries.extend(std::env::split_paths(&existing));
    }
    std::env::join_paths(entries).expect("PATH entries must be valid")
}

fn sidecar_cors_extra_origins() -> String {
    let mut origins = vec![
        "http://localhost:5174".to_string(),
        "http://127.0.0.1:5174".to_string(),
    ];
    if let Ok(existing) = std::env::var("STUDIO_CORS_EXTRA_ORIGINS") {
        origins.extend(
            existing
                .split(',')
                .map(str::trim)
                .filter(|origin| !origin.is_empty())
                .map(str::to_string),
        );
    }
    origins.sort();
    origins.dedup();
    origins.join(",")
}

fn capture_lines(stream: impl std::io::Read + Send + 'static, sink: Arc<Mutex<VecDeque<String>>>) {
    thread::spawn(move || {
        for line in BufReader::new(stream).lines().map_while(Result::ok) {
            let mut lines = sink.lock().expect("stderr ring poisoned");
            if lines.len() == STDERR_RING_LINES {
                lines.pop_front();
            }
            lines.push_back(line);
        }
    });
}

fn capture_stdout(stream: impl std::io::Read + Send + 'static) {
    thread::spawn(move || {
        for line in BufReader::new(stream).lines().map_while(Result::ok) {
            log::info!("python sidecar: {line}");
        }
    });
}

/// What `/health` answers (`apps/studio/backend/app/routers/system.py`). `pid`
/// is REQUIRED here: an answer that does not name the process that produced it
/// cannot be attributed to anything, so it does not count as an answer at all
/// and this struct refuses to deserialize it.
#[derive(Deserialize)]
struct HealthAnswer {
    pid: u32,
}

/// The ONE definition of "the process I mean is serving on this port": its own
/// `/health` endpoint answered with a SUCCESS status AND named itself as
/// `expected_pid`.
///
/// One request, one verdict — no polling, no retry. Every caller that wants
/// repetition builds it on top (`wait_for_health` below loops; the destruction
/// gate lets the frontend's 1s/4s/16s schedule provide the repetition), so the
/// threshold, the URL and the identity rule exist in exactly one place and
/// cannot drift between the question "has the process I just launched come up"
/// and the question "is the process I am about to kill still working".
///
/// **Identity, because a port identifies nobody.** A loopback port is a
/// rendezvous any local process can occupy. Without the pid, "something
/// answered 200 there" was compatible with a case that is fully reachable: the
/// child is alive but its listener is gone and an unrelated process now holds
/// the port. The destruction gate would then spare a sidecar that cannot serve
/// and hand the frontend a config for it, and the frontend — being told this is
/// recovery — would clear the banner and stop retrying. A live process reporting
/// its own pid is the OS's own answer to "who are you", and the supervisor
/// already holds the other half in the child handle.
///
/// Deliberately the pid rather than a launch nonce we inject and echo. Both bind
/// the answer to something; the pid binds it to the PROCESS, needs no new state
/// plumbed through the spawn, and puts no value that looks like a credential in
/// an unauthenticated response.
///
/// Its one assumption is that the process serving `/health` IS the child we
/// spawned, and that assumption is now ENFORCED at the launch boundary rather
/// than hoped for: `uvicorn_args` passes `--workers 1`, and `sidecar_command`
/// strips the inherited env switches that would change the process model. This
/// comment previously argued the premise held "because there is no `--workers`
/// flag" — which was exactly wrong, because a missing flag hands the decision to
/// `WEB_CONCURRENCY` instead of settling it (uvicorn `config.py`). A single
/// inherited variable made every startup health wait time out; a default is not
/// a guarantee. If a future design genuinely needs multiple workers, the pid
/// stops being the right identifier and the replacement is a nonce injected at
/// spawn, which workers inherit — and until then, mismatched pids fail toward
/// restarting rather than falsely sparing.
///
/// `is_success()` is the status threshold, and it is now the only one in the
/// tree. A looser "any HTTP reply counts" reading used to live in the frontend
/// probe this replaced, on the argument that a 503 at least proves a process is
/// alive. Inside the supervisor that argument has nothing left to do: liveness
/// is established by the process handle (`confirm_serving`), exactly, and
/// without inference from network behaviour. What remains for the probe is
/// whether a live child can still SERVE — and an alive-but-not-serving child is
/// precisely what an automatic restart is for. systemd's `WatchdogSec` draws
/// the same line: a service still running but no longer answering gets
/// restarted, not spared.
fn health_probe_once(
    client: &reqwest::blocking::Client,
    port: u16,
    timeout: Duration,
    expected_pid: u32,
) -> bool {
    let Ok(response) = client
        .get(format!("http://127.0.0.1:{port}/health"))
        .timeout(timeout)
        .send()
    else {
        return false;
    };
    if !response.status().is_success() {
        return false;
    }
    let Ok(body) = response.text() else {
        return false;
    };
    serde_json::from_str::<HealthAnswer>(&body).is_ok_and(|answer| answer.pid == expected_pid)
}

/// Poll until the process `expected_pid` answers for itself on `port`, or the
/// budget runs out. The identity requirement matters here too, and for a case
/// that actually happens: with `STUDIO_SIDECAR_PORT` pinned, a leftover sidecar
/// from an earlier run can still hold the port, our fresh child then fails to
/// bind and exits, and an identity-blind wait would read the ORPHAN's 200 as
/// "my sidecar came up" — leaving the supervisor believing it owns a process it
/// never started, whose token nothing here knows.
fn wait_for_health(port: u16, timeout: Duration, expected_pid: u32) -> bool {
    let client = reqwest::blocking::Client::new();
    let deadline = Instant::now() + timeout;

    while Instant::now() < deadline {
        if health_probe_once(&client, port, HEALTH_POLL_REQUEST_TIMEOUT, expected_pid) {
            return true;
        }
        thread::sleep(HEALTH_POLL_INTERVAL);
    }

    false
}

fn post_shutdown(port: u16, token: &str) -> Result<(), reqwest::Error> {
    let client = reqwest::blocking::Client::new();
    client
        .post(format!("http://127.0.0.1:{port}/shutdown"))
        .bearer_auth(token)
        .timeout(Duration::from_millis(500))
        .send()
        .map(|_| ())
}

fn wait_for_child_exit(child: &mut GroupChild, timeout: Duration) -> bool {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if child.try_wait().is_ok_and(|status| status.is_some()) {
            return true;
        }
        thread::sleep(Duration::from_millis(50));
    }
    false
}

fn kill_process_group(child: &mut GroupChild) -> std::io::Result<()> {
    match child.try_wait()? {
        Some(_) => Ok(()),
        None => {
            child.kill()?;
            let _ = child.wait();
            Ok(())
        }
    }
}

fn recent_stderr(stderr_lines: &Arc<Mutex<VecDeque<String>>>) -> Vec<String> {
    stderr_lines
        .lock()
        .expect("stderr ring poisoned")
        .iter()
        .cloned()
        .collect()
}

fn generate_api_token() -> String {
    rand::rng()
        .sample_iter(Alphanumeric)
        .take(64)
        .map(char::from)
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Read, Write};
    use std::sync::atomic::{AtomicBool, Ordering as AtomicOrdering};

    // These feed allocate_loopback_port_from explicit input instead of mutating
    // STUDIO_SIDECAR_PORT: process env is shared by every test thread, and the
    // set/remove dance raced under cargo's parallel runner (CI 2026-08-14: the
    // pinned test observed a sibling's remove_var and got a dynamic port).
    /// A directory parked at either retired runtime name must not outrank the
    /// one place the interpreter is actually vendored. The decoy stands where
    /// a tree that once used the old layout would leave one, and the real
    /// `vendor/python/<triple>` is absent — the case where a search would take
    /// the bait and hand the sidecar a stale interpreter instead of failing
    /// with the path it wanted.
    #[test]
    fn python_runtime_dir_names_one_place_and_ignores_retired_names() {
        let root = std::env::temp_dir().join(format!("studio-runtime-dir-{}", std::process::id()));
        let triple = host_target_triple();
        for retired in [
            root.join("vendor").join("python_runtime").join(triple),
            root.join("python_runtime").join(triple),
        ] {
            std::fs::create_dir_all(&retired).expect("decoy runtime dir");
        }

        let resolved = python_runtime_dir(&root);

        assert_eq!(resolved, root.join("vendor").join("python").join(triple));
        std::fs::remove_dir_all(&root).ok();
    }

    #[test]
    fn allocate_loopback_port_returns_bindable_dynamic_port() {
        let port = allocate_loopback_port_from(None).expect("port");
        assert_ne!(port, 0);
        let listener = TcpListener::bind(("127.0.0.1", port)).expect("released port should rebind");
        drop(listener);
    }

    #[test]
    fn allocate_loopback_port_honors_pinned_env() {
        let port = allocate_loopback_port_from(Some("49317")).expect("port");
        assert_eq!(port, 49317);
    }

    #[test]
    fn allocate_loopback_port_falls_back_on_invalid_env() {
        let port = allocate_loopback_port_from(Some("not-a-number")).expect("port");
        assert_ne!(port, 0);
    }

    #[test]
    fn uvicorn_args_pass_dynamic_port_without_8787_default() {
        let args = uvicorn_args(43210);
        assert!(args.contains(&"43210".to_string()));
        assert!(!args.contains(&"8787".to_string()));
        assert_eq!(args[0], "-m");
        assert_eq!(args[1], "uvicorn");
    }

    #[test]
    fn uvicorn_args_pin_one_worker_so_the_environment_cannot_add_more() {
        // The pid comparison in `health_probe_once` is only sound while the
        // process serving the app is the child we spawned. Uvicorn moves the
        // server into a separate process as soon as workers exceed one, and
        // omitting `--workers` does not mean "one" — it means `WEB_CONCURRENCY`
        // decides (uvicorn `config.py`). With `WEB_CONCURRENCY=2` inherited, the
        // handle pointed at a supervisor while `/health` answered with a
        // worker's pid: no match, ever, so all three startup attempts timed out
        // and the app did not come up at all.
        let args = uvicorn_args(43210);
        let workers = args
            .iter()
            .position(|arg| arg == "--workers")
            .expect("the worker count must be pinned on the command line");
        assert_eq!(args.get(workers + 1), Some(&"1".to_string()));
    }

    #[test]
    fn env_key_rewrites_uvicorn_launch_names_the_process_model_switches() {
        // uvicorn 0.46.0 declares its CLI with `auto_envvar_prefix="UVICORN"`,
        // so every option has an env twin; `WEB_CONCURRENCY` is the one that
        // does not carry the prefix. Case-insensitive because Windows env keys
        // are, and Python upper-cases them in `os.environ` on that platform.
        for rewrites in [
            "WEB_CONCURRENCY",
            "web_concurrency",
            "UVICORN_WORKERS",
            "UVICORN_RELOAD",
            "UVICORN_FACTORY",
            "uvicorn_reload",
        ] {
            assert!(
                env_key_rewrites_uvicorn_launch(rewrites),
                "{rewrites} can rewrite the launch and must not be inherited"
            );
        }
        // The sidecar's OWN configuration travels this way and must survive.
        for keeps in [
            "PYTHONPATH",
            "PYTHONUTF8",
            "PATH",
            "STUDIO_API_TOKEN",
            "STUDIO_CONFIG_DIR",
            "STUDIO_SIDECAR_PORT",
            "WEB_CONCURRENCY_LIMIT",
        ] {
            assert!(
                !env_key_rewrites_uvicorn_launch(keeps),
                "{keeps} is ours to set, not an inherited override"
            );
        }
    }

    #[test]
    fn sidecar_command_strips_the_env_switches_that_would_change_the_process_model() {
        // Asserted on the built command rather than by setting the variable for
        // real: process env is shared by every test thread and the set/remove
        // dance raced under cargo's parallel runner (see the note at the top of
        // this module). The removals are unconditional precisely so this is
        // observable without touching the environment.
        let command = sidecar_command(&unstartable_launch_config(), 45999, "token");
        let removed: Vec<String> = command
            .get_envs()
            .filter(|(_, value)| value.is_none())
            .map(|(key, _)| key.to_string_lossy().to_ascii_uppercase())
            .collect();

        for switch in UVICORN_ENV_OVERRIDES_ALWAYS_STRIPPED {
            assert!(
                removed.contains(&switch.to_string()),
                "{switch} must be removed from the child's environment; removed: {removed:?}"
            );
        }

        // And the sidecar's own environment is still handed over.
        let provided: Vec<String> = command
            .get_envs()
            .filter(|(_, value)| value.is_some())
            .map(|(key, _)| key.to_string_lossy().to_string())
            .collect();
        for own in ["STUDIO_API_TOKEN", "PYTHONPATH", "PYTHONUTF8"] {
            assert!(
                provided.contains(&own.to_string()),
                "{own} went missing from the launch"
            );
        }
    }

    #[test]
    fn api_token_is_generated_and_64_chars_alphanumeric() {
        let token = generate_api_token();
        assert_eq!(token.len(), 64);
        assert!(token.chars().all(|ch| ch.is_ascii_alphanumeric()));
    }

    #[test]
    fn health_wait_times_out_for_closed_port() {
        // A dynamic port explicitly: this test only needs a free port, and must
        // not pick up a pinned env value that might actually be listening.
        let port = allocate_loopback_port_from(None).expect("port");
        assert!(!wait_for_health(
            port,
            Duration::from_millis(20),
            std::process::id()
        ));
    }

    #[test]
    fn runtime_config_uses_dynamic_http_and_ws_urls() {
        let config = SidecarRuntimeConfig::new(
            45678,
            Path::new("/tmp/studio-resource"),
            Path::new("/tmp/studio-config"),
            "token",
        );
        assert_eq!(config.base_url, "http://127.0.0.1:45678/api");
        assert_eq!(config.ws_url, "ws://127.0.0.1:45678/ws");
        assert_eq!(config.resource_dir, "/tmp/studio-resource");
        assert_eq!(config.config_dir, "/tmp/studio-config");
        assert_eq!(config.api_token, "token");
    }

    #[test]
    fn launch_config_uses_resource_root_layout() {
        let config = SidecarLaunchConfig::from_resource_root(Path::new("/app/resources"));
        if cfg!(debug_assertions) {
            assert!(config.backend_dir.ends_with("apps/studio/backend"));
        } else {
            assert_eq!(
                config.backend_dir,
                Path::new("/app/resources/vendor/backend")
            );
        }
        assert_eq!(
            config.site_packages,
            Path::new("/app/resources/vendor/site-packages")
        );
        assert_eq!(
            config.resource_dir,
            Path::new("/app/resources/vendor/resources")
        );
        assert_eq!(
            config.config_dir,
            Path::new("/app/resources/vendor/resources/config")
        );
        assert_eq!(
            config
                .clone()
                .with_config_dir(PathBuf::from("/tmp/studio-config"))
                .config_dir,
            Path::new("/tmp/studio-config")
        );
    }

    /// A launch recipe that provably cannot produce a sidecar: the interpreter
    /// path does not exist, so `spawn` fails immediately instead of waiting out
    /// a health timeout. One attempt, so a failure costs nothing.
    fn unstartable_launch_config() -> SidecarLaunchConfig {
        let mut config = SidecarLaunchConfig::from_resource_root(Path::new("/nowhere/studio"));
        config.python = PathBuf::from("/nowhere/studio/definitely-not-an-interpreter");
        config.backend_dir = std::env::temp_dir();
        config.startup_attempts = 1;
        config.health_timeout = Duration::from_millis(10);
        config
    }

    #[test]
    fn retrying_a_sidecar_that_never_started_attempts_a_start() {
        // P2: the whole defect in one assertion. The supervisor owns the launch
        // recipe, so "start one" is reachable even when there is no process to
        // restart. Before this, the recipe lived inside a SidecarManager that
        // only a SUCCESSFUL start could produce — so a first start that failed
        // took the recipe with it, and retry could only refuse.
        let supervisor = SidecarSupervisor::start(unstartable_launch_config());
        assert!(supervisor.runtime_config().is_err());

        let error = supervisor
            .restart()
            .expect_err("this recipe cannot produce a sidecar");

        assert!(
            error.contains("failed to spawn"),
            "retry should report what THIS attempt hit; got: {error}"
        );
        assert!(
            !error.contains("is not running"),
            "retry refused to try instead of trying: {error}"
        );
    }

    #[test]
    fn the_reported_error_is_the_latest_attempts_own() {
        // What the banner shows must be what just happened. The original bug was
        // a startup error frozen at first-boot: every retry re-read the same
        // string, which is what "点了没反应" actually looked like.
        let supervisor = SidecarSupervisor::start(unstartable_launch_config());
        let retry_error = supervisor.restart().expect_err("cannot start");

        assert_eq!(
            supervisor.runtime_config().expect_err("still no sidecar"),
            retry_error,
        );
    }

    #[test]
    fn a_supervisor_with_no_sidecar_still_answers_for_stderr() {
        // The stderr surface reads through the same supervisor; with nothing
        // spawned there is no captured output, only the failure to report.
        let supervisor = SidecarSupervisor::start(unstartable_launch_config());
        assert!(!supervisor.recent_stderr().is_empty());
    }

    // --- dead-sidecar-says-so: bounded automatic restart ---------------------

    #[test]
    fn auto_restart_budget_admits_up_to_the_attempt_cap_then_refuses() {
        let mut budget = AutoRestartBudget::default();
        let t0 = Instant::now();
        for i in 0..AUTO_RESTART_MAX_ATTEMPTS {
            assert!(
                budget.record_attempt_if_allowed(t0 + Duration::from_secs(i as u64)),
                "attempt {i} should have been admitted"
            );
        }
        // The (N+1)th ask, still well inside the window, is refused outright.
        assert!(!budget.record_attempt_if_allowed(
            t0 + Duration::from_secs(AUTO_RESTART_MAX_ATTEMPTS as u64)
        ));
    }

    #[test]
    fn auto_restart_budget_refuses_once_the_window_elapses_even_under_the_attempt_cap() {
        // Two attempts used — one under the three-attempt cap — but the third
        // ask lands after the 2-minute window since the FIRST attempt. Still
        // refused: the window is a hard ceiling on one episode, not a per-
        // attempt cooldown that a slow caller could dodge by waiting.
        let mut budget = AutoRestartBudget::default();
        let t0 = Instant::now();
        assert!(budget.record_attempt_if_allowed(t0));
        assert!(budget.record_attempt_if_allowed(t0 + Duration::from_secs(30)));
        assert!(!budget.record_attempt_if_allowed(t0 + AUTO_RESTART_WINDOW + Duration::from_secs(1)));
    }

    #[test]
    fn auto_restart_budget_does_not_renew_after_being_exhausted() {
        // "到限就停,不再试" — exhausting the attempt cap is a TERMINAL state for
        // this episode, not a rate limiter that reopens next window. Unlike
        // `Restart=always`, nothing here retries again on its own; only a
        // manual restart() (tested below, on the supervisor) starts a fresh
        // episode.
        let mut budget = AutoRestartBudget::default();
        let t0 = Instant::now();
        for i in 0..AUTO_RESTART_MAX_ATTEMPTS {
            assert!(budget.record_attempt_if_allowed(t0 + Duration::from_secs(i as u64)));
        }
        // Long after the window would have elapsed, still refused — no renewal.
        assert!(!budget.record_attempt_if_allowed(t0 + AUTO_RESTART_WINDOW * 100));
    }

    #[test]
    fn automatic_restart_is_bounded_and_then_refuses_without_spawning_anything() {
        let supervisor = SidecarSupervisor::start(unstartable_launch_config());

        for attempt in 0..AUTO_RESTART_MAX_ATTEMPTS {
            match supervisor.restart_automatic() {
                AutoRestartOutcome::Failed(error) => {
                    assert!(
                        error.contains("failed to spawn"),
                        "attempt {attempt} should report a real (failed) spawn: {error}"
                    );
                }
                other => panic!("attempt {attempt}: expected a real attempt, got {other:?}"),
            }
        }

        // The budget is spent: the next automatic ask must not touch the
        // process at all — it comes back immediately as BudgetExhausted, not
        // another Failed (which would mean it tried again).
        match supervisor.restart_automatic() {
            AutoRestartOutcome::BudgetExhausted => {}
            other => panic!("expected the budget to refuse a 4th automatic attempt, got {other:?}"),
        }
    }

    #[test]
    fn a_manual_retry_is_never_refused_by_the_spent_automatic_budget() {
        let supervisor = SidecarSupervisor::start(unstartable_launch_config());
        for _ in 0..AUTO_RESTART_MAX_ATTEMPTS {
            let _ = supervisor.restart_automatic();
        }
        assert!(matches!(
            supervisor.restart_automatic(),
            AutoRestartOutcome::BudgetExhausted
        ));

        // A person pressing Retry must still get a REAL attempt. A Retry
        // button that silently does nothing once the auto-budget is spent
        // would leave the user with no way out — worse than the bug this
        // fixes (a dead sidecar with no visible recourse at all).
        let error = supervisor.restart().expect_err("still unstartable");
        assert!(
            error.contains("failed to spawn"),
            "manual retry should attempt, not refuse: {error}"
        );
    }

    #[test]
    fn a_manual_retry_resets_the_automatic_budget_for_a_fresh_episode() {
        let supervisor = SidecarSupervisor::start(unstartable_launch_config());
        for _ in 0..AUTO_RESTART_MAX_ATTEMPTS {
            let _ = supervisor.restart_automatic();
        }

        let _ = supervisor.restart(); // manual retry: fresh episode

        // The automatic budget is live again — the very next automatic ask
        // gets a real attempt, not an immediate refusal.
        match supervisor.restart_automatic() {
            AutoRestartOutcome::Failed(_) => {}
            other => panic!("expected the reset budget to allow a real attempt, got {other:?}"),
        }
    }

    // --- confirm-before-you-kill: the destruction gate ------------------------
    //
    // These run wherever `cargo test --lib` runs, which is the
    // `cross-platform-smoke` job on BOTH windows-latest and macos-latest (see
    // .github/workflows/ci.yml). Nothing here is `#[cfg]`-gated to one platform,
    // and nothing here needs a Python interpreter or the vendor closure: the
    // instance under test is a real child process plus a real socket, both of
    // which every host has.

    /// A TCP listener that answers one fixed HTTP status line and body to
    /// whatever connects: a sidecar serving and naming itself, a stranger on the
    /// port naming somebody else, an answer with no identity at all, an
    /// unhealthy reply, or — once stopped — a port with nobody on it.
    /// Deliberately not a real HTTP server: the only behaviour under test is
    /// what `health_probe_once` concludes from a status line and a body.
    struct FakeHealthEndpoint {
        port: u16,
        stop: Arc<AtomicBool>,
        server: Option<thread::JoinHandle<()>>,
    }

    impl FakeHealthEndpoint {
        fn answering(status_line: &'static str, body: String) -> Self {
            let listener = TcpListener::bind(("127.0.0.1", 0)).expect("bind fake health endpoint");
            let port = listener.local_addr().expect("local addr").port();
            listener
                .set_nonblocking(true)
                .expect("non-blocking accept so the thread can observe `stop`");
            let stop = Arc::new(AtomicBool::new(false));
            let stop_for_server = Arc::clone(&stop);
            let response = format!(
                "HTTP/1.1 {status_line}\r\ncontent-type: application/json\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{body}",
                body.len()
            );
            let server = thread::spawn(move || {
                while !stop_for_server.load(AtomicOrdering::Relaxed) {
                    match listener.accept() {
                        Ok((mut stream, _)) => {
                            stream.set_nonblocking(false).ok();
                            stream
                                .set_read_timeout(Some(Duration::from_millis(500)))
                                .ok();
                            // Drain the request before replying: answering and
                            // closing without reading can reset the connection
                            // and destroy the response before the client sees it.
                            let mut request = [0_u8; 1024];
                            let _ = stream.read(&mut request);
                            let _ = stream.write_all(response.as_bytes());
                            let _ = stream.flush();
                        }
                        Err(ref error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                            thread::sleep(Duration::from_millis(5));
                        }
                        Err(_) => break,
                    }
                }
            });
            Self {
                port,
                stop,
                server: Some(server),
            }
        }

        /// Stop answering — the port goes quiet while the child that "owns" it
        /// stays alive, which is the wedged-sidecar case.
        fn stop(&mut self) {
            self.stop.store(true, AtomicOrdering::Relaxed);
            if let Some(server) = self.server.take() {
                server.join().ok();
            }
        }
    }

    impl Drop for FakeHealthEndpoint {
        fn drop(&mut self) {
            self.stop();
        }
    }

    /// A process that stays alive long enough to be asked whether it is.
    /// `ping`/`sleep` are the "do nothing for a while" programs present on both
    /// CI legs of the job that runs these tests.
    fn spawn_long_lived_child() -> GroupChild {
        let mut command = if cfg!(windows) {
            let mut command = Command::new("cmd");
            command.args(["/C", "ping -n 60 127.0.0.1"]);
            command
        } else {
            let mut command = Command::new("sh");
            command.args(["-c", "sleep 60"]);
            command
        };
        command
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .group_spawn()
            .expect("spawn long-lived child")
    }

    impl SidecarManager {
        /// A manager wrapped around a child that is ALREADY running and a port
        /// something already listens on. `start` cannot serve here: it insists
        /// on spawning a Python interpreter and waiting for the real backend,
        /// which is the dependency these tests exist to avoid.
        fn around_running_child_for_test(
            child: GroupChild,
            port: u16,
            launch_config: SidecarLaunchConfig,
        ) -> Self {
            Self {
                state: Mutex::new(SidecarState {
                    child: Some(child),
                    token: "test-token".to_string(),
                    runtime_config: SidecarRuntimeConfig::new(
                        port,
                        &launch_config.resource_dir,
                        &launch_config.config_dir,
                        "test-token",
                    ),
                    stderr_lines: Arc::new(Mutex::new(VecDeque::new())),
                    // Small on purpose: a test that waits out a graceful-shutdown
                    // budget is measuring the clock, not the decision.
                    shutdown_timeout: Duration::from_millis(50),
                    launch_config,
                }),
            }
        }
    }

    impl SidecarSupervisor {
        fn around_running_manager_for_test(
            launch: SidecarLaunchConfig,
            manager: SidecarManager,
        ) -> Self {
            Self {
                launch,
                state: Mutex::new(SupervisorState {
                    sidecar: SupervisedSidecar::Running(manager),
                    auto_restart_budget: AutoRestartBudget::default(),
                }),
            }
        }
    }

    /// How the port answers, relative to the child the supervisor owns. The
    /// distinction these variants draw is the whole point of the identity rule:
    /// every one of them is a live child plus a 200 on the recorded port, and
    /// only the first is actually our sidecar serving.
    #[derive(Clone, Copy)]
    enum FakeHealth {
        /// A sidecar answering for itself — 200 naming the child's own pid.
        OwnedByTheChild,
        /// A stranger holding the port: 200, but it names a different process.
        /// The child is alive for its own reasons and its listener is gone.
        OwnedBySomeoneElse,
        /// 200 with no identity at all — an answer that cannot be attributed.
        Anonymous,
        /// A reply from the right process, but not a healthy one.
        UnhealthyFromTheChild,
    }

    /// A supervisor whose instance is a live child plus a port answering
    /// according to `answer`, and whose launch recipe provably cannot produce a
    /// replacement — so any restart it does perform is unmistakable in the
    /// outcome (`Failed`, "failed to spawn") rather than being inferred.
    fn supervisor_over_fake_instance(
        answer: FakeHealth,
    ) -> (SidecarSupervisor, FakeHealthEndpoint) {
        let mut child = spawn_long_lived_child();
        let child_pid = child.inner().id();
        let (status_line, body) = match answer {
            FakeHealth::OwnedByTheChild => {
                ("200 OK", format!("{{\"status\":\"ok\",\"pid\":{child_pid}}}"))
            }
            FakeHealth::OwnedBySomeoneElse => (
                "200 OK",
                // This test process: a real, live, unrelated pid.
                format!("{{\"status\":\"ok\",\"pid\":{}}}", std::process::id()),
            ),
            FakeHealth::Anonymous => ("200 OK", "{\"status\":\"ok\"}".to_string()),
            FakeHealth::UnhealthyFromTheChild => (
                "503 Service Unavailable",
                format!("{{\"status\":\"down\",\"pid\":{child_pid}}}"),
            ),
        };
        let endpoint = FakeHealthEndpoint::answering(status_line, body);
        let launch = unstartable_launch_config();
        let manager =
            SidecarManager::around_running_child_for_test(child, endpoint.port, launch.clone());
        (
            SidecarSupervisor::around_running_manager_for_test(launch, manager),
            endpoint,
        )
    }

    /// Reads the OS's answer for the child the supervisor currently owns —
    /// "was anything actually killed", asked of the process table rather than
    /// of the code under test.
    fn instance_child_is_running(supervisor: &SidecarSupervisor) -> bool {
        match &supervisor.state.lock().expect("sidecar state poisoned").sidecar {
            SupervisedSidecar::Running(manager) => {
                let mut state = manager.state.lock().expect("sidecar state poisoned");
                match state.child.as_mut() {
                    Some(child) => child.try_wait().expect("try_wait").is_none(),
                    None => false,
                }
            }
            SupervisedSidecar::Absent(_) => false,
        }
    }

    fn health_body_for(pid: u32) -> String {
        format!("{{\"status\":\"ok\",\"pid\":{pid}}}")
    }

    #[test]
    fn health_probe_once_accepts_only_a_success_status() {
        let client = reqwest::blocking::Client::new();
        let me = std::process::id();

        let serving = FakeHealthEndpoint::answering("200 OK", health_body_for(me));
        assert!(health_probe_once(
            &client,
            serving.port,
            CONFIRM_SERVING_REQUEST_TIMEOUT,
            me
        ));

        // The deliberate threshold choice, pinned: a reply is not a verdict.
        // Something that answers 503 is running but not serving, and this gate
        // decides whether a restart is warranted — not whether a process exists.
        let unhealthy =
            FakeHealthEndpoint::answering("503 Service Unavailable", health_body_for(me));
        assert!(!health_probe_once(
            &client,
            unhealthy.port,
            CONFIRM_SERVING_REQUEST_TIMEOUT,
            me
        ));
    }

    #[test]
    fn health_probe_once_requires_the_answer_to_name_the_expected_process() {
        // A port identifies nobody. Everything below is a healthy 200 on the
        // port we asked about, and none of it is the process we asked about.
        let client = reqwest::blocking::Client::new();
        let me = std::process::id();

        let stranger = FakeHealthEndpoint::answering("200 OK", health_body_for(me + 1));
        assert!(
            !health_probe_once(
                &client,
                stranger.port,
                CONFIRM_SERVING_REQUEST_TIMEOUT,
                me
            ),
            "an answer from a different process was accepted as ours"
        );

        let anonymous = FakeHealthEndpoint::answering("200 OK", "{\"status\":\"ok\"}".to_string());
        assert!(
            !health_probe_once(
                &client,
                anonymous.port,
                CONFIRM_SERVING_REQUEST_TIMEOUT,
                me
            ),
            "an answer naming nobody was accepted as ours"
        );

        let not_json = FakeHealthEndpoint::answering("200 OK", "ok".to_string());
        assert!(
            !health_probe_once(&client, not_json.port, CONFIRM_SERVING_REQUEST_TIMEOUT, me),
            "a body that carries no identity at all was accepted as ours"
        );
    }

    #[test]
    fn health_probe_once_is_bounded_by_the_timeout_it_was_given() {
        // The single-shot primitive must not behave like the poll loop, which
        // spends its WHOLE budget on a closed port (`health_wait_times_out_for_
        // closed_port` above). One request, bounded by the timeout passed in.
        //
        // The bound has to come from that timeout and nothing else. "Nobody is
        // listening" is not a free answer on every host: measured on Windows
        // 2026-09-01, a connect to a CLOSED loopback port takes ~2.04s to be
        // reported as refused (the stack retransmits the SYN) where unix
        // refuses at once. A 300ms budget must therefore still return in
        // roughly 300ms — which is the assertion below, and the reason
        // `confirm_serving` asks the process handle BEFORE it asks the network.
        let client = reqwest::blocking::Client::new();
        let port = allocate_loopback_port_from(None).expect("port");
        let started = Instant::now();

        assert!(!health_probe_once(
            &client,
            port,
            Duration::from_millis(300),
            std::process::id()
        ));

        assert!(
            started.elapsed() < Duration::from_secs(2),
            "the probe outlived the timeout it was given, taking {:?}",
            started.elapsed()
        );
    }

    #[test]
    fn an_automatic_restart_declines_and_touches_nothing_while_the_instance_serves() {
        let (supervisor, _endpoint) = supervisor_over_fake_instance(FakeHealth::OwnedByTheChild);
        let instance = supervisor.runtime_config().expect("a running instance");

        let declined_config = match supervisor.restart_automatic() {
            AutoRestartOutcome::Declined(config) => config,
            other => panic!("a serving instance must not be replaced, got {other:?}"),
        };

        // The refusal names the instance it spared, not some other truth read
        // later: this is what the caller reconnects to.
        assert_eq!(declined_config.port, instance.port);
        assert!(
            instance_child_is_running(&supervisor),
            "the child was killed despite the decline"
        );
        assert_eq!(
            supervisor.runtime_config().expect("still running").port,
            instance.port
        );

        supervisor.shutdown_blocking();
    }

    #[test]
    fn a_decline_spends_no_budget_so_a_real_death_is_still_recoverable() {
        let (supervisor, mut endpoint) = supervisor_over_fake_instance(FakeHealth::OwnedByTheChild);

        // Twice the attempt cap, all refused. A budget charged for refusals
        // would be long gone by now.
        for ask in 0..(AUTO_RESTART_MAX_ATTEMPTS * 2) {
            match supervisor.restart_automatic() {
                AutoRestartOutcome::Declined(_) => {}
                other => panic!("ask {ask}: expected a decline, got {other:?}"),
            }
        }

        // Now the sidecar stops serving for real.
        endpoint.stop();

        match supervisor.restart_automatic() {
            AutoRestartOutcome::Failed(error) => assert!(
                error.contains("failed to spawn"),
                "expected a real (failed) attempt: {error}"
            ),
            other => panic!("the refusals consumed the recovery budget, got {other:?}"),
        }
    }

    #[test]
    fn an_alive_but_unresponsive_instance_is_restarted_rather_than_spared() {
        // The case the process handle alone cannot decide: the child never
        // exited, so `try_wait` says "running", but it no longer answers. A gate
        // that stopped at the handle would refuse to ever restart a wedged
        // sidecar — the exact failure an automatic restart exists for.
        let (supervisor, mut endpoint) = supervisor_over_fake_instance(FakeHealth::OwnedByTheChild);
        assert!(instance_child_is_running(&supervisor));
        endpoint.stop();

        match supervisor.restart_automatic() {
            AutoRestartOutcome::Failed(error) => assert!(
                error.contains("failed to spawn"),
                "expected a real (failed) attempt: {error}"
            ),
            other => panic!("a wedged sidecar must not be spared, got {other:?}"),
        }
    }

    #[test]
    fn an_instance_answering_a_non_success_status_is_not_spared() {
        let (supervisor, _endpoint) =
            supervisor_over_fake_instance(FakeHealth::UnhealthyFromTheChild);

        match supervisor.restart_automatic() {
            AutoRestartOutcome::Failed(error) => assert!(
                error.contains("failed to spawn"),
                "expected a real (failed) attempt: {error}"
            ),
            other => panic!("answering 503 is not serving, got {other:?}"),
        }
    }

    /// The hole this fixture used to encode as CORRECT, now asserted the other
    /// way round. A live child plus a healthy 200 on the recorded port was
    /// treated as "our sidecar is serving" — but a port is a rendezvous, and
    /// this is the fully reachable case where the child is alive while its
    /// listener is gone and an unrelated process holds the port. Sparing it
    /// would hand the frontend a config for a sidecar that cannot serve it, and
    /// the frontend — told this is recovery — clears the banner and stops
    /// retrying. A silent dead end, and the decline costs no budget, so the app
    /// could sit in it indefinitely.
    #[test]
    fn an_answer_from_an_unrelated_process_does_not_spare_the_instance() {
        let (supervisor, _endpoint) =
            supervisor_over_fake_instance(FakeHealth::OwnedBySomeoneElse);
        assert!(
            instance_child_is_running(&supervisor),
            "the fixture must present a LIVE child, or it tests nothing"
        );

        match supervisor.restart_automatic() {
            AutoRestartOutcome::Failed(error) => assert!(
                error.contains("failed to spawn"),
                "expected a real (failed) attempt: {error}"
            ),
            other => panic!(
                "a stranger on the port was accepted as our serving sidecar, got {other:?}"
            ),
        }
    }

    #[test]
    fn an_answer_naming_nobody_does_not_spare_the_instance() {
        // Same shape, weaker attacker: a 200 with no identity at all. It cannot
        // be attributed, so it cannot authorise sparing — an answer that names
        // nobody is not an answer about this instance.
        let (supervisor, _endpoint) = supervisor_over_fake_instance(FakeHealth::Anonymous);
        assert!(instance_child_is_running(&supervisor));

        match supervisor.restart_automatic() {
            AutoRestartOutcome::Failed(error) => assert!(
                error.contains("failed to spawn"),
                "expected a real (failed) attempt: {error}"
            ),
            other => panic!("an unattributable answer spared the instance, got {other:?}"),
        }
    }

    #[test]
    fn only_an_answer_from_the_child_itself_spares_it() {
        // The positive half of the pair above, stated as the contrast: the ONLY
        // difference between this and `an_answer_from_an_unrelated_process_…`
        // is which pid the port reports.
        let (serving, _serving_endpoint) =
            supervisor_over_fake_instance(FakeHealth::OwnedByTheChild);
        assert!(matches!(
            serving.restart_automatic(),
            AutoRestartOutcome::Declined(_)
        ));
        serving.shutdown_blocking();

        let (stranger, _stranger_endpoint) =
            supervisor_over_fake_instance(FakeHealth::OwnedBySomeoneElse);
        assert!(matches!(
            stranger.restart_automatic(),
            AutoRestartOutcome::Failed(_)
        ));
    }

    #[test]
    fn a_manual_retry_is_never_refused_by_the_confirmation() {
        // The counterpart to the whole gate: it protects the app from acting on
        // evidence it cannot interpret, and a person pressing Retry is not that
        // evidence. This is also why the two live on separate commands.
        let (supervisor, _endpoint) = supervisor_over_fake_instance(FakeHealth::OwnedByTheChild);

        let error = supervisor
            .restart()
            .expect_err("this recipe cannot produce a replacement");

        assert!(
            error.contains("failed to spawn"),
            "manual retry should attempt, not decline: {error}"
        );
        // It really went through with the teardown — the serving instance was
        // replaced (and the replacement failed), not spared.
        assert!(supervisor.runtime_config().is_err());
    }

    #[test]
    fn debug_runtime_resource_root_uses_source_tauri_dir() {
        let resolved = PathBuf::from("/app/target/debug");
        let root = resource_root_for_runtime_mode(resolved, true);
        assert_eq!(root, default_tauri_dir());
    }

    #[test]
    fn release_runtime_resource_root_prefers_resolved_vendor_root() {
        let resolved = default_tauri_dir();
        let root = resource_root_for_runtime_mode(resolved.clone(), false);
        assert_eq!(root, resolved);
    }

    #[test]
    fn release_runtime_resource_root_falls_back_without_vendor() {
        let root = resource_root_for_runtime_mode(PathBuf::from("/app/no-vendor"), false);
        assert_eq!(root, default_tauri_dir());
    }

    #[test]
    fn sidecar_cors_extra_origins_includes_default_backup_dev_port() {
        let origins = sidecar_cors_extra_origins();
        assert!(origins.contains("http://127.0.0.1:5174"));
        assert!(origins.contains("http://localhost:5174"));
    }

    #[cfg(windows)]
    #[test]
    fn python_path_env_includes_pywin32_target_paths_before_backend() {
        let root = temp_test_dir("pywin32-pythonpath");
        let site_packages = root.join("site-packages");
        let backend_dir = root.join("backend");
        std::fs::create_dir_all(site_packages.join("win32").join("lib")).expect("win32 dirs");
        std::fs::create_dir_all(&backend_dir).expect("backend dir");

        let joined = python_path_env(&site_packages, &backend_dir);
        let entries = std::env::split_paths(&joined).collect::<Vec<_>>();

        assert_eq!(entries[0], site_packages);
        assert_eq!(entries[1], root.join("site-packages").join("win32"));
        assert_eq!(
            entries[2],
            root.join("site-packages").join("win32").join("lib")
        );
        assert_eq!(entries[3], backend_dir);

        std::fs::remove_dir_all(root).expect("cleanup temp dir");
    }

    #[cfg(windows)]
    #[test]
    fn sidecar_path_env_prepends_pywin32_dll_path() {
        let root = temp_test_dir("pywin32-path");
        let site_packages = root.join("site-packages");
        let pywin32_system32 = site_packages.join("pywin32_system32");
        std::fs::create_dir_all(&pywin32_system32).expect("pywin32 dll dir");

        let joined = sidecar_path_env(&site_packages);
        let entries = std::env::split_paths(&joined).collect::<Vec<_>>();

        assert_eq!(entries[0], pywin32_system32);

        std::fs::remove_dir_all(root).expect("cleanup temp dir");
    }

    #[test]
    fn runtime_config_serializes_frontend_contract_field_names() {
        let config = SidecarRuntimeConfig::new(
            45678,
            Path::new("/tmp/studio-resource"),
            Path::new("/tmp/studio-config"),
            "token",
        );
        let json = serde_json::to_value(config).expect("serialize config");
        assert_eq!(json["baseURL"], "http://127.0.0.1:45678/api");
        assert_eq!(json["wsURL"], "ws://127.0.0.1:45678/ws");
        assert_eq!(json["resourceDir"], "/tmp/studio-resource");
        assert_eq!(json["configDir"], "/tmp/studio-config");
        assert_eq!(json["api_token"], "token");
    }

    #[cfg(unix)]
    #[test]
    fn kill_process_group_stops_long_running_child() {
        let mut child = Command::new("sh")
            .arg("-c")
            .arg("sleep 30")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .group_spawn()
            .expect("spawn sleep");

        kill_process_group(&mut child).expect("kill process group");
        assert!(child.try_wait().expect("wait after kill").is_some());
    }

    #[cfg(windows)]
    fn temp_test_dir(label: &str) -> PathBuf {
        let suffix = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("system clock")
            .as_nanos();
        std::env::temp_dir().join(format!(
            "skill-studio-sidecar-{label}-{}-{suffix}",
            std::process::id()
        ))
    }
}
