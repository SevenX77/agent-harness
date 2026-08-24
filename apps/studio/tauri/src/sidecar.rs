use command_group::{CommandGroup, GroupChild};
use rand::{distr::Alphanumeric, Rng};
use serde::Serialize;
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

            if wait_for_health(port, config.health_timeout) {
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

            if wait_for_health(port, launch_config.health_timeout) {
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
pub struct SidecarSupervisor {
    launch: SidecarLaunchConfig,
    state: Mutex<SupervisedSidecar>,
    /// Bookkeeping for `restart_automatic` ONLY — a manual `restart()` always
    /// attempts and resets this (see the struct doc above).
    auto_restart_budget: Mutex<AutoRestartBudget>,
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
        let state = match SidecarManager::start(launch.clone()) {
            Ok(manager) => SupervisedSidecar::Running(manager),
            Err(error) => {
                SupervisedSidecar::Absent(format!("failed to start Python sidecar: {error}"))
            }
        };
        Self {
            launch,
            state: Mutex::new(state),
            auto_restart_budget: Mutex::new(AutoRestartBudget::default()),
        }
    }

    pub fn runtime_config(&self) -> Result<SidecarRuntimeConfig, String> {
        match &*self.state.lock().expect("sidecar state poisoned") {
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
    /// automatic budget (struct doc above) — and resets that budget, so this
    /// is also how a fresh automatic-restart episode begins after one ran out.
    pub fn restart(&self) -> Result<SidecarRuntimeConfig, String> {
        *self
            .auto_restart_budget
            .lock()
            .expect("sidecar auto-restart budget poisoned") = AutoRestartBudget::default();
        self.perform_restart()
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
    pub fn restart_automatic(&self) -> AutoRestartOutcome {
        let admitted = {
            let mut budget = self
                .auto_restart_budget
                .lock()
                .expect("sidecar auto-restart budget poisoned");
            budget.record_attempt_if_allowed(Instant::now())
        };
        if !admitted {
            return AutoRestartOutcome::BudgetExhausted;
        }
        match self.perform_restart() {
            Ok(runtime_config) => AutoRestartOutcome::Restarted(runtime_config),
            Err(error) => AutoRestartOutcome::Failed(error),
        }
    }

    /// The actual restart-or-start attempt, shared by `restart` and
    /// `restart_automatic` — everything above this line is only about WHETHER
    /// an attempt is allowed, never about how the attempt itself works.
    fn perform_restart(&self) -> Result<SidecarRuntimeConfig, String> {
        let mut state = self.state.lock().expect("sidecar state poisoned");
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
        match &*self.state.lock().expect("sidecar state poisoned") {
            SupervisedSidecar::Running(manager) => manager.recent_stderr(),
            SupervisedSidecar::Absent(error) => error.lines().map(str::to_string).collect(),
        }
    }

    pub fn shutdown_blocking(&self) {
        let mut state = self.state.lock().expect("sidecar state poisoned");
        if let SupervisedSidecar::Running(manager) = &*state {
            manager.shutdown_blocking();
        }
        *state = SupervisedSidecar::Absent("Python sidecar was shut down".to_string());
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

pub fn uvicorn_args(port: u16) -> Vec<String> {
    [
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        &port.to_string(),
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

fn spawn_sidecar_process(
    config: &SidecarLaunchConfig,
    port: u16,
    api_token: &str,
    stderr_lines: Arc<Mutex<VecDeque<String>>>,
) -> Result<GroupChild, SidecarError> {
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

fn wait_for_health(port: u16, timeout: Duration) -> bool {
    let client = reqwest::blocking::Client::new();
    let url = format!("http://127.0.0.1:{port}/health");
    let deadline = Instant::now() + timeout;

    while Instant::now() < deadline {
        if client
            .get(&url)
            .timeout(Duration::from_millis(500))
            .send()
            .is_ok_and(|response| response.status().is_success())
        {
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
        assert!(!wait_for_health(port, Duration::from_millis(20)));
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
