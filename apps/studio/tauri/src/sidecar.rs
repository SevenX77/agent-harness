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
const STDERR_RING_LINES: usize = 200;
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
    pub startup_attempts: usize,
    pub health_timeout: Duration,
    pub shutdown_timeout: Duration,
}

impl SidecarLaunchConfig {
    pub fn from_tauri_dir(tauri_dir: impl AsRef<Path>) -> Self {
        let tauri_dir = tauri_dir.as_ref();
        Self {
            python: python_executable_path(tauri_dir),
            backend_dir: tauri_dir
                .parent()
                .expect("tauri dir must live under apps/studio")
                .join("backend"),
            site_packages: tauri_dir.join("vendor").join("site-packages"),
            resource_dir: tauri_dir.join("vendor").join("resources"),
            startup_attempts: MAX_STARTUP_ATTEMPTS,
            health_timeout: Duration::from_secs(10),
            shutdown_timeout: Duration::from_secs(2),
        }
    }
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SidecarRuntimeConfig {
    pub port: u16,
    pub base_url: String,
    pub ws_url: String,
    pub resource_dir: String,
}

impl SidecarRuntimeConfig {
    fn new(port: u16, resource_dir: &Path) -> Self {
        Self {
            port,
            base_url: format!("http://127.0.0.1:{port}/api"),
            ws_url: format!("ws://127.0.0.1:{port}/ws"),
            resource_dir: resource_dir.display().to_string(),
        }
    }
}

pub struct SidecarManager {
    state: Mutex<SidecarState>,
}

struct SidecarState {
    child: Option<GroupChild>,
    token: String,
    runtime_config: SidecarRuntimeConfig,
    stderr_lines: Arc<Mutex<VecDeque<String>>>,
    shutdown_timeout: Duration,
}

impl SidecarManager {
    pub fn start(config: SidecarLaunchConfig) -> Result<Self, SidecarError> {
        let attempts = config.startup_attempts.max(1);
        let mut last_error = None;

        for _ in 0..attempts {
            let port = allocate_loopback_port()?;
            let token = generate_shutdown_token();
            let stderr_lines = Arc::new(Mutex::new(VecDeque::with_capacity(STDERR_RING_LINES)));
            let mut child =
                spawn_sidecar_process(&config, port, &token, Arc::clone(&stderr_lines))?;

            if wait_for_health(port, config.health_timeout) {
                return Ok(Self {
                    state: Mutex::new(SidecarState {
                        child: Some(child),
                        token,
                        runtime_config: SidecarRuntimeConfig::new(port, &config.resource_dir),
                        stderr_lines,
                        shutdown_timeout: config.shutdown_timeout,
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
}

pub fn default_tauri_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

pub fn allocate_loopback_port() -> std::io::Result<u16> {
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

pub fn shutdown_header_name() -> &'static str {
    "x-studio-shutdown-token"
}

pub fn python_executable_path(tauri_dir: &Path) -> PathBuf {
    let runtime_dir = tauri_dir
        .join("vendor")
        .join("python")
        .join(host_target_triple());
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
    token: &str,
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
        .env("STUDIO_RESOURCE_DIR", &config.resource_dir)
        .env("STUDIO_SHUTDOWN_TOKEN", token)
        .env("STUDIO_EXIT_ON_ORPHAN", "1")
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
    let mut entries = vec![site_packages.to_path_buf(), backend_dir.to_path_buf()];
    if let Some(existing) = std::env::var_os("PYTHONPATH") {
        entries.extend(std::env::split_paths(&existing));
    }
    std::env::join_paths(entries).expect("PYTHONPATH entries must be valid")
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
        .header(shutdown_header_name(), token)
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

fn generate_shutdown_token() -> String {
    rand::rng()
        .sample_iter(Alphanumeric)
        .take(48)
        .map(char::from)
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn allocate_loopback_port_returns_bindable_dynamic_port() {
        let port = allocate_loopback_port().expect("port");
        assert_ne!(port, 0);
        let listener = TcpListener::bind(("127.0.0.1", port)).expect("released port should rebind");
        drop(listener);
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
  fn shutdown_uses_expected_token_header() {
    assert_eq!(shutdown_header_name(), "x-studio-shutdown-token");
  }

  #[test]
  fn health_wait_times_out_for_closed_port() {
    let port = allocate_loopback_port().expect("port");
    assert!(!wait_for_health(port, Duration::from_millis(20)));
  }

  #[test]
  fn runtime_config_uses_dynamic_http_and_ws_urls() {
        let config = SidecarRuntimeConfig::new(45678, Path::new("/tmp/studio-resource"));
        assert_eq!(config.base_url, "http://127.0.0.1:45678/api");
        assert_eq!(config.ws_url, "ws://127.0.0.1:45678/ws");
        assert_eq!(config.resource_dir, "/tmp/studio-resource");
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
}
