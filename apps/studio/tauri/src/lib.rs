mod cli_terminal;
mod native_fs;
mod sidecar;

// ah v1.4.0+ state-contract test fixtures (studio-ah-state-contract-v1, task 1).
// Test-only: the frozen ah CLI snapshot/version/identity samples that the RED tests
// in tasks 2–9 consume. Builds no production types (the typed parser is task 3).
#[cfg(test)]
mod ah_contract_fixtures;

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::io::{BufRead, BufReader};
use std::path::Path;
use std::path::PathBuf;
use std::process::{Child, Command, Output, Stdio};
use std::sync::{
    atomic::{AtomicBool, Ordering},
    mpsc, Arc, Mutex, OnceLock,
};
use std::time::{Duration, Instant};
#[cfg(target_os = "macos")]
use tauri::menu::{AboutMetadata, Menu, PredefinedMenuItem, Submenu};
use tauri::{Emitter, Manager};
use tauri_plugin_dialog::DialogExt;

/// R-F19.2 — `RunEvent::ExitRequested` blocks the shutdown for up to this long
/// while the frontend flushes any in-flight debounced roles save and acks via
/// `confirm_quit_ready`. Chosen to comfortably cover the 300ms debounce timer
/// + a typical local PUT round-trip (sidecar is in-process loopback), without
/// making the user wait noticeably if the FE is gone.
const QUIT_FLUSH_BUDGET: Duration = Duration::from_millis(1500);
const QUIT_FLUSH_POLL_INTERVAL: Duration = Duration::from_millis(25);

const AH_VERSION_MIN: &str = "1.4.0";

static AH_VERSION_CACHE: std::sync::OnceLock<Result<(), String>> = std::sync::OnceLock::new();

fn run_ah_version() -> Result<String, String> {
    if cfg!(target_os = "windows") {
        let mut command = Command::new("wsl.exe");
        let script = "export PATH=\"$HOME/.cargo/bin:$HOME/.local/bin:$PATH\"; export SYSTEMD_LOG_LEVEL=err; ah version";
        command.args(["-e", "bash", "-lc", script]);
        let output = command.output().map_err(|e| format!("failed to execute wsl.exe: {e}"))?;
        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            return Err(format!("wsl.exe returned error exit code: {:?}, stderr: {}", output.status.code(), stderr.trim()));
        }
        Ok(String::from_utf8_lossy(&output.stdout).to_string())
    } else {
        let mut command = Command::new("ah");
        command.arg("version");
        let output = command.output().map_err(|e| format!("failed to execute ah: {e}"))?;
        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            return Err(format!("ah version returned error exit code: {:?}, stderr: {}", output.status.code(), stderr.trim()));
        }
        Ok(String::from_utf8_lossy(&output.stdout).to_string())
    }
}

fn ah_version_gate(version_output: &str) -> Result<(), String> {
    let version_str = version_output.trim();
    if version_str.is_empty() {
        return Err("ah version output is empty".to_string());
    }
    let clean_version = version_str.split('-').next().unwrap_or(version_str);
    let parts: Vec<&str> = clean_version.split('.').collect();
    if parts.is_empty() {
        return Err(format!("Invalid version format: '{}'", version_str));
    }
    let major = parts[0].parse::<u32>().map_err(|e| format!("Failed to parse major version '{}': {}", parts[0], e))?;
    let minor = if parts.len() > 1 {
        parts[1].parse::<u32>().map_err(|e| format!("Failed to parse minor version '{}': {}", parts[1], e))?
    } else {
        0
    };
    let patch = if parts.len() > 2 {
        parts[2].parse::<u32>().map_err(|e| format!("Failed to parse patch version '{}': {}", parts[2], e))?
    } else {
        0
    };

    let min_parts: Vec<&str> = AH_VERSION_MIN.split('.').collect();
    let min_major = min_parts.get(0).copied().unwrap_or("1").parse::<u32>().unwrap_or(1);
    let min_minor = min_parts.get(1).copied().unwrap_or("4").parse::<u32>().unwrap_or(4);
    let min_patch = min_parts.get(2).copied().unwrap_or("0").parse::<u32>().unwrap_or(0);

    let is_ok = if major > min_major {
        true
    } else if major == min_major {
        if minor > min_minor {
            true
        } else if minor == min_minor {
            patch >= min_patch
        } else {
            false
        }
    } else {
        false
    };

    if is_ok {
        Ok(())
    } else {
        Err(format!(
            "Installed ah version {} is below the minimum required version {}",
            version_str, AH_VERSION_MIN
        ))
    }
}

fn check_ah_version_cached() -> Result<(), String> {
    AH_VERSION_CACHE.get_or_init(|| {
        let output = match run_ah_version() {
            Ok(out) => out,
            Err(e) => return Err(e),
        };
        ah_version_gate(&output)
    }).clone()
}

struct SidecarAppState {
    manager: Mutex<Option<sidecar::SidecarManager>>,
    startup_error: Mutex<Option<String>>,
}

/// Set to true by the `confirm_quit_ready` tauri command after the FE has
/// awaited `flushRolesSave()`. The exit handler polls this to know when it
/// can proceed without dropping a pending in-memory edit.
struct QuitFlushState {
    ready: AtomicBool,
}

struct CodeAssistantRuntimeState {
    configs: Mutex<BTreeSet<PathBuf>>,
    status_streams: Mutex<BTreeMap<PathBuf, CodeAssistantStatusStream>>,
    status_specs: Mutex<BTreeMap<PathBuf, CodeAssistantStatusSpec>>,
    status_snapshots: Mutex<BTreeMap<PathBuf, AhRuntimeSnapshot>>,
}

struct CodeAssistantStatusStream {
    stop: Arc<AtomicBool>,
    child: Arc<Mutex<Option<Child>>>,
}

#[derive(Clone)]
struct CodeAssistantStatusSpec {
    workspace_root: PathBuf,
    assistant: CodeAssistant,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
enum AssistantStatus {
    /// Studio 知道这个助手有一份 ah 配置，但还没拿到任何一帧描述它的运行时快照。
    ///
    /// 它不是 `Inactive`：`Inactive` 是一句关于运行时的**断言**（该 config 的 ah 运行时
    /// 确实被回收过），而这里 Studio 只是**还没观测到**。把"没观测到"塞进那句断言，
    /// 面板就会在缺乏依据时给出一个可点击、语义错误的 Open 入口——那正是 2026-08-03
    /// 缺陷 C 的可见形态（决议 D-C3）。面板对它的处理与 `Starting` 同类：hands-off。
    Unknown,
    Inactive,
    Starting,
    Active,
    /// ah 的运行时仍然存在，但其中已经没有活的 CLI 会话。
    ///
    /// 它不表示 CLI 进程还在跑：`/exit` 之后 ah 把会话标成终态，却把 tmux 会话和
    /// `remain-on-exit` 留下的死窗格原样留着（ah 生产代码里回收 tmux 的唯一位置是 ahd
    /// 收到 SIGTERM 时的整体清理）。此时面板必须继续提供 Close，而不是谎称运行时已经
    /// 消失、可以重新打开——否则再点 Open 只会 attach 回那块死窗格。
    Lingering,
    Degraded,
    Error,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
struct AssistantState {
    status: AssistantStatus,
    #[serde(skip_serializing_if = "Option::is_none")]
    reason: Option<String>,
    read_only: bool,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
struct CodeAssistantStatus {
    claude: AssistantState,
    codex: AssistantState,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct CodeAssistantStatusEvent {
    workspace_root: String,
    status: CodeAssistantStatus,
}

const CODE_ASSISTANT_STATUS_EVENT: &str = "code-assistant-status-changed";

#[tauri::command]
fn get_sidecar_config(
    state: tauri::State<'_, SidecarAppState>,
) -> Result<sidecar::SidecarRuntimeConfig, String> {
    if let Some(manager) = state
        .manager
        .lock()
        .expect("sidecar state poisoned")
        .as_ref()
    {
        return Ok(manager.runtime_config());
    }
    Err(state
        .startup_error
        .lock()
        .expect("sidecar error state poisoned")
        .clone()
        .unwrap_or_else(|| "Python sidecar is not running".to_string()))
}

/// R-F19.2 — the frontend calls this after `flushRolesSave()` resolves in its
/// `before-quit` listener. The exit handler polls `QuitFlushState::ready` and
/// proceeds with sidecar shutdown + `exit(0)` as soon as it's set, or after
/// `QUIT_FLUSH_BUDGET` lapses (so a stuck FE can't trap the user in the app).
#[tauri::command]
fn confirm_quit_ready(state: tauri::State<'_, QuitFlushState>) {
    state.ready.store(true, Ordering::SeqCst);
    log::info!("phase=quit action=flush-ready source=frontend");
}

/// R-F13 — tear down the current Python sidecar process and spawn a fresh one,
/// then emit `SIDECAR_RESTARTED_EVENT` so the frontend's `sidecar-restarted`
/// listener rotates `currentApiToken` / `currentApiBaseURL`. The next
/// `useStudioEventStream` reconnect picks up the new token via `wsUrl()` instead
/// of looping on 4401 closes (the auth gate's "Unauthorized" close code).
///
/// Intended trigger: a future watchdog / FE recovery flow. Wiring it up now means
/// the moment a trigger exists, token rotation is end-to-end without a second
/// landing.
#[tauri::command]
fn restart_sidecar(
    app_handle: tauri::AppHandle,
    state: tauri::State<'_, SidecarAppState>,
) -> Result<sidecar::SidecarRuntimeConfig, String> {
    let runtime_config = {
        let guard = state.manager.lock().expect("sidecar state poisoned");
        let manager = guard
            .as_ref()
            .ok_or_else(|| "Python sidecar is not running".to_string())?;
        manager
            .restart()
            .map_err(|err| format!("failed to restart Python sidecar: {err}"))?
    };
    if let Err(err) = app_handle.emit(sidecar::SIDECAR_RESTARTED_EVENT, &runtime_config) {
        // Don't fail the command on emit error: the sidecar IS restarted; the
        // frontend just won't auto-rotate the token until a manual refresh. Log
        // loudly so this never goes silent (logging-rule iron rule).
        log::error!(
            "phase=sidecar-restart action=emit-failed event={} error={err}",
            sidecar::SIDECAR_RESTARTED_EVENT
        );
    } else {
        log::info!(
            "phase=sidecar-restart action=emit-ok event={} port={}",
            sidecar::SIDECAR_RESTARTED_EVENT,
            runtime_config.port
        );
    }
    Ok(runtime_config)
}

#[tauri::command]
fn get_sidecar_stderr(state: tauri::State<'_, SidecarAppState>) -> Vec<String> {
    if let Some(manager) = state
        .manager
        .lock()
        .expect("sidecar state poisoned")
        .as_ref()
    {
        return manager.recent_stderr();
    }
    state
        .startup_error
        .lock()
        .expect("sidecar error state poisoned")
        .clone()
        .map(|error| error.lines().map(str::to_string).collect())
        .unwrap_or_default()
}

/// Resolve the sidecar config dir, honoring an explicit `STUDIO_CONFIG_DIR`
/// override (the same contract the backend and e2e harness use) so the app can
/// run against an isolated config dir for verification without touching the
/// user's real `~/Library/Application Support/AgentStudio` store. Unset -> the
/// platform default, i.e. unchanged behavior for end users.
fn config_dir_from_override(override_value: Option<std::ffi::OsString>) -> Option<PathBuf> {
    override_value
        .map(PathBuf::from)
        .filter(|path| !path.as_os_str().is_empty())
}

pub(crate) fn resolve_config_dir() -> PathBuf {
    config_dir_from_override(std::env::var_os("STUDIO_CONFIG_DIR"))
        .unwrap_or_else(sidecar::default_user_config_dir)
}

fn existing_path(path: &str) -> Result<PathBuf, String> {
    let target = path.trim();
    if target.is_empty() {
        return Err("path is required".to_string());
    }
    let target = PathBuf::from(target);
    if !target.exists() {
        return Err(format!("path does not exist: {}", target.display()));
    }
    Ok(target)
}

/// Render a path the way the platform's file manager expects to receive it.
///
/// Windows Explorer does not accept `/` as a separator: handed
/// `D:/skills/demo/.workspace/import_files` it silently opens Documents instead
/// of the folder, with no error to notice. Studio builds its workspace paths
/// with forward slashes, so the conversion happens here — at the single point
/// where a path leaves Rust for the file manager — rather than at each caller.
fn file_manager_argument(path: &Path) -> PathBuf {
    if cfg!(target_os = "windows") {
        return PathBuf::from(path.to_string_lossy().replace('/', "\\"));
    }
    path.to_path_buf()
}

fn existing_directory(path: &str) -> Result<PathBuf, String> {
    let target = existing_path(path)?;
    if !target.is_dir() {
        return Err(format!("path is not a directory: {}", target.display()));
    }
    Ok(target)
}

fn find_ah_config(start_dir: &Path) -> Option<PathBuf> {
    let mut current = if start_dir.is_file() {
        start_dir.parent()?.to_path_buf()
    } else {
        start_dir.to_path_buf()
    };
    loop {
        let candidate = current.join("ah.toml");
        if candidate.is_file() {
            return Some(candidate);
        }
        if !current.pop() {
            return None;
        }
    }
}

fn workspace_hash(workspace_root: &Path) -> String {
    let canonical = workspace_root
        .canonicalize()
        .unwrap_or_else(|_| workspace_root.to_path_buf());
    let mut hasher = Sha256::new();
    hasher.update(canonical.display().to_string().as_bytes());
    let digest = hasher.finalize();
    digest[..8]
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn transient_ah_config_path(workspace_root: &Path, assistant: CodeAssistant) -> PathBuf {
    std::env::temp_dir()
        .join("skill-studio-ah")
        .join(workspace_hash(workspace_root))
        .join(assistant.slug())
        .join("ah.toml")
}

fn studio_ah_temp_root() -> PathBuf {
    std::env::temp_dir().join("skill-studio-ah")
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct ConfigOwnership {
    read_only: bool,
}

fn classify_config_ownership(config_path: &Path) -> ConfigOwnership {
    let read_only = !config_path.starts_with(studio_ah_temp_root());
    ConfigOwnership { read_only }
}

/// Lifecycle-command entry guard (Req 5.9). `start`/`stop`/`kill` may run ONLY
/// against a Studio-managed temp config; a workspace-owned config discovered by
/// walking up (`find_ah_config`) belongs to the operator's own fleet and is
/// read-only. The verdict is sourced from the single ownership authority
/// `classify_config_ownership` (底座一/SSOT), never a second guess. Read-only
/// commands (status / events / observational attach) do NOT pass through this
/// guard — only the paths that can emit a lifecycle command do.
fn ensure_lifecycle_command_allowed(config_path: &Path) -> Result<(), String> {
    if classify_config_ownership(config_path).read_only {
        return Err(format!(
            "refusing lifecycle command (start/stop/kill) on workspace-owned ah config {}: it \
             lives outside the Studio-managed temp namespace and belongs to the operator's own \
             fleet (Req 5.9)",
            config_path.display()
        ));
    }
    Ok(())
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum CodeAssistant {
    Claude,
    Codex,
}

impl CodeAssistant {
    const ALL: [Self; 2] = [Self::Claude, Self::Codex];

    fn slug(self) -> &'static str {
        match self {
            Self::Claude => "claude",
            Self::Codex => "codex",
        }
    }

    fn provider(self) -> &'static str {
        self.slug()
    }

    fn display_name(self) -> &'static str {
        match self {
            Self::Claude => "Claude Code",
            Self::Codex => "Codex",
        }
    }

    fn launcher_stem(self) -> &'static str {
        match self {
            Self::Claude => "open-claude-code",
            Self::Codex => "open-codex-cli",
        }
    }

    fn attach_launcher_stem(self) -> &'static str {
        match self {
            Self::Claude => "attach-claude-code",
            Self::Codex => "attach-codex-cli",
        }
    }

    fn master_cmd(
        self,
        studio_mcp: Option<&StudioMcpEndpoint>,
        skill: Option<&SessionSkillContext>,
    ) -> String {
        match self {
            Self::Claude => claude_master_cmd(studio_mcp, skill),
            Self::Codex => codex_master_cmd(studio_mcp, skill),
        }
    }

    fn from_slug(value: &str) -> Result<Self, String> {
        match value {
            "claude" => Ok(Self::Claude),
            "codex" => Ok(Self::Codex),
            _ => Err(format!("unknown code assistant: {value}")),
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct AhLifecycleSnapshot {
    ahd_has_inventory: bool,
    master_tmux_alive: bool,
    worker_tmux_alive: bool,
}

impl AhLifecycleSnapshot {
    fn new(ahd_has_inventory: bool, master_tmux_alive: bool, worker_tmux_alive: bool) -> Self {
        Self {
            ahd_has_inventory,
            master_tmux_alive,
            worker_tmux_alive,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum CodeAssistantLifecycleAction {
    StartFresh,
    AttachExisting,
    CleanupStale,
    // Take no lifecycle action: startup is in progress and must be left alone (Req 3.6).
    HandsOff,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum CodeAssistantOpenDecision {
    StartFresh,
    AttachRequested,
    RejectOtherActive,
    CleanupStale,
    // Startup is in progress: Open takes NO lifecycle action (not a duplicate start, not
    // cleanup, not attach, not a reject) and waits for startup to finish (Req 3.6). Mirrors
    // `CodeAssistantLifecycleAction::HandsOff` for the Open decision plane.
    HandsOff,
}

fn code_assistant_shutdown_is_complete(snapshot: AhLifecycleSnapshot) -> bool {
    !snapshot.ahd_has_inventory && !snapshot.master_tmux_alive && !snapshot.worker_tmux_alive
}

#[derive(Clone, Debug)]
struct CommandResult {
    success: bool,
    stdout: String,
    stderr: String,
}

impl CommandResult {
    fn from_output(output: Output) -> Self {
        Self {
            success: output.status.success(),
            stdout: String::from_utf8_lossy(&output.stdout).to_string(),
            stderr: String::from_utf8_lossy(&output.stderr).to_string(),
        }
    }
}

/// Tiny launch trigger for the ah-managed interactive master. The actual
/// self-report contract lives in the `moirai-intro` skill, so the first visible
/// user turn does not hard-code the answer it expects. Kept free of quotes so it
/// embeds cleanly in both the TOML `cmd` string and the shell argument.
const MOIRAI_MASTER_REPORT_PROMPT: &str = "使用 moirai-intro 介绍你自己。";

/// The identity a session is opened against: which skill, and where it lives.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SessionSkillContext {
    pub skill_id: String,
    pub workspace_root: String,
}

/// First message for the master: the report prompt plus who it is bound to.
///
/// Without this the model has no way to learn its own `skill_id` — `context_resolved`
/// carries only an assets summary — so it infers one from the manifest `name:`.
/// That inference is what let a session operate on a different, protected skill
/// (exp-B R0), and what sent a later one grepping the disk for its own id (round2).
fn master_prompt(skill: Option<&SessionSkillContext>) -> String {
    match skill {
        None => MOIRAI_MASTER_REPORT_PROMPT.to_string(),
        Some(context) => format!(
            "{MOIRAI_MASTER_REPORT_PROMPT}\n\n\
             [Studio 会话上下文] 你绑定的 skill_id 是 `{skill_id}`,工作区在 `{workspace_root}`。\
             调用 Studio 工具时一律用这个 skill_id,不要从 manifest 的 name 推断,\
             也不要去磁盘上搜。",
            skill_id = context.skill_id,
            workspace_root = context.workspace_root,
        ),
    }
}

const STUDIO_AH_MANAGED_MARKER_PREFIX: &str = "<!-- studio-ah-managed hash:";
const STUDIO_AH_MANAGED_MARKER_SUFFIX: &str = " -->";

/// Resource root registered at app setup; the packaged agents-dir resolution
/// depends on it (dev builds resolve the live backend checkout instead).
static STUDIO_RESOURCE_ROOT: OnceLock<PathBuf> = OnceLock::new();

fn register_studio_resource_root(resource_root: &Path) {
    let _ = STUDIO_RESOURCE_ROOT.set(resource_root.to_path_buf());
}

/// The packaged agent-assets tree (roles / operating manual / contexts /
/// knowledge / skills / agent-skill-map). Same dev/packaged resolution as the
/// sidecar backend (`sidecar::backend_dir_for_resource_root`): a live backend
/// checkout wins in debug builds, the vendored snapshot serves the packaged
/// app. Missing tree = hard error (fail loud), never a silent fallback.
fn studio_agents_dir() -> Result<PathBuf, String> {
    if cfg!(debug_assertions) {
        if let Some(studio_dir) = PathBuf::from(env!("CARGO_MANIFEST_DIR")).parent() {
            let live = studio_dir.join("backend").join("app").join("agents");
            if live.is_dir() {
                return Ok(live);
            }
        }
    }
    if let Some(root) = STUDIO_RESOURCE_ROOT.get() {
        let packaged = root
            .join("vendor")
            .join("backend")
            .join("app")
            .join("agents");
        if packaged.is_dir() {
            return Ok(packaged);
        }
        return Err(format!(
            "studio agent assets missing at {} (vendor snapshot incomplete; re-run build_vendor.py)",
            packaged.display()
        ));
    }
    Err(
        "studio agent assets could not be resolved: no live backend tree (dev) and no \
         resource root registered (packaged)"
            .to_string(),
    )
}

/// `.ah/rules/<file>` ← the role that anchors its assembly (role + operating
/// manual + CLI surface context, per the R1.4 assembly contract).
const STUDIO_AH_RULE_FILES: &[(&str, &str)] = &[
    (".ah/rules/master.md", "moirai"),
    (".ah/rules/clotho.md", "clotho"),
    (".ah/rules/lachesis.md", "lachesis"),
    (".ah/rules/atropos.md", "atropos"),
];

fn read_agent_asset(
    assets_dir: &Path,
    relative_path: &str,
    missing: &mut Vec<String>,
) -> Option<String> {
    let path = relative_path
        .split('/')
        .fold(assets_dir.to_path_buf(), |acc, seg| acc.join(seg));
    match std::fs::read_to_string(&path) {
        Ok(body) => Some(body.trim().to_string()),
        Err(_) => {
            missing.push(relative_path.to_string());
            None
        }
    }
}

/// On-disk assembly (R1.4): one header naming the sources, then each source
/// body wrapped in BEGIN/END section markers carrying its content sha256.
fn assemble_rule_body(assets_dir: &Path, role: &str, missing: &mut Vec<String>) -> Option<String> {
    let sources = [
        format!("roles/{role}.md"),
        "operating-manual.md".to_string(),
        "contexts/cli.md".to_string(),
    ];
    let mut bodies = Vec::with_capacity(sources.len());
    for source in &sources {
        bodies.push(read_agent_asset(assets_dir, source, missing)?);
    }
    let mut assembled = format!(
        "<!-- assembled-by=studio sources={} -->\n",
        sources.join(",")
    );
    for (source, body) in sources.iter().zip(bodies) {
        let digest = &sha256_hex(&body)[..8];
        assembled.push_str(&format!(
            "<!-- BEGIN assembled-section source={source} sha256={digest} -->\n{body}\n<!-- END assembled-section source={source} -->\n"
        ));
    }
    Some(assembled)
}

fn agent_asset_file_names(dir: &Path, suffix: &str) -> Vec<String> {
    let mut names: Vec<String> = std::fs::read_dir(dir)
        .map(|entries| {
            entries
                .filter_map(|entry| entry.ok())
                .filter_map(|entry| entry.file_name().into_string().ok())
                .filter(|name| name.ends_with(suffix))
                .collect()
        })
        .unwrap_or_default();
    names.sort();
    names
}

fn agent_skill_names(assets_dir: &Path) -> Vec<String> {
    let skills_dir = assets_dir.join("skills");
    let mut names: Vec<String> = std::fs::read_dir(&skills_dir)
        .map(|entries| {
            entries
                .filter_map(|entry| entry.ok())
                .filter_map(|entry| entry.file_name().into_string().ok())
                .filter(|name| skills_dir.join(name).join("SKILL.md").is_file())
                .collect()
        })
        .unwrap_or_default();
    names.sort();
    names
}

fn load_agent_skill_map(assets_dir: &Path) -> Result<serde_json::Value, String> {
    let path = assets_dir.join("agent-skill-map.json");
    let raw = std::fs::read_to_string(&path)
        .map_err(|error| format!("failed to read {}: {error}", path.display()))?;
    serde_json::from_str(&raw).map_err(|error| format!("invalid {}: {error}", path.display()))
}

fn skills_for_agent(map: &serde_json::Value, agent: &str) -> Result<Vec<String>, String> {
    map.get(agent)
        .and_then(|value| value.as_array())
        .map(|items| {
            items
                .iter()
                .filter_map(|item| item.as_str().map(str::to_string))
                .collect()
        })
        .ok_or_else(|| format!("agent-skill-map.json has no skill list for agent '{agent}'"))
}

/// Every `.ah/` file Studio materializes for a fresh workspace, built at
/// runtime from the packaged assets. A missing source file aborts with the
/// COMPLETE missing list (fail loud), never a partial workspace.
fn studio_ah_managed_payloads() -> Result<Vec<(String, String)>, String> {
    let assets_dir = studio_agents_dir()?;
    let mut missing: Vec<String> = Vec::new();
    let mut files: Vec<(String, String)> = Vec::new();

    for (relative_path, role) in STUDIO_AH_RULE_FILES {
        if let Some(body) = assemble_rule_body(&assets_dir, role, &mut missing) {
            files.push(((*relative_path).to_string(), body));
        }
    }

    let map = load_agent_skill_map(&assets_dir);
    let mut required_skills: Vec<String> = Vec::new();
    match &map {
        Ok(map) => {
            for agent in ["moirai", "clotho", "lachesis", "atropos"] {
                required_skills.extend(skills_for_agent(map, agent).unwrap_or_default());
            }
        }
        Err(_) => missing.push("agent-skill-map.json".to_string()),
    }
    let shipped_skills = agent_skill_names(&assets_dir);
    for name in &required_skills {
        if !shipped_skills.contains(name) {
            missing.push(format!("skills/{name}/SKILL.md"));
        }
    }
    for name in &shipped_skills {
        if let Some(body) = read_agent_asset(
            &assets_dir,
            &format!("skills/{name}/SKILL.md"),
            &mut missing,
        ) {
            files.push((format!(".ah/skills/{name}/SKILL.md"), body));
        }
    }

    let knowledge_files = agent_asset_file_names(&assets_dir.join("knowledge"), ".md");
    if !knowledge_files.iter().any(|name| name == "KB-00-hub.md") {
        missing.push("knowledge/KB-00-hub.md".to_string());
    }
    for name in &knowledge_files {
        if let Some(body) =
            read_agent_asset(&assets_dir, &format!("knowledge/{name}"), &mut missing)
        {
            files.push((format!(".ah/knowledge/{name}"), body));
        }
    }

    if !missing.is_empty() {
        missing.sort();
        missing.dedup();
        return Err(format!(
            "studio agent assets incomplete under {}: missing {} file(s): {}",
            assets_dir.display(),
            missing.len(),
            missing.join(", ")
        ));
    }
    Ok(files)
}

/// The command ah runs as the interactive master.
///
/// - `IS_SANDBOX=1` lets `--dangerously-skip-permissions` run even when the WSL
///   default user is root (claude refuses that flag under root/sudo otherwise);
///   it is a harmless no-op for a normal uid.
/// - No `--continue`: a freshly opened workspace has no prior conversation, and
///   interactive `claude --continue` aborts with "No conversation found to
///   continue". (No `/remote-control` either — that opens claude's *phone*
///   remote-control dialog, irrelevant to a local terminal attach.)
/// - The trailing prompt auto-submits as the first turn → the status report.
/// Studio read/probe tools pre-allowed in a CLI session. Write and execute
/// tools are deliberately absent: they surface claude's own approval prompt,
/// which is the human gate for a session the user is sitting in front of —
/// Studio does not build a second approval system on top of it. For the same
/// reason the interactive launch drops `--dangerously-skip-permissions`.
const CLAUDE_STUDIO_ALLOWED_TOOLS: &str = concat!(
    "mcp__studio__compile_skill,",
    "mcp__studio__predict_skill,",
    "mcp__studio__get_run_detail,",
    "mcp__studio__query_run_trace,",
    "mcp__studio__wait_for_run,",
    "mcp__studio__list_golden,",
    "mcp__studio__get_golden_content,",
    "mcp__studio__get_resume_validity,",
    "mcp__studio__get_llm_roles,",
    "mcp__studio__search_llm_registry"
);

/// The master runs under ahd, which does NOT inherit the environment of the
/// shell that ran `ah start`: a session started against an already-running
/// daemon sees none of the launcher's exports. Anything the master needs must
/// therefore travel inside the command string ahd runs verbatim — the same
/// reason `build_ah_bash_script` clamps state-dir vars in-script.
fn studio_mcp_exports(studio_mcp: Option<&StudioMcpEndpoint>) -> String {
    match studio_mcp {
        Some(endpoint) => format!(
            "export STUDIO_MCP_URL={url}; export STUDIO_API_TOKEN={token}; ",
            url = sh_single_quote_str(&format!("http://127.0.0.1:{}/mcp", endpoint.port)),
            token = sh_single_quote_str(&endpoint.token),
        ),
        None => String::new(),
    }
}

fn claude_master_cmd(
    studio_mcp: Option<&StudioMcpEndpoint>,
    skill: Option<&SessionSkillContext>,
) -> String {
    let prompt = sh_single_quote_str(&master_prompt(skill));
    let claude_allowed_tools = CLAUDE_STUDIO_ALLOWED_TOOLS;
    let studio_mcp_exports = studio_mcp_exports(studio_mcp);
    let script = format!(
        "set -e; {studio_mcp_exports}export SYSTEMD_LOG_LEVEL=err; claude_real=$(command -v claude || true); if [ -z \"$claude_real\" ] && [ -n \"${{STUDIO_AH_HOST_HOME:-}}\" ] && [ -x \"$STUDIO_AH_HOST_HOME/.local/bin/claude\" ]; then claude_real=\"$STUDIO_AH_HOST_HOME/.local/bin/claude\"; fi; if [ -z \"$claude_real\" ]; then printf '%s\\n' 'claude CLI was not found on PATH.' >&2; exit 127; fi; claude_target=$(readlink -f \"$claude_real\" 2>/dev/null || printf '%s' \"$claude_real\"); case \"$claude_target\" in /mnt/*) printf '%s\\n' \"claude resolves to a Windows binary ($claude_target).\" >&2; printf '%s\\n' \"A Windows process cannot run inside ah's sandbox (it ignores HOME injection).\" >&2; printf '%s\\n' 'Fix: re-run scripts/install-claude-code-wsl.ps1 (it repairs the native install).' >&2; exit 127 ;; esac; mkdir -p \"$HOME/.local/bin\" \"$HOME/.claude\"; if [ \"$claude_real\" != \"$HOME/.local/bin/claude\" ]; then ln -sfn \"$claude_real\" \"$HOME/.local/bin/claude\"; fi; if [ -n \"${{STUDIO_AH_HOST_HOME:-}}\" ] && [ -f \"$STUDIO_AH_HOST_HOME/.claude.json\" ]; then ln -sfn \"$STUDIO_AH_HOST_HOME/.claude.json\" \"$HOME/.claude.json\"; fi; if [ -n \"${{STUDIO_AH_HOST_HOME:-}}\" ] && [ -f \"$STUDIO_AH_HOST_HOME/.claude/.credentials.json\" ]; then ln -sfn \"$STUDIO_AH_HOST_HOME/.claude/.credentials.json\" \"$HOME/.claude/.credentials.json\"; fi; export IS_SANDBOX=1; studio_mcp_args=; if [ -n \"${{STUDIO_MCP_URL:-}}\" ]; then studio_mcp_cfg=\"$HOME/.claude/studio-mcp.json\"; printf '%s\\n' '{{\"mcpServers\":{{\"studio\":{{\"type\":\"http\",\"url\":\"${{STUDIO_MCP_URL}}\",\"headers\":{{\"Authorization\":\"Bearer ${{STUDIO_API_TOKEN}}\"}}}}}}}}' > \"$studio_mcp_cfg\"; studio_mcp_args=\"--mcp-config $studio_mcp_cfg --allowedTools {claude_allowed_tools}\"; fi; exec \"$claude_real\" $studio_mcp_args {prompt}"
    );
    format!("bash -c {}", sh_single_quote_str(&script))
}

/// The Codex master uses Codex-native locations inside ah's sandbox:
///
/// - `$HOME/.codex/auth.json` for ChatGPT auth, linked from the WSL host copy
///   that Studio refreshes from Windows before `ah start`.
/// - `$HOME/.codex/AGENTS.md` for the MoirAI master instructions.
/// - `$HOME/.agents/skills` for Studio-managed skills, matching Codex's
///   documented local skill discovery path.
fn codex_master_cmd(
    studio_mcp: Option<&StudioMcpEndpoint>,
    skill: Option<&SessionSkillContext>,
) -> String {
    let prompt = sh_single_quote_str(&master_prompt(skill));
    let studio_mcp_exports = studio_mcp_exports(studio_mcp);
    let script = format!(
        "set -e; {studio_mcp_exports}export SYSTEMD_LOG_LEVEL=err; codex_real=; if [ -n \"${{STUDIO_AH_HOST_HOME:-}}\" ] && [ -x \"$STUDIO_AH_HOST_HOME/.codex/packages/standalone/current/bin/codex\" ]; then codex_real=\"$STUDIO_AH_HOST_HOME/.codex/packages/standalone/current/bin/codex\"; fi; if [ -z \"$codex_real\" ]; then codex_real=$(command -v codex || true); fi; if [ -z \"$codex_real\" ] && [ -n \"${{STUDIO_AH_HOST_HOME:-}}\" ] && [ -x \"$STUDIO_AH_HOST_HOME/.local/bin/codex\" ]; then codex_real=\"$STUDIO_AH_HOST_HOME/.local/bin/codex\"; fi; if [ -z \"$codex_real\" ]; then printf '%s\\n' 'codex CLI was not found on PATH.' >&2; exit 127; fi; codex_target=$(readlink -f \"$codex_real\" 2>/dev/null || printf '%s' \"$codex_real\"); case \"$codex_target\" in /mnt/*) printf '%s\\n' \"codex resolves to a Windows binary ($codex_target).\" >&2; printf '%s\\n' \"A Windows process cannot run inside ah's sandbox (it ignores HOME injection).\" >&2; printf '%s\\n' 'Fix: re-run scripts/install-claude-code-wsl.ps1 (it repairs the native install).' >&2; exit 127 ;; esac; mkdir -p \"$HOME/.local/bin\" \"$HOME/.codex\" \"$HOME/.agents\"; codex_config=\"$HOME/.codex/config.toml\"; if [ \"$codex_real\" != \"$HOME/.local/bin/codex\" ]; then ln -sfn \"$codex_real\" \"$HOME/.local/bin/codex\"; fi; if [ -n \"${{STUDIO_AH_HOST_HOME:-}}\" ] && [ -f \"$STUDIO_AH_HOST_HOME/.codex/auth.json\" ]; then ln -sfn \"$STUDIO_AH_HOST_HOME/.codex/auth.json\" \"$HOME/.codex/auth.json\"; fi; codex_project_key=$(printf '%s' \"$PWD\" | sed 's/\\\\/\\\\\\\\/g; s/\"/\\\\\"/g'); codex_trust_header=\"[projects.\\\"$codex_project_key\\\"]\"; if ! grep -Fqx \"$codex_trust_header\" \"$codex_config\" 2>/dev/null; then {{ if [ -s \"$codex_config\" ]; then printf '\\n'; fi; printf '%s\\ntrust_level = \"trusted\"\\n' \"$codex_trust_header\"; }} >> \"$codex_config\"; fi; codex_mcp_header=\"[mcp_servers.codex_apps]\"; if grep -Fqx \"$codex_mcp_header\" \"$codex_config\" 2>/dev/null; then if awk 'BEGIN{{in_section=0; found=1}} /^\\[mcp_servers\\.codex_apps\\]$/{{in_section=1; next}} /^\\[/{{in_section=0}} in_section && /^[[:space:]]*startup_timeout_sec[[:space:]]*=/{{found=0}} END{{exit found}}' \"$codex_config\"; then sed -i '/^\\[mcp_servers\\.codex_apps\\]$/,/^\\[/ s/^[[:space:]]*startup_timeout_sec[[:space:]]*=.*/startup_timeout_sec = 120/' \"$codex_config\"; else sed -i '/^\\[mcp_servers\\.codex_apps\\]$/a startup_timeout_sec = 120' \"$codex_config\"; fi; else {{ if [ -s \"$codex_config\" ]; then printf '\\n'; fi; printf '%s\\nstartup_timeout_sec = 120\\n' \"$codex_mcp_header\"; }} >> \"$codex_config\"; fi; if [ -f \"$PWD/.ah/rules/master.md\" ]; then ln -sfn \"$PWD/.ah/rules/master.md\" \"$HOME/.codex/AGENTS.md\"; fi; if [ -d \"$PWD/.ah/skills\" ]; then rm -rf \"$HOME/.agents/skills\"; ln -sfn \"$PWD/.ah/skills\" \"$HOME/.agents/skills\"; fi; if [ -n \"${{STUDIO_MCP_URL:-}}\" ]; then studio_mcp_header=\"[mcp_servers.studio]\"; if ! grep -Fqx \"$studio_mcp_header\" \"$codex_config\" 2>/dev/null; then {{ if [ -s \"$codex_config\" ]; then printf '\\n'; fi; printf '%s\\nurl = \"%s\"\\nbearer_token_env_var = \"STUDIO_API_TOKEN\"\\n' \"$studio_mcp_header\" \"${{STUDIO_MCP_URL}}\"; }} >> \"$codex_config\"; fi; fi; exec \"$codex_real\" --dangerously-bypass-approvals-and-sandbox --dangerously-bypass-hook-trust {prompt}"
    );
    format!("bash -c {}", sh_single_quote_str(&script))
}

fn sha256_hex(value: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(value.as_bytes());
    hasher
        .finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn studio_managed_marker(body: &str) -> String {
    format!(
        "{STUDIO_AH_MANAGED_MARKER_PREFIX}{}{}",
        sha256_hex(body),
        STUDIO_AH_MANAGED_MARKER_SUFFIX
    )
}

fn frontmatter_insert_offset(body: &str) -> Option<usize> {
    if !body.starts_with("---\n") && !body.starts_with("---\r\n") {
        return None;
    }
    let mut offset = 0;
    let mut fence_count = 0;
    for line in body.split_inclusive('\n') {
        offset += line.len();
        if line.trim_end_matches(&['\r', '\n'][..]) == "---" {
            fence_count += 1;
            if fence_count == 2 {
                return Some(offset);
            }
        }
    }
    None
}

fn with_studio_managed_marker(body: &str) -> String {
    let marker = studio_managed_marker(body);
    if let Some(offset) = frontmatter_insert_offset(body) {
        let (frontmatter, content) = body.split_at(offset);
        return format!("{frontmatter}{marker}\n{content}");
    }
    format!("{marker}\n{body}")
}

fn extract_studio_managed_hash(content: &str) -> Option<&str> {
    content.lines().find_map(|line| {
        let trimmed = line.trim();
        let hash = trimmed.strip_prefix(STUDIO_AH_MANAGED_MARKER_PREFIX)?;
        hash.strip_suffix(STUDIO_AH_MANAGED_MARKER_SUFFIX)
    })
}

fn strip_studio_managed_marker(content: &str) -> String {
    content
        .split_inclusive('\n')
        .filter(|line| {
            let trimmed = line.trim();
            !trimmed.starts_with(STUDIO_AH_MANAGED_MARKER_PREFIX)
                || !trimmed.ends_with(STUDIO_AH_MANAGED_MARKER_SUFFIX)
        })
        .collect()
}

fn studio_ah_file_path(workspace_root: &Path, relative_path: &str) -> PathBuf {
    relative_path
        .split('/')
        .fold(workspace_root.to_path_buf(), |path, segment| {
            path.join(segment)
        })
}

fn write_studio_managed_file(path: &Path, body: &str) -> Result<(), String> {
    if path.exists() {
        if !path.is_file() {
            return Err(format!(
                "refusing to overwrite non-file ah path: {}",
                path.display()
            ));
        }
        let existing = std::fs::read_to_string(path).map_err(|error| {
            format!(
                "failed to read existing ah file {}: {error}",
                path.display()
            )
        })?;
        let previous_hash = extract_studio_managed_hash(&existing).ok_or_else(|| {
            format!(
                "refusing to overwrite unmanaged ah file: {}",
                path.display()
            )
        })?;
        let existing_body = strip_studio_managed_marker(&existing);
        let actual_hash = sha256_hex(&existing_body);
        if previous_hash != actual_hash {
            return Err(format!(
                "refusing to overwrite modified Studio-managed ah file: {}",
                path.display()
            ));
        }
    }
    let parent = path
        .parent()
        .ok_or_else(|| format!("cannot resolve ah file parent: {}", path.display()))?;
    std::fs::create_dir_all(parent)
        .map_err(|error| format!("failed to create ah file dir {}: {error}", parent.display()))?;
    std::fs::write(path, with_studio_managed_marker(body))
        .map_err(|error| format!("failed to write ah file {}: {error}", path.display()))
}

fn prepare_studio_ah_workspace(workspace_root: &Path) -> Result<(), String> {
    for (relative_path, body) in studio_ah_managed_payloads()? {
        let path = studio_ah_file_path(workspace_root, &relative_path);
        write_studio_managed_file(&path, &body)?;
    }
    Ok(())
}

/// Serialize one TOML basic string.
///
/// A basic string may not contain a literal newline, so a value carrying one
/// silently produced an unparseable config: `ah start` died with `invalid basic
/// string` (exit 3) and the CLI session could not open at all. Control
/// characters are therefore escaped, not passed through.
fn toml_string(value: &str) -> String {
    let mut escaped = String::with_capacity(value.len() + 2);
    escaped.push('"');
    for character in value.chars() {
        match character {
            '\\' => escaped.push_str("\\\\"),
            '"' => escaped.push_str("\\\""),
            '\n' => escaped.push_str("\\n"),
            '\r' => escaped.push_str("\\r"),
            '\t' => escaped.push_str("\\t"),
            other => escaped.push(other),
        }
    }
    escaped.push('"');
    escaped
}

fn toml_string_array(values: &[String]) -> String {
    let items = values
        .iter()
        .map(|value| toml_string(value))
        .collect::<Vec<_>>()
        .join(", ");
    format!("[{items}]")
}

fn transient_ah_config_content(
    assistant: CodeAssistant,
    studio_mcp: Option<&StudioMcpEndpoint>,
    skill: Option<&SessionSkillContext>,
) -> Result<String, String> {
    let provider = assistant.provider();
    let assets_dir = studio_agents_dir()?;
    // skills 由 agent-skill-map.json 派生(R5.5/R7.3):backend 的
    // AgentDefinition.skills 与这里同源,不再各自硬编码。
    let map = load_agent_skill_map(&assets_dir)?;
    let master_skills = skills_for_agent(&map, "moirai")?;
    let clotho_skills = skills_for_agent(&map, "clotho")?;
    let lachesis_skills = skills_for_agent(&map, "lachesis")?;
    let atropos_skills = skills_for_agent(&map, "atropos")?;
    // ah >= 1.3.4 injects worker sandbox env natively. Studio only keeps the
    // Claude master root escape via `export IS_SANDBOX=1` in its cmd string.
    Ok(format!(
        "version = \"1\"\n\n[master]\nenabled = true\nprovider = {provider_toml}\ncmd = {cmd}\nreadiness_timeout_s = 180\nwindow_size = \"follow\"\nskills = {master_skills}\n\n[agents.clotho]\nprovider = {provider_toml}\nskills = {clotho_skills}\n\n[agents.lachesis]\nprovider = {provider_toml}\nskills = {lachesis_skills}\n\n[agents.atropos]\nprovider = {provider_toml}\nskills = {atropos_skills}\n",
        provider_toml = toml_string(provider),
        cmd = toml_string(&assistant.master_cmd(studio_mcp, skill)),
        master_skills = toml_string_array(&master_skills),
        clotho_skills = toml_string_array(&clotho_skills),
        lachesis_skills = toml_string_array(&lachesis_skills),
        atropos_skills = toml_string_array(&atropos_skills),
    ))
}

fn ah_config_for_workspace(
    workspace_root: &Path,
    assistant: CodeAssistant,
    studio_mcp: Option<&StudioMcpEndpoint>,
    skill: Option<&SessionSkillContext>,
) -> Result<PathBuf, String> {
    if let Some(config) = find_ah_config(workspace_root) {
        return Ok(config);
    }
    prepare_studio_ah_workspace(workspace_root)?;
    let config = transient_ah_config_path(workspace_root, assistant);
    let parent = config
        .parent()
        .ok_or_else(|| format!("cannot resolve ah config parent: {}", config.display()))?;
    std::fs::create_dir_all(parent)
        .map_err(|error| format!("failed to create transient ah config dir: {error}"))?;
    std::fs::write(&config, transient_ah_config_content(assistant, studio_mcp, skill)?)
        .map_err(|error| format!("failed to write transient ah config: {error}"))?;
    Ok(config)
}

fn ah_config_for_status(workspace_root: &Path, assistant: CodeAssistant) -> Option<PathBuf> {
    find_ah_config(workspace_root).or_else(|| {
        let transient = transient_ah_config_path(workspace_root, assistant);
        transient.is_file().then_some(transient)
    })
}

fn command_result(mut command: Command, label: &str) -> Result<CommandResult, String> {
    command
        .output()
        .map(CommandResult::from_output)
        .map_err(|error| format!("failed to run {label}: {error}"))
}

/// The bash `-c` script the Windows `wsl.exe -e bash -lc` path runs for an ah
/// command (Req 4.7 / 坑洞 3.5). The state-dir env — `AH_STATE_DIR`,
/// `CCBD_STATE_DIR`, `XDG_STATE_HOME` — is clamped to empty INSIDE the script
/// string, before the ah command reads the environment: a `-lc` login shell
/// re-sources the user profile AFTER inheriting Rust's `Command::env`, so a
/// Rust-side clamp would be silently overwritten, whereas an in-script `export`
/// runs after the profile and wins. Both `run_ah_config_command_output` and
/// `spawn_ah_events_command` build their Windows script through this single seam
/// so the clamp cannot drift between the two call sites.
fn build_ah_bash_script(config_path: &Path, ah_args: &[&str]) -> String {
    let args = ah_args
        .iter()
        .map(|arg| sh_single_quote_str(arg))
        .collect::<Vec<_>>()
        .join(" ");
    format!(
        "export AH_STATE_DIR=\"\"; export CCBD_STATE_DIR=\"\"; export XDG_STATE_HOME=\"\"; \
export PATH=\"$HOME/.cargo/bin:$HOME/.local/bin:$PATH\"; export SYSTEMD_LOG_LEVEL=err; \
ah --config {} {}",
        sh_single_quote_str(&windows_path_to_wsl(config_path)),
        args
    )
}

fn run_ah_config_command_output(
    config_path: &Path,
    ah_args: &[&str],
) -> Result<CommandResult, String> {
    if cfg!(target_os = "windows") {
        let mut command = Command::new("wsl.exe");
        let script = build_ah_bash_script(config_path, ah_args);
        command.args(["-e", "bash", "-lc", &script]);
        return command_result(command, "ah");
    }

    let mut command = Command::new("ah");
    command.env("SYSTEMD_LOG_LEVEL", "err");
    command.arg("--config").arg(config_path).args(ah_args);
    command_result(command, "ah")
}

fn run_ah_config_command(config_path: &Path, ah_args: &[&str]) -> Result<bool, String> {
    run_ah_config_command_output(config_path, ah_args).map(|result| result.success)
}

fn spawn_ah_events_command(config_path: &Path) -> Result<Child, String> {
    let mut command = if cfg!(target_os = "windows") {
        let mut command = Command::new("wsl.exe");
        let script = build_ah_bash_script(config_path, &["events", "--format", "json"]);
        command.args(["-e", "bash", "-lc", &script]);
        command
    } else {
        let mut command = Command::new("ah");
        command.env("SYSTEMD_LOG_LEVEL", "err");
        command
            .arg("--config")
            .arg(config_path)
            .args(["events", "--format", "json"]);
        command
    };
    command.stdout(Stdio::piped()).stderr(Stdio::null());
    command
        .spawn()
        .map_err(|error| format!("failed to run ah events: {error}"))
}

fn stop_ah_config(config_path: &Path) -> Result<bool, String> {
    run_ah_config_command(config_path, &["stop"])
}

fn tmux_socket_label_is_safe(label: &str) -> bool {
    !label.is_empty()
        && label
            .chars()
            .all(|ch| ch.is_ascii_alphanumeric() || ch == '-' || ch == '_' || ch == '.')
}

fn extract_tmux_socket_label(text: &str) -> Option<String> {
    for suffix in text.split("tmux -L ").skip(1) {
        let Some(raw_label) = suffix.split_whitespace().next() else {
            continue;
        };
        let label = raw_label.trim_matches(|ch| ch == '\'' || ch == '"' || ch == '`');
        if tmux_socket_label_is_safe(label) {
            return Some(label.to_string());
        }
    }
    None
}

fn extract_ah_session_ids(text: &str) -> Vec<String> {
    text.split_whitespace()
        .map(|token| {
            token.trim_matches(|ch: char| !(ch.is_ascii_alphanumeric() || ch == '_' || ch == '-'))
        })
        .filter(|token| token.starts_with("sess_"))
        .map(str::to_string)
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect()
}

fn ah_ps_output_has_inventory(text: &str) -> bool {
    !extract_ah_session_ids(text).is_empty()
}

/// Escalate `ah kill --session <id> --force` to exactly the sessions ah itself
/// flagged for cleanup in the identity-checked snapshot (`cleanup_target_session_ids`)
/// — never a Studio "non-terminal ⇒ kill" re-derivation, and never a direct tmux
/// kill (design.md:226-227, Req 4.2/5.5). The caller has already gated
/// `config_path` to a Studio-managed config (ownership skip + lifecycle guard),
/// so no further ownership check runs here. Returns whether any kill reported
/// success, so the close can report whether it actually tore something down.
fn force_cleanup_ah_sessions(config_path: &Path, snapshot: &AhRuntimeSnapshot) -> bool {
    let mut killed_any = false;
    for session_id in cleanup_target_session_ids(snapshot) {
        match run_ah_config_command(config_path, &["kill", "--session", &session_id, "--force"]) {
            Ok(true) => {
                killed_any = true;
                log::info!(
                    "phase=code-assistant-cleanup action=ah-kill-session-ok config={} session_id={session_id}",
                    config_path.display()
                );
            }
            Ok(false) => log::info!(
                "phase=code-assistant-cleanup action=ah-kill-session-skip config={} session_id={session_id}",
                config_path.display()
            ),
            Err(error) => log::warn!(
                "phase=code-assistant-cleanup action=ah-kill-session-failed config={} session_id={session_id} error={error}",
                config_path.display()
            ),
        }
    }
    killed_any
}

/// Close a single ah config, crossing NO ownership boundary (design.md 215-228).
///
/// A workspace-owned config (a walked-up repo-root `ah.toml` outside the Studio
/// temp namespace) belongs to the operator's own fleet: skip it transparently —
/// issue no lifecycle command, and never abort the sweep over the remaining
/// Studio-managed configs (Req 5.9/4.6). The skip is ownership-selective, sourced
/// from the single ownership authority, not a blanket no-op.
///
/// For a Studio-managed config the normal close is `ah stop`; then the current
/// snapshot is re-read through the typed events-primary/status-fallback plane
/// (identity-checked when the workspace is known), and `ah kill --session <id>
/// --force` is escalated ONLY to the sessions ah itself flagged `cleanup_required`
/// — never Studio re-deriving "non-terminal therefore kill", never a direct tmux
/// kill (design.md:225-227).
fn cleanup_code_assistant_config(
    config_path: &Path,
    workspace_dir: Option<&Path>,
) -> Result<bool, String> {
    if classify_config_ownership(config_path).read_only {
        return Ok(false);
    }
    // Fail-closed boundary: the ownership skip above already excludes
    // workspace-owned configs, so this always passes here; it keeps
    // `ensure_lifecycle_command_allowed` the single authority guarding every path
    // that can emit a lifecycle command.
    ensure_lifecycle_command_allowed(config_path)?;
    check_ah_version_cached()?;

    let stopped = stop_ah_config(config_path)?;

    let killed_any = resolve_cleanup_snapshot(config_path, workspace_dir)
        .map(|snapshot| force_cleanup_ah_sessions(config_path, &snapshot))
        .unwrap_or(false);

    Ok(stopped || killed_any)
}

/// 每轮确认之间的等待。ah 的 shutdown 是"先回 RPC、50ms 后自发 SIGTERM、再在信号路径里
/// 逐个 kill-session 并 kill-server",所以确认必然要跨若干轮。
const AH_STOP_CONFIRM_POLL_INTERVAL: Duration = Duration::from_millis(300);

/// 确认运行时消失的最多轮数。用满仍未确认就如实报告失败，由调用方保留可关闭状态。
const AH_STOP_CONFIRM_MAX_ATTEMPTS: u32 = 5;

/// 轮询确认 ah 运行时确实消失了。
///
/// 因果验证(AGENTS.md 铁律):`ah stop` 只是把停止命令送达 ahd,命令返回不能证明 tmux 已被
/// 回收——ahd 是先回 RPC、再自发 SIGTERM,真正的回收发生在信号处理路径里。在确认之前就对外
/// 宣布"已清理",面板会在残留还在时把控件变回 `Open in CLI`,破坏"控件可开 ⇒ 残留已清"这条
/// 不变量。
///
/// 探测器由调用方注入(生产实现在其中读快照并退避等待),因此这段判定逻辑可以脱离子进程离线
/// 验证。返回 `true` 表示已确认消失(探测不到快照,或快照自报 `ahd_alive:false`);
/// `false` 表示用满轮数仍未确认——调用方必须据此保留可关闭状态,不得谎报已清理。
fn wait_until_ah_runtime_gone<P>(mut probe: P, max_attempts: u32) -> bool
where
    P: FnMut(u32) -> Option<AhRuntimeSnapshot>,
{
    (0..max_attempts).any(|attempt| match probe(attempt) {
        None => true,
        Some(snapshot) => !snapshot.ahd_alive,
    })
}

fn workspace_code_assistant_configs(workspace_root: &Path) -> BTreeSet<PathBuf> {
    CodeAssistant::ALL
        .iter()
        .filter_map(|assistant| ah_config_for_status(workspace_root, *assistant))
        .collect()
}

struct CodeAssistantCleanupResult {
    configs: BTreeSet<PathBuf>,
    closed_any: bool,
    runtime_confirmed_gone: bool,
}

fn cleanup_workspace_code_assistants(
    workspace_root: &Path,
) -> Result<CodeAssistantCleanupResult, String> {
    let configs = workspace_code_assistant_configs(workspace_root);
    let mut closed_any = false;
    for config in &configs {
        closed_any |= cleanup_code_assistant_config(config, Some(workspace_root))?;
    }

    // 因果验证(AGENTS.md 铁律):上面只是把停止命令送达 ahd —— ahd 先回 RPC、再自发 SIGTERM,
    // 真正的 kill-session / kill-server 发生在信号处理路径里。所以这里必须观察到运行时确实
    // 消失,才能对外说"清干净了";只要有一个 config 没确认,整次清理就不算确认——不能被其中
    // 一个成功的掩盖。工作区自己的 ah.toml 不归 Studio 管(上面就跳过了没发命令),自然也不
    // 该因它把面板卡在可关闭态。
    let runtime_confirmed_gone = configs.iter().all(|config| {
        classify_config_ownership(config).read_only
            || wait_until_ah_runtime_gone(
                |attempt| {
                    if attempt > 0 {
                        std::thread::sleep(AH_STOP_CONFIRM_POLL_INTERVAL);
                    }
                    resolve_cleanup_snapshot(config, Some(workspace_root))
                },
                AH_STOP_CONFIRM_MAX_ATTEMPTS,
            )
    });

    Ok(CodeAssistantCleanupResult {
        configs,
        closed_any,
        runtime_confirmed_gone,
    })
}

fn code_assistant_status_specs_for_workspace(
    workspace_root: &Path,
) -> BTreeMap<PathBuf, CodeAssistantStatusSpec> {
    let mut specs = BTreeMap::new();
    for assistant in CodeAssistant::ALL {
        if let Some(config_path) = ah_config_for_status(workspace_root, assistant) {
            specs.entry(config_path).or_insert(CodeAssistantStatusSpec {
                workspace_root: workspace_root.to_path_buf(),
                assistant,
            });
        }
    }
    specs
}

fn status_specs_for_workspace(
    state: &CodeAssistantRuntimeState,
    workspace_root: &Path,
) -> BTreeMap<PathBuf, CodeAssistantStatusSpec> {
    state
        .status_specs
        .lock()
        .expect("code assistant status specs poisoned")
        .iter()
        .filter(|(_, spec)| spec.workspace_root == workspace_root)
        .map(|(config, spec)| (config.clone(), spec.clone()))
        .collect()
}

fn next_status_specs_for_workspace(
    state: &CodeAssistantRuntimeState,
    workspace_root: &Path,
) -> BTreeMap<PathBuf, CodeAssistantStatusSpec> {
    let mut specs = code_assistant_status_specs_for_workspace(workspace_root);
    let registered_configs = state
        .configs
        .lock()
        .expect("code assistant state poisoned")
        .clone();
    let registered_specs = state
        .status_specs
        .lock()
        .expect("code assistant status specs poisoned")
        .clone();

    for (config, spec) in registered_specs {
        if spec.workspace_root == workspace_root && registered_configs.contains(&config) {
            specs.insert(config, spec);
        }
    }

    specs
}

fn snapshots_for_configs(
    state: &CodeAssistantRuntimeState,
    specs: &BTreeMap<PathBuf, CodeAssistantStatusSpec>,
) -> BTreeMap<PathBuf, AhRuntimeSnapshot> {
    let snapshots = state
        .status_snapshots
        .lock()
        .expect("code assistant status snapshots poisoned");
    specs
        .keys()
        .filter_map(|config| {
            snapshots
                .get(config)
                .map(|snapshot| (config.clone(), snapshot.clone()))
        })
        .collect()
}

fn code_assistant_status_from_snapshots(
    specs: &BTreeMap<PathBuf, CodeAssistantStatusSpec>,
    snapshots: &BTreeMap<PathBuf, AhRuntimeSnapshot>,
) -> CodeAssistantStatus {
    let mut claude_state = AssistantState {
        status: AssistantStatus::Inactive,
        reason: None,
        read_only: false,
    };
    let mut codex_state = AssistantState {
        status: AssistantStatus::Inactive,
        reason: None,
        read_only: false,
    };

    for (config, spec) in specs {
        // Project the typed snapshot onto the UI status (SSOT, design.md:132-133): each phase
        // renders distinctly instead of collapsing every non-active phase to "inactive", and an
        // `inactive` phase whose ahd is still alive projects to `lingering` (决议 2026-08-02
        // D-A1). 有 spec 但一帧都还没拿到 ⇒ `Unknown`：这时 Studio 只是尚未观测，说不出
        // 「运行时已被回收」这句断言（决议 2026-08-03 D-C3）。而**没有 spec** 的助手保持
        // 下面的 `Inactive` 默认值——磁盘上没有 ah 配置本身就是一次真实观测。
        let status_val = snapshots
            .get(config)
            .map(assistant_status_for_snapshot)
            .unwrap_or(AssistantStatus::Unknown);
        let read_only = classify_config_ownership(config).read_only;
        let state = AssistantState {
            status: status_val,
            reason: None,
            read_only,
        };
        match spec.assistant {
            CodeAssistant::Claude => claude_state = state,
            CodeAssistant::Codex => codex_state = state,
        }
    }

    CodeAssistantStatus {
        claude: claude_state,
        codex: codex_state,
    }
}

fn emit_code_assistant_status_for_workspace(
    app: &tauri::AppHandle,
    state: &CodeAssistantRuntimeState,
    workspace_root: &Path,
) {
    let specs = status_specs_for_workspace(state, workspace_root);
    let snapshots = snapshots_for_configs(state, &specs);
    let status = code_assistant_status_from_snapshots(&specs, &snapshots);
    if let Err(error) = app.emit(
        CODE_ASSISTANT_STATUS_EVENT,
        CodeAssistantStatusEvent {
            workspace_root: workspace_root.display().to_string(),
            status,
        },
    ) {
        log::warn!("phase=code-assistant-status action=emit-failed error={error}");
    }
}

/// 重开这个 workspace 的观察流,让它对着**当前**的 daemon 事实重新基线。
///
/// 为什么不是"清空快照缓存"就够(2026-08-04 真机复现):`ah stop` 杀掉的是 ahd,而这个
/// config 的 `ah events` 子进程**不会随之退出**——它只是从此永远不再发帧(实测:ahd 停掉
/// 后子进程仍存活 3 分钟以上,监督循环零重生、日志零 `events-exited-respawning`)。所以
/// 只清缓存的话,缓存就再也没有任何东西能把它填回来:投影按「尚未观测」给出 `unknown`,
/// 面板把 Open 控件永久禁用,使用者连重新打开 CLI 的入口都没有了。
///
/// 一条流绑定的是**某一个 daemon 实例**,不是这份 config。Studio 自己改变了 daemon 的
/// 存亡,就必须把观察者一起重开——重开后的 `ah events` 立刻发一帧 `daemon_absent`
/// (`ahd_alive:false`),投影成 `inactive`,Open 恢复可点。
fn restart_status_streams_for_workspace(
    app: &tauri::AppHandle,
    state: &CodeAssistantRuntimeState,
    workspace_root: &Path,
) -> Result<(), String> {
    for config in status_specs_for_workspace(state, workspace_root).keys() {
        drop_status_stream(state, config);
    }
    ensure_code_assistant_status_streams_for_workspace(app, state, workspace_root)
}

fn handle_code_assistant_status_snapshot(
    app: &tauri::AppHandle,
    config_path: &Path,
    snapshot: AhRuntimeSnapshot,
) {
    let Some(state) = app.try_state::<CodeAssistantRuntimeState>() else {
        return;
    };
    let workspace_root = {
        let specs = state
            .status_specs
            .lock()
            .expect("code assistant status specs poisoned");
        specs
            .get(config_path)
            .map(|spec| spec.workspace_root.clone())
    };
    let Some(workspace_root) = workspace_root else {
        return;
    };

    state
        .status_snapshots
        .lock()
        .expect("code assistant status snapshots poisoned")
        .insert(config_path.to_path_buf(), snapshot);

    // Snapshots only drive the status display. A cold-starting runtime
    // (inventory ACTIVE, master tmux not up for ~15s) is indistinguishable
    // from a stale leftover here, so auto-cleanup on event snapshots would
    // kill the runtime `ah start` is still bringing up. Cleanup happens on
    // user actions only (open/attach/close/quit).
    emit_code_assistant_status_for_workspace(app, &state, &workspace_root);
}

fn stop_code_assistant_status_stream(stream: CodeAssistantStatusStream) {
    stream.stop.store(true, Ordering::SeqCst);
    if let Some(mut child) = stream
        .child
        .lock()
        .expect("code assistant events child poisoned")
        .take()
    {
        let _ = child.kill();
        let _ = child.wait();
    }
}

/// 冷启动播种：该 config 一帧都没有时，读一次 `status --json` 并按与 events 帧完全相同的
/// 路径写进缓存（决议 2026-08-03 D-C4）。读不到就什么也不做——投影层保持 `unknown`，
/// 由随后到达的 events 首帧接手。
fn seed_bootstrap_snapshot(app: &tauri::AppHandle, config_path: &Path, workspace_root: &Path) {
    let Some(state) = app.try_state::<CodeAssistantRuntimeState>() else {
        return;
    };
    let needs_seed = {
        let snapshots = state
            .status_snapshots
            .lock()
            .expect("code assistant status snapshots poisoned");
        needs_bootstrap_seed(&snapshots, config_path)
    };
    if !needs_seed {
        return;
    }
    match resolve_open_snapshot(None, config_path, workspace_root) {
        Some(snapshot) => {
            log::info!(
                "phase=code-assistant-status action=bootstrap-seeded config={} runtime_state={:?}",
                config_path.display(),
                snapshot.runtime_state
            );
            handle_code_assistant_status_snapshot(app, config_path, snapshot);
        }
        None => log::info!(
            "phase=code-assistant-status action=bootstrap-empty config={}",
            config_path.display()
        ),
    }
}

fn start_code_assistant_status_stream(
    app: tauri::AppHandle,
    config_path: PathBuf,
    workspace_root: PathBuf,
) -> Result<CodeAssistantStatusStream, String> {
    check_ah_version_cached()?;
    let stop = Arc::new(AtomicBool::new(false));
    let child_slot: Arc<Mutex<Option<Child>>> = Arc::new(Mutex::new(None));
    let thread_stop = Arc::clone(&stop);
    let thread_child = Arc::clone(&child_slot);
    std::thread::spawn(move || {
        // events 为主、`status --json` 作 bootstrap（design.md「Live status subscription」）
        // ——这条规则原先只接在生命周期判定那条道上（`resolve_open_snapshot`），UI 投影
        // 这条道没接，于是"还没观测到"被投影成 `inactive` 那句断言。在这里补上（决议
        // 2026-08-03 D-C4）。放在流线程而不是 `watch` 命令里：这一读要跨 WSL，耗时以秒计，
        // 阻塞 IPC 会拖住前台；这段时间面板呈现的是诚实的 `unknown`。
        seed_bootstrap_snapshot(&app, &config_path, &workspace_root);
        // The events child can die for reasons that are not stop requests —
        // WSL still booting when the app comes up, `wsl --shutdown`, crashes.
        // A one-shot child would leave the status frozen on its last
        // snapshot, so supervise it: respawn with a short backoff until this
        // stream is explicitly stopped. The respawned `ah events` immediately
        // emits a fresh snapshot (local inactive when the daemon is absent),
        // which corrects any staleness accumulated during the gap.
        let backoff = |stop_flag: &AtomicBool| {
            for _ in 0..30 {
                if stop_flag.load(Ordering::SeqCst) {
                    return true;
                }
                std::thread::sleep(Duration::from_millis(100));
            }
            false
        };
        while !thread_stop.load(Ordering::SeqCst) {
            let mut child = match spawn_ah_events_command(&config_path) {
                Ok(child) => child,
                Err(error) => {
                    log::warn!(
                        "phase=code-assistant-status action=events-spawn-failed config={} error={error}",
                        config_path.display()
                    );
                    if backoff(&thread_stop) {
                        break;
                    }
                    continue;
                }
            };
            let Some(stdout) = child.stdout.take() else {
                let _ = child.kill();
                let _ = child.wait();
                log::warn!("phase=code-assistant-status action=events-no-stdout");
                if backoff(&thread_stop) {
                    break;
                }
                continue;
            };
            *thread_child
                .lock()
                .expect("code assistant events child poisoned") = Some(child);
            let reader = BufReader::new(stdout);
            for line in reader.lines() {
                if thread_stop.load(Ordering::SeqCst) {
                    break;
                }
                match line {
                    Ok(line) => {
                        // events-primary: each `ah events --format json` snapshot line is the
                        // typed v2 `AhRuntimeSnapshot` (design.md:325). Non-snapshot event lines
                        // (or any that fail schema validation) are skipped, never collapsed to a
                        // boolean plane.
                        if let Ok(snapshot) = parse_ah_runtime_snapshot(&line) {
                            handle_code_assistant_status_snapshot(&app, &config_path, snapshot);
                        }
                    }
                    Err(error) => {
                        log::warn!(
                            "phase=code-assistant-status action=events-read-failed error={error}"
                        );
                        break;
                    }
                }
            }
            if let Some(mut child) = thread_child
                .lock()
                .expect("code assistant events child poisoned")
                .take()
            {
                let _ = child.kill();
                let _ = child.wait();
            }
            if thread_stop.load(Ordering::SeqCst) {
                break;
            }
            log::warn!(
                "phase=code-assistant-status action=events-exited-respawning config={}",
                config_path.display()
            );
            if backoff(&thread_stop) {
                break;
            }
        }
    });
    Ok(CodeAssistantStatusStream {
        stop,
        child: child_slot,
    })
}

/// 观察用生产者集合的**策略**：谁该存在、谁该停。与 spawn/kill 的**机制**分离，
/// 所以它可以被纯数据单测（AGENTS.md「副作用隔离」）。
#[derive(Debug, PartialEq, Eq)]
struct StatusStreamPlan {
    start: Vec<PathBuf>,
    stop: Vec<PathBuf>,
}

/// 决议 2026-08-03 D-C2：生产者集合只由「当前被观察的 workspace」决定。
///
/// - **该存在的** = `watched`（当前 workspace 的全部 config）。Studio 同一时刻只显示一个
///   工作区，用这条不变量给生产者数量定上界——这是删掉订阅者驱动的 teardown（D-C1）
///   之后仍然需要的资源上界。
/// - **该停的** = 已登记或已在跑、但不在 `watched` 里的：切走的工作区，以及本工作区里
///   已经消失的 config。**正在被观察的生产者永远不在这个集合里**，缺陷 C 里"卸载一个
///   视图就杀掉活着的订阅者的数据源"因此在结构上不可能再发生。
fn plan_status_streams(
    registered: &BTreeSet<PathBuf>,
    running: &BTreeSet<PathBuf>,
    watched: &BTreeSet<PathBuf>,
) -> StatusStreamPlan {
    StatusStreamPlan {
        start: watched
            .iter()
            .filter(|config| !running.contains(*config))
            .cloned()
            .collect(),
        stop: registered
            .union(running)
            .filter(|config| !watched.contains(*config))
            .cloned()
            .collect(),
    }
}

/// 决议 2026-08-03 D-C4：只有该 config 一帧都没有时才做 `status --json` 播种。
/// 子进程重生时缓存里已有帧，重复播种只会多一次跨 WSL 的秒级读取。
fn needs_bootstrap_seed(
    snapshots: &BTreeMap<PathBuf, AhRuntimeSnapshot>,
    config_path: &Path,
) -> bool {
    !snapshots.contains_key(config_path)
}

fn drop_status_stream(state: &CodeAssistantRuntimeState, config: &Path) {
    if let Some(stream) = state
        .status_streams
        .lock()
        .expect("code assistant status streams poisoned")
        .remove(config)
    {
        stop_code_assistant_status_stream(stream);
        log::info!(
            "phase=code-assistant-status action=stream-stop config={}",
            config.display()
        );
    }
    state
        .status_specs
        .lock()
        .expect("code assistant status specs poisoned")
        .remove(config);
    state
        .status_snapshots
        .lock()
        .expect("code assistant status snapshots poisoned")
        .remove(config);
}

fn ensure_code_assistant_status_streams_for_workspace(
    app: &tauri::AppHandle,
    state: &CodeAssistantRuntimeState,
    workspace_root: &Path,
) -> Result<(), String> {
    let next_specs = next_status_specs_for_workspace(state, workspace_root);
    let watched = next_specs.keys().cloned().collect::<BTreeSet<_>>();
    let registered = state
        .status_specs
        .lock()
        .expect("code assistant status specs poisoned")
        .keys()
        .cloned()
        .collect::<BTreeSet<_>>();
    let running = state
        .status_streams
        .lock()
        .expect("code assistant status streams poisoned")
        .keys()
        .cloned()
        .collect::<BTreeSet<_>>();

    let plan = plan_status_streams(&registered, &running, &watched);
    for config in plan.stop {
        drop_status_stream(state, &config);
    }

    {
        let mut specs = state
            .status_specs
            .lock()
            .expect("code assistant status specs poisoned");
        for (config, spec) in next_specs {
            specs.insert(config, spec);
        }
    }

    for config in plan.start {
        let stream = start_code_assistant_status_stream(
            app.clone(),
            config.clone(),
            workspace_root.to_path_buf(),
        )?;
        let mut streams = state
            .status_streams
            .lock()
            .expect("code assistant status streams poisoned");
        if let std::collections::btree_map::Entry::Vacant(entry) = streams.entry(config.clone()) {
            entry.insert(stream);
            log::info!(
                "phase=code-assistant-status action=stream-start config={}",
                config.display()
            );
        } else {
            stop_code_assistant_status_stream(stream);
        }
    }
    Ok(())
}

fn register_opened_code_assistant_status_spec(
    state: &CodeAssistantRuntimeState,
    workspace_root: &Path,
    assistant: CodeAssistant,
    config_path: &Path,
) {
    state
        .status_specs
        .lock()
        .expect("code assistant status specs poisoned")
        .insert(
            config_path.to_path_buf(),
            CodeAssistantStatusSpec {
                workspace_root: workspace_root.to_path_buf(),
                assistant,
            },
        );
}

fn stop_all_code_assistant_status_streams(state: &CodeAssistantRuntimeState) {
    let streams = std::mem::take(
        &mut *state
            .status_streams
            .lock()
            .expect("code assistant status streams poisoned"),
    );
    for (_, stream) in streams {
        stop_code_assistant_status_stream(stream);
    }
}

fn discover_studio_ah_configs() -> Vec<PathBuf> {
    fn visit(dir: &Path, configs: &mut Vec<PathBuf>) {
        let Ok(entries) = std::fs::read_dir(dir) else {
            return;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() {
                visit(&path, configs);
            } else if path.file_name().and_then(|name| name.to_str()) == Some("ah.toml") {
                configs.push(path);
            }
        }
    }

    let mut configs = Vec::new();
    visit(&studio_ah_temp_root(), &mut configs);
    configs
}

fn cleanup_registered_code_assistants(configs: BTreeSet<PathBuf>) {
    for config in configs {
        // App-quit sweep: only Studio-managed configs reach here (registered
        // state + Studio temp namespace discovery), and there is no workspace to
        // disambiguate, so the snapshot is read config-scoped (Some/None handled
        // in `resolve_cleanup_snapshot`).
        match cleanup_code_assistant_config(&config, None) {
            Ok(true) => log::info!(
                "phase=code-assistant-cleanup action=close-ok config={}",
                config.display()
            ),
            Ok(false) => log::info!(
                "phase=code-assistant-cleanup action=close-skip config={} reason=not_running",
                config.display()
            ),
            Err(error) => log::warn!(
                "phase=code-assistant-cleanup action=close-failed config={} error={error}",
                config.display()
            ),
        }
    }
}


fn sh_single_quote_str(value: &str) -> String {
    format!("'{}'", value.replace('\'', "'\\''"))
}

/// Double-quoted shell literal, for values that must stay readable inside an
/// exported env line. Escapes the four characters the shell still expands
/// inside double quotes.
fn sh_double_quote_str(value: &str) -> String {
    let escaped = value
        .replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('$', "\\$")
        .replace('`', "\\`");
    format!("\"{escaped}\"")
}

fn sh_single_quote(value: &Path) -> String {
    sh_single_quote_str(&value.display().to_string())
}

/// Translate a Windows path (`C:\Users\x\skill`) into the WSL mount path
/// (`/mnt/c/Users/x/skill`) that ah + claude see from inside the distro.
fn windows_path_to_wsl(path: &Path) -> String {
    let mut slashed = path.display().to_string().replace('\\', "/");
    if let Some(stripped) = slashed.strip_prefix("//?/") {
        slashed = stripped.to_string();
    }
    let bytes = slashed.as_bytes();
    if slashed.len() >= 2 && bytes[1] == b':' && bytes[0].is_ascii_alphabetic() {
        let drive = (bytes[0] as char).to_ascii_lowercase();
        return format!("/mnt/{}{}", drive, &slashed[2..]);
    }
    slashed
}

/// Python payload embedded in both launcher scripts that pre-approves the
/// onboarding gates for the workspace ah is about to open the interactive
/// master in: theme picker, per-workspace folder-trust, and external-CLAUDE.md
/// -imports.
///
/// The imports approval is gated per the DIRECTORY OF THE IMPORTING CLAUDE.md,
/// not the workspace cwd — verified empirically: seeding only the workspace's
/// own `projects` entry still left the "Allow external CLAUDE.md file
/// imports?" dialog blocking, because this repo's root CLAUDE.md `@`-imports
/// AGENTS.md (outside a skill subdirectory's cwd) and the approval is recorded
/// against that CLAUDE.md's own directory. So this walks every ancestor
/// directory up to the filesystem root and seeds any that has its own
/// CLAUDE.md, in addition to the workspace itself.
const CLAUDE_ONBOARDING_PRESEED_PY: &str = r#"import json, os, sys
p = os.path.expanduser('~/.claude.json')
try:
    d = json.load(open(p))
except Exception:
    d = {}
d.setdefault('theme', 'dark')
proj = d.setdefault('projects', {})

def seed(path):
    e = proj.setdefault(path, {})
    e['hasTrustDialogAccepted'] = True
    e['hasClaudeMdExternalIncludesApproved'] = True
    e['hasClaudeMdExternalIncludesWarningShown'] = True
    e.setdefault('hasCompletedProjectOnboarding', True)
    e.setdefault('projectOnboardingSeenCount', 3)

ws = sys.argv[1]
seed(ws)
cur = ws
while True:
    parent = os.path.dirname(cur)
    if parent == cur:
        break
    if os.path.isfile(os.path.join(parent, 'CLAUDE.md')):
        seed(parent)
    cur = parent

json.dump(d, open(p, 'w'), indent=2)
"#;

/// Open 之前在宿主 HOME 刷新 Claude CLI 的片段（决议 2026-08-02 D-B1..D-B5）。
///
/// Claude CLI 的自更新是"运行中的进程更新它自己 `$HOME` 底下那份安装"。ah 给每个会话指定
/// 独立的临时 `HOME` 并在会话结束时删除，所以沙箱里跑出来的更新永远回不到宿主那份安装——
/// 宿主 HOME、进入 ah 沙箱之前，是这套官方机制唯一能生效的位置。
///
/// Studio 只负责给官方机制这个位置和时机：调用官方安装器入口，自己不比对版本号、不下载、
/// 不安装。24 小时节流是因为 native build 是约 250 MB 的单文件，尚无法确证"已是最新时安装器
/// 立即返回"；失败一律放行，因为能否打开 CLI 不该由一次网络抖动决定。
const CLAUDE_CLI_REFRESH_SH: &str = r#"STUDIO_CLAUDE_UPDATE_STAMP="$HOME/.cache/studio-claude-cli-update-check"
if [ ! -f "$STUDIO_CLAUDE_UPDATE_STAMP" ] || [ -n "$(find "$STUDIO_CLAUDE_UPDATE_STAMP" -mmin +1440 2>/dev/null)" ]; then
  printf '%s\n' "Checking for a newer Claude Code CLI (official installer)..."
  if timeout 300 claude install latest </dev/null; then
    mkdir -p "$(dirname "$STUDIO_CLAUDE_UPDATE_STAMP")" && : > "$STUDIO_CLAUDE_UPDATE_STAMP"
  else
    printf '%s\n' "Claude Code CLI refresh skipped (offline, or the installer failed); continuing with the installed version."
  fi
fi
"#;

/// The bash payload ah + claude run inside WSL. It pre-accepts the onboarding
/// gates (see `CLAUDE_ONBOARDING_PRESEED_PY`) so the interactive master reaches
/// its prompt instead of blocking, then `ah start`s and attaches the master —
/// all in ONE wsl session so the interactive attach holds the distro alive and
/// the master persists.
/// Where a CLI session reaches the running Studio sidecar's MCP surface.
///
/// WSL mirrored networking (the default on this project's Windows hosts) makes
/// the Windows sidecar reachable at 127.0.0.1 from inside the distro, so the
/// sidecar keeps its loopback-only bind. A distro without mirrored networking
/// simply cannot resolve it — the launcher then omits the env and the session
/// runs without Studio tools rather than failing to start.
pub(crate) struct StudioMcpEndpoint {
    pub port: u16,
    pub token: String,
}

/// Bash snippet appended to launcher scripts that own a Studio transient
/// ah.toml: ah >= 1.7.0 requires `providers.claude.shared_credentials_dir`
/// (it becomes CLAUDE_SECURESTORAGE_CONFIG_DIR inside every sandbox), and the
/// value is the launching user's `$HOME/.claude` — resolvable only in the
/// launcher's own shell, never at config-write time on the Windows side.
fn claude_provider_config_patch(config_ref: &str) -> String {
    format!(
        r#"if ! grep -q '^\[providers\.claude\]' {config_ref} 2>/dev/null; then
  mkdir -p "$HOME/.claude"
  printf '\n[providers.claude]\nshared_credentials_dir = "%s"\n' "$HOME/.claude" >> {config_ref}
fi
"#
    )
}

fn wsl_payload_script(
    wsl_workspace: &str,
    wsl_config: &str,
    assistant: CodeAssistant,
    windows_codex_home: Option<&str>,
    windows_claude_home: Option<&str>,
    studio_mcp: Option<&StudioMcpEndpoint>,
    patch_transient_claude_config: bool,
) -> String {
    let min_parts: Vec<&str> = AH_VERSION_MIN.split('.').collect();
    let min_major = min_parts.get(0).copied().unwrap_or("1");
    let min_minor = min_parts.get(1).copied().unwrap_or("4");
    let min_patch = min_parts.get(2).copied().unwrap_or("0");

    let codex_auth_sync = if matches!(assistant, CodeAssistant::Codex) {
        let windows_home = windows_codex_home
            .map(sh_single_quote_str)
            .unwrap_or_else(|| "''".to_string());
        format!(
            r#"WIN_CODEX_HOME={windows_home}
if [ -z "$WIN_CODEX_HOME" ] || [ ! -f "$WIN_CODEX_HOME/auth.json" ]; then
  printf '%s\n' "Windows Codex auth was not found."
  printf '%s\n' "Run Codex login on Windows first, then reopen Studio's Codex menu item."
  exec bash -i
fi
mkdir -p "$HOME/.codex"
cp "$WIN_CODEX_HOME/auth.json" "$HOME/.codex/auth.json"
chmod 600 "$HOME/.codex/auth.json"
"#,
            windows_home = windows_home
        )
    } else {
        String::new()
    };
    // Claude auth bridge: the Windows `.credentials.json` is the single auth
    // file. WSL root and the ah sandbox link to it instead of copying it, so
    // the user only signs in to Claude Code on Windows.
    let claude_auth_bridge = if matches!(assistant, CodeAssistant::Claude) {
        let windows_home = windows_claude_home
            .map(sh_single_quote_str)
            .unwrap_or_else(|| "''".to_string());
        format!(
            r#"WIN_CLAUDE_HOME={windows_home}
CLAUDE_CRED="$HOME/.claude/.credentials.json"
if [ -z "$WIN_CLAUDE_HOME" ] || [ ! -f "$WIN_CLAUDE_HOME/.credentials.json" ]; then
  printf '%s\n' "Windows Claude login was not found."
  printf '%s\n' "Sign in to Claude Code on Windows, then reopen Studio's Open in CLI > Claude code item."
  exec bash -i
fi
mkdir -p "$HOME/.claude"
ln -sfn "$WIN_CLAUDE_HOME/.credentials.json" "$CLAUDE_CRED"
claude_auth_ok=0
if [ -f "$CLAUDE_CRED" ] && command -v python3 >/dev/null 2>&1; then
  if python3 - "$CLAUDE_CRED" <<'CREDPY'
import json
import sys
try:
    oauth = json.load(open(sys.argv[1])).get("claudeAiOauth") or {{}}
except Exception:
    sys.exit(1)
sys.exit(0 if (oauth.get("accessToken") or oauth.get("refreshToken")) else 1)
CREDPY
  then
    claude_auth_ok=1
  fi
fi
if [ "$claude_auth_ok" -ne 1 ]; then
  printf '%s\n' "Windows Claude credentials are present but not logged in."
  printf '%s\n' "Sign in to Claude Code on Windows, then reopen Studio's Open in CLI > Claude code item."
  exec bash -i
fi
"#,
            windows_home = windows_home
        )
    } else {
        String::new()
    };
    let studio_mcp_env = match studio_mcp {
        Some(endpoint) => format!(
            "export STUDIO_MCP_URL=\"http://127.0.0.1:{port}/mcp\"\nexport STUDIO_API_TOKEN={token}\n",
            port = endpoint.port,
            token = sh_double_quote_str(&endpoint.token),
        ),
        None => String::new(),
    };
    let claude_config_patch =
        if patch_transient_claude_config && matches!(assistant, CodeAssistant::Claude) {
            claude_provider_config_patch("\"$CFG\"")
        } else {
            String::new()
        };
    let claude_cli_refresh = if matches!(assistant, CodeAssistant::Claude) {
        CLAUDE_CLI_REFRESH_SH
    } else {
        ""
    };
    format!(
        r#"#!/usr/bin/env bash
export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
WS={workspace}
CFG={config}
export SYSTEMD_LOG_LEVEL=err
export STUDIO_AH_HOST_HOME="$HOME"
{studio_mcp_env}{codex_auth_sync}{claude_auth_bridge}
if ! command -v ah >/dev/null 2>&1; then
  printf '%s\n' "ah CLI was not found in WSL."
  printf '%s\n' "Install it from https://github.com/SevenX77/ah then reopen Studio."
  exec bash -i
fi
ah_version="$(ah version 2>/dev/null)"
# requires ah >= 1.3.4
ah_major="${{ah_version%%.*}}"
ah_rest="${{ah_version#*.}}"
ah_minor="${{ah_rest%%.*}}"
ah_patch="${{ah_rest#*.}}"
[ "$ah_patch" = "$ah_rest" ] && ah_patch=0
ah_ok=0
if [ "$ah_major" -gt {min_major} ] 2>/dev/null; then
  ah_ok=1
elif [ "$ah_major" -eq {min_major} ] 2>/dev/null && [ "$ah_minor" -gt {min_minor} ] 2>/dev/null; then
  ah_ok=1
elif [ "$ah_major" -eq {min_major} ] 2>/dev/null && [ "$min_minor" -eq "$min_minor" ] 2>/dev/null && [ "$ah_minor" -eq {min_minor} ] 2>/dev/null && [ "$ah_patch" -ge {min_patch} ] 2>/dev/null; then
  ah_ok=1
fi
if [ "$ah_ok" -ne 1 ]; then
  printf 'ah %s is installed; Studio requires ah >= {min_version} for runtime inventory, starting status, and native worker sandbox env.\n' "${{ah_version:-unknown}}"
  printf '%s\n' "Run scripts/install-claude-code-wsl.ps1, then reopen Studio."
  exec bash -i
fi
{claude_cli_refresh}{claude_config_patch}if command -v python3 >/dev/null 2>&1; then
python3 - "$WS" <<'PY'
{preseed}
PY
fi
cd "$WS" 2>/dev/null || cd "$HOME"
printf '%s\n' "Starting {assistant_name} through ah (first launch ~15s cold start)..."
ah --config "$CFG" start --wait
status=$?
if [ "$status" -ne 0 ]; then
  printf 'ah start failed with exit code %s\n' "$status"
  exec bash -i
fi
{tmux_mouse}printf '%s\n' "Attaching - {assistant_name} will auto-report its status (detach: Ctrl-b then d)."
ah --config "$CFG" attach master
printf '[attach ended; exit=%s]\n' "$?"
exec bash -i
"#,
        workspace = sh_single_quote_str(wsl_workspace),
        tmux_mouse = tmux_mouse_enable_snippet("\"$WS\""),
        config = sh_single_quote_str(wsl_config),
        assistant_name = assistant.display_name(),
        codex_auth_sync = codex_auth_sync,
        claude_auth_bridge = claude_auth_bridge,
        claude_cli_refresh = claude_cli_refresh,
        claude_config_patch = claude_config_patch,
        preseed = CLAUDE_ONBOARDING_PRESEED_PY,
        min_version = AH_VERSION_MIN,
        min_major = min_major,
        min_minor = min_minor,
        min_patch = min_patch,
    )
}

/// tmux ships with `mouse off` and ah sets no tmux options of its own (the ah
/// repository has no `mouse` setting anywhere), so inside an attached pane the
/// wheel scrolls nothing. The embedded terminal is a mouse-first surface, so
/// the launcher turns the option on for the tmux server that owns THIS
/// workspace's session, right before attaching.
///
/// The server is located by matching a session's working directory against the
/// workspace — deliberately NOT by recomputing ah's socket-name hash
/// (`ahd-<sha256(state_dir)[..16]>`), which would weld Studio to an ah
/// internal. Every failure path is silent: with the option unset, scrolling
/// still works through tmux's keyboard route (prefix `Ctrl-b`, then `[`).
fn tmux_mouse_enable_snippet(workspace_expr: &str) -> String {
    format!(
        r#"studio_enable_tmux_mouse() {{
  command -v tmux >/dev/null 2>&1 || return 0
  studio_uid="$(id -u 2>/dev/null)" || return 0
  for studio_sock in "/tmp/tmux-$studio_uid"/ahd-*; do
    [ -S "$studio_sock" ] || continue
    tmux -S "$studio_sock" list-sessions -F '#{{session_path}}' 2>/dev/null \
      | grep -Fxq {workspace_expr} || continue
    tmux -S "$studio_sock" set-option -g mouse on >/dev/null 2>&1 || true
    return 0
  done
  return 0
}}
studio_enable_tmux_mouse
"#
    )
}


fn wsl_attach_payload_script(
    wsl_config: &str,
    wsl_workspace: &str,
    assistant: CodeAssistant,
) -> String {
    let min_parts: Vec<&str> = AH_VERSION_MIN.split('.').collect();
    let min_major = min_parts.get(0).copied().unwrap_or("1");
    let min_minor = min_parts.get(1).copied().unwrap_or("4");
    let min_patch = min_parts.get(2).copied().unwrap_or("0");

    format!(
        r#"#!/usr/bin/env bash
export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
CFG={config}
export SYSTEMD_LOG_LEVEL=err
if ! command -v ah >/dev/null 2>&1; then
  printf '%s\n' "ah CLI was not found in WSL."
  printf '%s\n' "Install it from https://github.com/SevenX77/ah then reopen Studio."
  exec bash -i
fi
ah_version="$(ah version 2>/dev/null)"
# requires ah >= 1.3.4
ah_major="${{ah_version%%.*}}"
ah_rest="${{ah_version#*.}}"
ah_minor="${{ah_rest%%.*}}"
ah_patch="${{ah_rest#*.}}"
[ "$ah_patch" = "$ah_rest" ] && ah_patch=0
ah_ok=0
if [ "$ah_major" -gt {min_major} ] 2>/dev/null; then
  ah_ok=1
elif [ "$ah_major" -eq {min_major} ] 2>/dev/null && [ "$ah_minor" -gt {min_minor} ] 2>/dev/null; then
  ah_ok=1
elif [ "$----" = "$----" ] 2>/dev/null && [ "$ah_major" -eq {min_major} ] 2>/dev/null && [ "$ah_minor" -eq {min_minor} ] 2>/dev/null && [ "$ah_patch" -ge {min_patch} ] 2>/dev/null; then
  ah_ok=1
fi
if [ "$ah_ok" -ne 1 ]; then
  printf 'ah %s is installed; Studio requires ah >= {min_version} for runtime inventory, starting status, and native worker sandbox env.\n' "${{ah_version:-unknown}}"
  printf '%s\n' "Run scripts/install-claude-code-wsl.ps1, then reopen Studio."
  exec bash -i
fi
{tmux_mouse}printf '%s\n' "Attaching {assistant_name} master pane (detach: Ctrl-b then d)."
ah --config "$CFG" attach master
printf '[attach ended; exit=%s]\n' "$?"
exec bash -i
"#,
        config = sh_single_quote_str(wsl_config),
        tmux_mouse = tmux_mouse_enable_snippet(&sh_single_quote_str(wsl_workspace)),
        assistant_name = assistant.display_name(),
        min_version = AH_VERSION_MIN,
        min_major = min_major,
        min_minor = min_minor,
        min_patch = min_patch,
    )
}


/// On native Linux ah runs directly. macOS is not yet supported by ah.
fn unix_code_assistant_launcher_script(
    workspace_root: &Path,
    config_path: &Path,
    assistant: CodeAssistant,
    patch_transient_claude_config: bool,
) -> String {
    let min_parts: Vec<&str> = AH_VERSION_MIN.split('.').collect();
    let min_major = min_parts.get(0).copied().unwrap_or("1");
    let min_minor = min_parts.get(1).copied().unwrap_or("4");
    let min_patch = min_parts.get(2).copied().unwrap_or("0");
    let claude_config_patch =
        if patch_transient_claude_config && matches!(assistant, CodeAssistant::Claude) {
            claude_provider_config_patch(&sh_single_quote(config_path))
        } else {
            String::new()
        };

    format!(
        r#"#!/bin/sh
set -u
export SYSTEMD_LOG_LEVEL=err
export STUDIO_AH_HOST_HOME="$HOME"
if ! command -v ah >/dev/null 2>&1; then
  printf '%s\n' "ah CLI was not found on PATH."
  printf '%s\n' "Install it from https://github.com/SevenX77/ah then reopen Studio."
  exec "${{SHELL:-/bin/sh}}"
fi
ah_version="$(ah version 2>/dev/null)"
# requires ah >= 1.3.4
ah_major="${{ah_version%%.*}}"
ah_rest="${{ah_version#*.}}"
ah_minor="${{ah_rest%%.*}}"
ah_patch="${{ah_rest#*.}}"
[ "$ah_patch" = "$ah_rest" ] && ah_patch=0
ah_ok=0
if [ "$ah_major" -gt {min_major} ] 2>/dev/null; then
  ah_ok=1
elif [ "$ah_major" -eq {min_major} ] 2>/dev/null && [ "$ah_minor" -gt {min_minor} ] 2>/dev/null; then
  ah_ok=1
elif [ "$ah_major" -eq {min_major} ] 2>/dev/null && [ "$ah_minor" -eq {min_minor} ] 2>/dev/null && [ "$ah_patch" -ge {min_patch} ] 2>/dev/null; then
  ah_ok=1
fi
if [ "$ah_ok" -ne 1 ]; then
  printf 'ah %s is installed; Studio requires ah >= {min_version} for runtime inventory, starting status, and native worker sandbox env.\n' "${{ah_version:-unknown}}"
  printf '%s\n' "Install ah from https://github.com/SevenX77/ah, then reopen Studio."
  exec "${{SHELL:-/bin/sh}}"
fi
{claude_config_patch}if command -v python3 >/dev/null 2>&1; then
python3 - {workspace} <<'PY'
{preseed}
PY
fi
cd {workspace}
printf '%s\n' "Starting {assistant_name} through ah (first launch ~15s cold start)..."
ah --config {config} start --wait
status=$?
if [ "$status" -ne 0 ]; then
  printf 'ah start failed with exit code %s\n' "$status"
  exec "${{SHELL:-/bin/sh}}"
fi
{tmux_mouse}ah --config {config} attach master
printf '[attach ended]\n'
exec "${{SHELL:-/bin/sh}}"
"#,
        workspace = sh_single_quote(workspace_root),
        tmux_mouse = tmux_mouse_enable_snippet(&sh_single_quote(workspace_root)),
        config = sh_single_quote(config_path),
        assistant_name = assistant.display_name(),
        claude_config_patch = claude_config_patch,
        preseed = CLAUDE_ONBOARDING_PRESEED_PY,
        min_version = AH_VERSION_MIN,
        min_major = min_major,
        min_minor = min_minor,
        min_patch = min_patch,
    )
}

fn unix_code_assistant_attach_launcher_script(
    workspace_root: &Path,
    config_path: &Path,
    assistant: CodeAssistant,
) -> String {
    let min_parts: Vec<&str> = AH_VERSION_MIN.split('.').collect();
    let min_major = min_parts.get(0).copied().unwrap_or("1");
    let min_minor = min_parts.get(1).copied().unwrap_or("4");
    let min_patch = min_parts.get(2).copied().unwrap_or("0");

    format!(
        r#"#!/bin/sh
set -u
export SYSTEMD_LOG_LEVEL=err
export STUDIO_AH_HOST_HOME="$HOME"
if ! command -v ah >/dev/null 2>&1; then
  printf '%s\n' "ah CLI was not found on PATH."
  printf '%s\n' "Install it from https://github.com/SevenX77/ah then reopen Studio."
  exec "${{SHELL:-/bin/sh}}"
fi
ah_version="$(ah version 2>/dev/null)"
# requires ah >= 1.3.4
ah_major="${{ah_version%%.*}}"
ah_rest="${{ah_version#*.}}"
ah_minor="${{ah_rest%%.*}}"
ah_patch="${{ah_rest#*.}}"
[ "$ah_patch" = "$ah_rest" ] && ah_patch=0
ah_ok=0
if [ "$ah_major" -gt {min_major} ] 2>/dev/null; then
  ah_ok=1
elif [ "$ah_major" -eq {min_major} ] 2>/dev/null && [ "$ah_minor" -gt {min_minor} ] 2>/dev/null; then
  ah_ok=1
elif [ "$ah_major" -eq {min_major} ] 2>/dev/null && [ "$ah_minor" -eq {min_minor} ] 2>/dev/null && [ "$ah_patch" -ge {min_patch} ] 2>/dev/null; then
  ah_ok=1
fi
if [ "$ah_ok" -ne 1 ]; then
  printf 'ah %s is installed; Studio requires ah >= {min_version} for runtime inventory, starting status, and native worker sandbox env.\n' "${{ah_version:-unknown}}"
  printf '%s\n' "Install ah from https://github.com/SevenX77/ah, then reopen Studio."
  exec "${{SHELL:-/bin/sh}}"
fi
{tmux_mouse}printf '%s\n' "Attaching {assistant_name} master pane (detach: Ctrl-b then d)."
ah --config {config} attach master
printf '[attach ended]\n'
exec "${{SHELL:-/bin/sh}}"
"#,
        config = sh_single_quote(config_path),
        tmux_mouse = tmux_mouse_enable_snippet(&sh_single_quote(workspace_root)),
        assistant_name = assistant.display_name(),
        min_version = AH_VERSION_MIN,
        min_major = min_major,
        min_minor = min_minor,
        min_patch = min_patch,
    )
}

/// Every launcher is a shell script now: on Windows it is the bash payload WSL
/// runs, elsewhere it is the script the PTY runs directly.
fn launcher_script_path_with_stem(workspace_root: &Path, assistant: CodeAssistant, stem: &str) -> PathBuf {
    std::env::temp_dir()
        .join("skill-studio-ah")
        .join(workspace_hash(workspace_root))
        .join(assistant.slug())
        .join(format!("{stem}.sh"))
}

fn launcher_script_path(workspace_root: &Path, assistant: CodeAssistant) -> PathBuf {
    launcher_script_path_with_stem(workspace_root, assistant, assistant.launcher_stem())
}

fn attach_launcher_script_path(workspace_root: &Path, assistant: CodeAssistant) -> PathBuf {
    launcher_script_path_with_stem(workspace_root, assistant, assistant.attach_launcher_stem())
}

/// Owns one embedded terminal. A workspace + assistant pair has exactly one
/// live CLI session, so this is the dedupe key: reopening replaces the previous
/// client instead of stacking a second one.
fn cli_terminal_owner_key(workspace_root: &Path, assistant: CodeAssistant) -> String {
    format!(
        "{}-{}",
        assistant.slug(),
        workspace_hash(workspace_root)
    )
}

fn windows_codex_home_wsl() -> Option<String> {
    let user_profile = std::env::var_os("USERPROFILE")?;
    Some(windows_path_to_wsl(
        &PathBuf::from(user_profile).join(".codex"),
    ))
}

fn windows_claude_home_wsl() -> Option<String> {
    let user_profile = std::env::var_os("USERPROFILE")?;
    Some(windows_path_to_wsl(
        &PathBuf::from(user_profile).join(".claude"),
    ))
}

/// Windows runs the bash payload through `wsl.exe`; every other platform runs
/// the launcher script directly. Either way the embedded PTY (see
/// `cli_terminal`) is the only console involved.
fn launcher_command_for_script(script_path: &Path) -> cli_terminal::LauncherCommand {
    if cfg!(target_os = "windows") {
        cli_terminal::LauncherCommand {
            program: "wsl.exe".to_string(),
            args: vec![
                "-e".to_string(),
                "bash".to_string(),
                windows_path_to_wsl(script_path),
            ],
        }
    } else {
        cli_terminal::LauncherCommand {
            program: script_path.display().to_string(),
            args: Vec::new(),
        }
    }
}

fn write_launcher_file(
    script_path: &Path,
    content: String,
    assistant: CodeAssistant,
) -> Result<(), String> {
    let parent = script_path
        .parent()
        .ok_or_else(|| format!("cannot resolve launcher parent: {}", script_path.display()))?;
    std::fs::create_dir_all(parent)
        .map_err(|error| format!("failed to create launcher script dir: {error}"))?;
    std::fs::write(script_path, content).map_err(|error| {
        format!(
            "failed to write {} launcher: {error}",
            assistant.display_name()
        )
    })?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut permissions = std::fs::metadata(script_path)
            .map_err(|error| {
                format!(
                    "failed to stat {} launcher: {error}",
                    assistant.display_name()
                )
            })?
            .permissions();
        permissions.set_mode(0o700);
        std::fs::set_permissions(script_path, permissions).map_err(|error| {
            format!(
                "failed to chmod {} launcher: {error}",
                assistant.display_name()
            )
        })?;
    }
    Ok(())
}

fn write_code_assistant_launcher_script(
    workspace_root: &Path,
    config_path: &Path,
    assistant: CodeAssistant,
    studio_mcp: Option<&StudioMcpEndpoint>,
) -> Result<cli_terminal::LauncherCommand, String> {
    let script_path = launcher_script_path(workspace_root, assistant);
    // Only Studio's own transient config may be patched at launch time; a
    // user-owned ah.toml keeps ah's diagnostics untouched.
    let patch_transient_claude_config = config_path.starts_with(studio_ah_temp_root());
    let content = if cfg!(target_os = "windows") {
        // ah + claude live inside WSL2 on Windows, so the launcher IS the bash
        // payload; paths are translated to the /mnt/... form the distro sees.
        wsl_payload_script(
            &windows_path_to_wsl(workspace_root),
            &windows_path_to_wsl(config_path),
            assistant,
            windows_codex_home_wsl().as_deref(),
            windows_claude_home_wsl().as_deref(),
            studio_mcp,
            patch_transient_claude_config,
        )
    } else {
        unix_code_assistant_launcher_script(
            workspace_root,
            config_path,
            assistant,
            patch_transient_claude_config,
        )
    };
    write_launcher_file(&script_path, content, assistant)?;
    Ok(launcher_command_for_script(&script_path))
}

fn write_code_assistant_attach_launcher_script(
    workspace_root: &Path,
    config_path: &Path,
    assistant: CodeAssistant,
) -> Result<cli_terminal::LauncherCommand, String> {
    let script_path = attach_launcher_script_path(workspace_root, assistant);
    let content = if cfg!(target_os = "windows") {
        wsl_attach_payload_script(
            &windows_path_to_wsl(config_path),
            &windows_path_to_wsl(workspace_root),
            assistant,
        )
    } else {
        unix_code_assistant_attach_launcher_script(workspace_root, config_path, assistant)
    };
    write_launcher_file(&script_path, content, assistant)?;
    Ok(launcher_command_for_script(&script_path))
}

enum CodeAssistantOpenAction {
    StartFresh,
    AttachExisting(PathBuf),
}

fn prepare_code_assistant_open(
    state: &CodeAssistantRuntimeState,
    workspace_root: &Path,
    requested: CodeAssistant,
) -> Result<CodeAssistantOpenAction, String> {
    check_ah_version_cached()?;

    let cached_snapshot = |config: &Path| -> Option<AhRuntimeSnapshot> {
        state
            .status_snapshots
            .lock()
            .expect("code assistant status snapshots poisoned")
            .get(config)
            .cloned()
    };

    let requested_runtime = ah_config_for_status(workspace_root, requested).and_then(|config| {
        resolve_open_snapshot(cached_snapshot(&config).as_ref(), &config, workspace_root)
            .map(|snapshot| (config, snapshot))
    });
    let requested_config = requested_runtime
        .as_ref()
        .map(|(config, _)| config.to_path_buf());
    let other_runtimes = CodeAssistant::ALL
        .iter()
        .copied()
        .filter(|assistant| assistant.slug() != requested.slug())
        .filter_map(|assistant| {
            ah_config_for_status(workspace_root, assistant).and_then(|config| {
                resolve_open_snapshot(cached_snapshot(&config).as_ref(), &config, workspace_root)
                    .map(|snapshot| (assistant, config, snapshot))
            })
        })
        .filter(|(_, config, _)| requested_config.as_ref() != Some(config))
        .collect::<Vec<_>>();
    let other_snapshots = other_runtimes
        .iter()
        .map(|(_, _, snapshot)| snapshot.clone())
        .collect::<Vec<_>>();

    match decide_code_assistant_open_v2(
        requested_runtime.as_ref().map(|(_, snapshot)| snapshot),
        &other_snapshots,
    ) {
        CodeAssistantOpenDecision::AttachRequested => {
            let (config, _) = requested_runtime.expect("requested runtime must exist");
            Ok(CodeAssistantOpenAction::AttachExisting(config))
        }
        CodeAssistantOpenDecision::RejectOtherActive => {
            let assistant = other_runtimes
                .iter()
                .find_map(|(assistant, _, snapshot)| {
                    (snapshot.runtime_state == AhRuntimeState::Active).then_some(*assistant)
                })
                .expect("active other assistant must exist");
            Err(format!(
                "{} is already running; close it before opening {}.",
                assistant.display_name(),
                requested.display_name()
            ))
        }
        CodeAssistantOpenDecision::CleanupStale => {
            cleanup_workspace_code_assistants(workspace_root)?;
            Ok(CodeAssistantOpenAction::StartFresh)
        }
        CodeAssistantOpenDecision::StartFresh => Ok(CodeAssistantOpenAction::StartFresh),
        // Startup in progress: take no lifecycle action, mirror attach's hands-off wait (Req 3.6).
        CodeAssistantOpenDecision::HandsOff => Err(format!(
            "{} is still starting; wait for startup to finish before opening it again.",
            requested.display_name()
        )),
    }
}

/// Read the live sidecar's MCP endpoint, if the sidecar is up. A CLI session
/// opened before the sidecar is ready simply gets no Studio tools — the
/// session must still launch (N5 design: never hard-fail the terminal on a
/// tool-surface problem).
fn studio_mcp_endpoint(app: &tauri::AppHandle) -> Option<StudioMcpEndpoint> {
    let state = app.try_state::<SidecarAppState>()?;
    let manager = state.manager.lock().ok()?;
    let runtime = manager.as_ref()?.runtime_config();
    Some(StudioMcpEndpoint {
        port: runtime.port,
        token: runtime.api_token,
    })
}

/// Grid the CLI session starts at when the caller has not measured one yet.
const CLI_TERMINAL_FALLBACK_COLS: u16 = 100;
const CLI_TERMINAL_FALLBACK_ROWS: u16 = 30;

struct OpenedCodeAssistant {
    config_path: PathBuf,
    session_id: String,
}

fn open_code_assistant(
    on_event: tauri::ipc::Channel<cli_terminal::CliTerminalEvent>,
    state: &CodeAssistantRuntimeState,
    terminals: &cli_terminal::CliTerminalState,
    workspace_root: &Path,
    assistant: CodeAssistant,
    studio_mcp: Option<&StudioMcpEndpoint>,
    cols: u16,
    rows: u16,
) -> Result<OpenedCodeAssistant, String> {
    check_ah_version_cached()?;
    // Read the id off the registry rather than trusting the opener: the session
    // must be told which skill it is bound to, and it must be the registered one.
    let skill = native_fs::registered_skill_id_for_root(&resolve_config_dir(), workspace_root).map(
        |skill_id| SessionSkillContext {
            skill_id,
            workspace_root: workspace_root.display().to_string(),
        },
    );
    let (config_path, launcher) = match prepare_code_assistant_open(state, workspace_root, assistant)?
    {
        CodeAssistantOpenAction::AttachExisting(config_path) => {
            let launcher = write_code_assistant_attach_launcher_script(
                workspace_root,
                &config_path,
                assistant,
            )?;
            (config_path, launcher)
        }
        CodeAssistantOpenAction::StartFresh => {
            let config_path =
                ah_config_for_workspace(workspace_root, assistant, studio_mcp, skill.as_ref())?;
            ensure_lifecycle_command_allowed(&config_path)?;
            let launcher = write_code_assistant_launcher_script(
                workspace_root,
                &config_path,
                assistant,
                studio_mcp,
            )?;
            (config_path, launcher)
        }
    };
    let session_id = cli_terminal::spawn(
        on_event,
        terminals,
        &cli_terminal_owner_key(workspace_root, assistant),
        &launcher,
        workspace_root,
        cli_terminal::initial_size(cols, rows),
    )?;
    Ok(OpenedCodeAssistant {
        config_path,
        session_id,
    })
}

fn attach_code_assistant_terminal(
    on_event: tauri::ipc::Channel<cli_terminal::CliTerminalEvent>,
    state: &CodeAssistantRuntimeState,
    terminals: &cli_terminal::CliTerminalState,
    workspace_root: String,
    assistant: CodeAssistant,
    cols: u16,
    rows: u16,
) -> Result<String, String> {
    check_ah_version_cached()?;
    let workspace_root = existing_directory(&workspace_root)?;
    let Some(config_path) = ah_config_for_status(&workspace_root, assistant) else {
        return Err(format!("{} is not running", assistant.display_name()));
    };
    let cached = state
        .status_snapshots
        .lock()
        .expect("code assistant status snapshots poisoned")
        .get(&config_path)
        .cloned();
    let snapshot = resolve_open_snapshot(cached.as_ref(), &config_path, &workspace_root);
    let action = snapshot
        .as_ref()
        .map(reconcile_snapshot_lifecycle)
        .unwrap_or(CodeAssistantLifecycleAction::StartFresh);
    match action {
        CodeAssistantLifecycleAction::AttachExisting => {}
        CodeAssistantLifecycleAction::CleanupStale => {
            cleanup_workspace_code_assistants(&workspace_root)?;
            return Err(format!(
                "{} was stale and has been closed; reopen it from Open in.",
                assistant.display_name()
            ));
        }
        CodeAssistantLifecycleAction::StartFresh => {
            return Err(format!("{} is not running", assistant.display_name()));
        }
        CodeAssistantLifecycleAction::HandsOff => {
            return Err(format!(
                "{} is still starting; wait for startup to finish before attaching.",
                assistant.display_name()
            ));
        }
    }
    let launcher =
        write_code_assistant_attach_launcher_script(&workspace_root, &config_path, assistant)?;
    cli_terminal::spawn(
        on_event,
        terminals,
        &cli_terminal_owner_key(&workspace_root, assistant),
        &launcher,
        &workspace_root,
        cli_terminal::initial_size(cols, rows),
    )
}

/// Both Open-in-CLI commands differ only in which assistant they start; the
/// registration + status-stream tail is identical, so it lives here once.
fn open_code_assistant_command(
    app: tauri::AppHandle,
    workspace_root: String,
    state: tauri::State<'_, CodeAssistantRuntimeState>,
    terminals: tauri::State<'_, cli_terminal::CliTerminalState>,
    assistant: CodeAssistant,
    cols: Option<u16>,
    rows: Option<u16>,
    on_event: tauri::ipc::Channel<cli_terminal::CliTerminalEvent>,
) -> Result<String, String> {
    let workspace_root = existing_directory(&workspace_root)?;
    let studio_mcp = studio_mcp_endpoint(&app);
    let opened = open_code_assistant(
        on_event,
        &state,
        &terminals,
        &workspace_root,
        assistant,
        studio_mcp.as_ref(),
        cols.unwrap_or(CLI_TERMINAL_FALLBACK_COLS),
        rows.unwrap_or(CLI_TERMINAL_FALLBACK_ROWS),
    )?;
    state
        .configs
        .lock()
        .expect("code assistant state poisoned")
        .insert(opened.config_path.clone());
    register_opened_code_assistant_status_spec(
        &state,
        &workspace_root,
        assistant,
        &opened.config_path,
    );
    ensure_code_assistant_status_streams_for_workspace(&app, &state, &workspace_root)?;
    emit_code_assistant_status_for_workspace(&app, &state, &workspace_root);
    Ok(opened.session_id)
}

#[tauri::command]
fn open_claude_code(
    app: tauri::AppHandle,
    workspace_root: String,
    state: tauri::State<'_, CodeAssistantRuntimeState>,
    terminals: tauri::State<'_, cli_terminal::CliTerminalState>,
    cols: Option<u16>,
    rows: Option<u16>,
    on_event: tauri::ipc::Channel<cli_terminal::CliTerminalEvent>,
) -> Result<String, String> {
    open_code_assistant_command(
        app,
        workspace_root,
        state,
        terminals,
        CodeAssistant::Claude,
        cols,
        rows,
        on_event,
    )
}

#[tauri::command]
fn open_codex_cli(
    app: tauri::AppHandle,
    workspace_root: String,
    state: tauri::State<'_, CodeAssistantRuntimeState>,
    terminals: tauri::State<'_, cli_terminal::CliTerminalState>,
    cols: Option<u16>,
    rows: Option<u16>,
    on_event: tauri::ipc::Channel<cli_terminal::CliTerminalEvent>,
) -> Result<String, String> {
    open_code_assistant_command(
        app,
        workspace_root,
        state,
        terminals,
        CodeAssistant::Codex,
        cols,
        rows,
        on_event,
    )
}

#[tauri::command]
fn attach_code_assistant(
    workspace_root: String,
    assistant: String,
    state: tauri::State<'_, CodeAssistantRuntimeState>,
    terminals: tauri::State<'_, cli_terminal::CliTerminalState>,
    cols: Option<u16>,
    rows: Option<u16>,
    on_event: tauri::ipc::Channel<cli_terminal::CliTerminalEvent>,
) -> Result<String, String> {
    let assistant = CodeAssistant::from_slug(assistant.trim())?;
    attach_code_assistant_terminal(
        on_event,
        &state,
        &terminals,
        workspace_root,
        assistant,
        cols.unwrap_or(CLI_TERMINAL_FALLBACK_COLS),
        rows.unwrap_or(CLI_TERMINAL_FALLBACK_ROWS),
    )
}

#[tauri::command]
fn cli_terminal_write(
    session_id: String,
    data: String,
    terminals: tauri::State<'_, cli_terminal::CliTerminalState>,
) -> Result<(), String> {
    cli_terminal::write(&terminals, &session_id, &data)
}

#[tauri::command]
fn cli_terminal_resize(
    session_id: String,
    cols: u16,
    rows: u16,
    terminals: tauri::State<'_, cli_terminal::CliTerminalState>,
) -> Result<(), String> {
    cli_terminal::resize(&terminals, &session_id, cols, rows)
}

/// Ends the local terminal client only — detach semantics. The ah runtime keeps
/// running; `close_code_assistant` is the one command that stops it.
#[tauri::command]
fn cli_terminal_detach(
    session_id: String,
    terminals: tauri::State<'_, cli_terminal::CliTerminalState>,
) -> bool {
    cli_terminal::close(&terminals, &session_id)
}

/// 前端观察状态的唯一入口，语义是**幂等的「确保生产者存在」**：确保该 workspace 的每个
/// spec 都有一条 `ah events` 流，并停掉别的 workspace 的流（决议 2026-08-03 D-C2）。
///
/// 没有反向命令。生产者由 `CodeAssistantRuntimeState` 拥有，前端只是观察者——订阅结束
/// 时它只撤销自己建立的那个本地监听器，不得销毁共享的数据源（D-C1）。生产者只在两处
/// 终止：`watch` 切到别的 workspace，以及 app 退出。
#[tauri::command]
fn watch_code_assistant_status(
    app: tauri::AppHandle,
    workspace_root: String,
    state: tauri::State<'_, CodeAssistantRuntimeState>,
) -> Result<(), String> {
    let workspace_root = existing_directory(&workspace_root)?;
    log::info!(
        "phase=code-assistant-status action=watch workspace={}",
        workspace_root.display()
    );
    ensure_code_assistant_status_streams_for_workspace(&app, &state, &workspace_root)?;
    emit_code_assistant_status_for_workspace(&app, &state, &workspace_root);
    Ok(())
}

#[tauri::command]
fn close_code_assistant(
    app: tauri::AppHandle,
    workspace_root: String,
    assistant: String,
    state: tauri::State<'_, CodeAssistantRuntimeState>,
) -> Result<bool, String> {
    let workspace_root = existing_directory(&workspace_root)?;
    let assistant = CodeAssistant::from_slug(assistant.trim())?;
    if ah_config_for_status(&workspace_root, assistant).is_none() {
        restart_status_streams_for_workspace(&app, &state, &workspace_root)?;
        emit_code_assistant_status_for_workspace(&app, &state, &workspace_root);
        return Ok(false);
    }
    let cleanup = cleanup_workspace_code_assistants(&workspace_root)?;
    state
        .configs
        .lock()
        .expect("code assistant state poisoned")
        .retain(|registered_config| !cleanup.configs.contains(registered_config));
    // 只有确认运行时真的消失了，才动观察流：把它重开，让它对着"没有 daemon"重新基线
    // (`daemon_absent` → `inactive`，Open 恢复可点)。确认不了就保留最后一帧快照，
    // 面板继续呈现 `lingering`（可再关一次），而不是在残留还在时谎报可以重新打开。
    if cleanup.runtime_confirmed_gone {
        restart_status_streams_for_workspace(&app, &state, &workspace_root)?;
    }
    emit_code_assistant_status_for_workspace(&app, &state, &workspace_root);
    Ok(cleanup.closed_any)
}

#[tauri::command]
async fn select_directory(
    app: tauri::AppHandle,
    default_path: Option<String>,
) -> Result<Option<String>, String> {
    let mut dialog = app.dialog().file();
    if let Some(default_path) = picker_starting_directory(default_path) {
        dialog = dialog.set_directory(default_path);
    }
    let (sender, receiver) = mpsc::channel();
    dialog.pick_folder(move |path| {
        let _ = sender.send(path.map(|path| path.to_string()));
    });

    tauri::async_runtime::spawn_blocking(move || {
        receiver
            .recv()
            .map_err(|error| format!("directory picker failed: {error}"))
    })
    .await
    .map_err(|error| format!("directory picker task failed: {error}"))?
}

#[tauri::command]
async fn select_file(
    app: tauri::AppHandle,
    default_path: Option<String>,
) -> Result<Option<String>, String> {
    let mut dialog = app.dialog().file();
    if let Some(default_path) = picker_starting_directory(default_path) {
        dialog = dialog.set_directory(default_path);
    }
    let (sender, receiver) = mpsc::channel();
    dialog.pick_file(move |path| {
        let _ = sender.send(path.map(|path| path.to_string()));
    });

    tauri::async_runtime::spawn_blocking(move || {
        receiver
            .recv()
            .map_err(|error| format!("file picker failed: {error}"))
    })
    .await
    .map_err(|error| format!("file picker task failed: {error}"))?
}

fn picker_starting_directory(default_path: Option<String>) -> Option<PathBuf> {
    let candidate = PathBuf::from(default_path?.trim());
    if candidate.as_os_str().is_empty() {
        return None;
    }
    if candidate.is_dir() {
        return Some(candidate);
    }
    if std::fs::create_dir_all(&candidate).is_ok() && candidate.is_dir() {
        return Some(candidate);
    }
    candidate
        .parent()
        .filter(|parent| parent.is_dir())
        .map(PathBuf::from)
}

#[tauri::command]
fn reveal_in_file_manager(path: String) -> Result<(), String> {
    let target = existing_path(&path)?;
    if cfg!(target_os = "macos") {
        return Command::new("open")
            .arg("-R")
            .arg(target)
            .spawn()
            .map(|_| ())
            .map_err(|error| format!("failed to reveal in Finder: {error}"));
    }

    if cfg!(target_os = "linux") {
        return Command::new("xdg-open")
            .arg(target)
            .spawn()
            .map(|_| ())
            .map_err(|error| format!("failed to open file manager: {error}"));
    }

    if cfg!(target_os = "windows") {
        return Command::new("explorer")
            .arg(format!("/select,{}", target.display()))
            .spawn()
            .map(|_| ())
            .map_err(|error| format!("failed to open Explorer: {error}"));
    }

    Err("revealing in file manager is not supported on this platform".to_string())
}

#[tauri::command]
fn open_path(path: String) -> Result<(), String> {
    let target = existing_path(&path)?;
    if cfg!(target_os = "macos") {
        return Command::new("open")
            .arg(target)
            .spawn()
            .map(|_| ())
            .map_err(|error| format!("failed to open path: {error}"));
    }

    if cfg!(target_os = "linux") {
        return Command::new("xdg-open")
            .arg(target)
            .spawn()
            .map(|_| ())
            .map_err(|error| format!("failed to open path: {error}"));
    }

    if cfg!(target_os = "windows") {
        return Command::new("explorer")
            .arg(file_manager_argument(&target))
            .spawn()
            .map(|_| ())
            .map_err(|error| format!("failed to open Explorer: {error}"));
    }

    Err("opening paths is not supported on this platform".to_string())
}

#[cfg(all(target_os = "macos", test))]
fn macos_edit_menu_labels() -> &'static [&'static str] {
    &["Undo", "Redo", "Cut", "Copy", "Paste", "Select All"]
}

#[cfg(target_os = "macos")]
fn macos_menu<R: tauri::Runtime>(app_handle: &tauri::AppHandle<R>) -> tauri::Result<Menu<R>> {
    let pkg_info = app_handle.package_info();
    let config = app_handle.config();
    let about_metadata = AboutMetadata {
        name: Some(pkg_info.name.clone()),
        version: Some(pkg_info.version.to_string()),
        copyright: config.bundle.copyright.clone(),
        authors: config
            .bundle
            .publisher
            .clone()
            .map(|publisher| vec![publisher]),
        ..Default::default()
    };

    let app_menu = Submenu::with_items(
        app_handle,
        pkg_info.name.clone(),
        true,
        &[
            &PredefinedMenuItem::about(app_handle, None, Some(about_metadata))?,
            &PredefinedMenuItem::separator(app_handle)?,
            &PredefinedMenuItem::services(app_handle, None)?,
            &PredefinedMenuItem::separator(app_handle)?,
            &PredefinedMenuItem::hide(app_handle, None)?,
            &PredefinedMenuItem::hide_others(app_handle, None)?,
            &PredefinedMenuItem::separator(app_handle)?,
            &PredefinedMenuItem::quit(app_handle, None)?,
        ],
    )?;
    let file_menu = Submenu::with_items(
        app_handle,
        "File",
        true,
        &[&PredefinedMenuItem::close_window(app_handle, None)?],
    )?;
    let edit_menu = Submenu::with_items(
        app_handle,
        "Edit",
        true,
        &[
            &PredefinedMenuItem::undo(app_handle, None)?,
            &PredefinedMenuItem::redo(app_handle, None)?,
            &PredefinedMenuItem::separator(app_handle)?,
            &PredefinedMenuItem::cut(app_handle, None)?,
            &PredefinedMenuItem::copy(app_handle, None)?,
            &PredefinedMenuItem::paste(app_handle, None)?,
            &PredefinedMenuItem::select_all(app_handle, None)?,
        ],
    )?;
    let view_menu = Submenu::with_items(
        app_handle,
        "View",
        true,
        &[&PredefinedMenuItem::fullscreen(app_handle, None)?],
    )?;
    let window_menu = Submenu::with_items(
        app_handle,
        "Window",
        true,
        &[
            &PredefinedMenuItem::minimize(app_handle, None)?,
            &PredefinedMenuItem::maximize(app_handle, None)?,
            &PredefinedMenuItem::separator(app_handle)?,
            &PredefinedMenuItem::close_window(app_handle, None)?,
        ],
    )?;
    let help_menu = Submenu::with_items(app_handle, "Help", true, &[])?;

    Menu::with_items(
        app_handle,
        &[
            &app_menu,
            &file_menu,
            &edit_menu,
            &view_menu,
            &window_menu,
            &help_menu,
        ],
    )
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let builder = tauri::Builder::default();
    #[cfg(target_os = "macos")]
    let builder = builder.enable_macos_default_menu(false).menu(macos_menu);

    let app = builder
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            get_sidecar_config,
            get_sidecar_stderr,
            confirm_quit_ready,
            restart_sidecar,
            select_directory,
            select_file,
            reveal_in_file_manager,
            open_path,
            open_claude_code,
            open_codex_cli,
            attach_code_assistant,
            cli_terminal_write,
            cli_terminal_resize,
            cli_terminal_detach,
            watch_code_assistant_status,
            close_code_assistant,
            native_fs::write_workspace_file,
            native_fs::publish_package_writer,
            native_fs::read_workspace_file,
            native_fs::delete_workspace_path,
            native_fs::move_workspace_path,
            native_fs::list_workspace_dir,
            native_fs::checkpoint_workspace_file,
            native_fs::seed_workspace_checkpoint,
            native_fs::restore_workspace_file,
            native_fs::clear_workspace_checkpoint,
            native_fs::add_recent_workspace,
            native_fs::list_recent_workspaces,
            native_fs::remove_recent_workspace,
            native_fs::ensure_workspace_support_dirs,
            native_fs::create_skill_workspace,
            native_fs::open_skill_workspace,
            native_fs::workspace_path_exists
        ])
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }
            // R-F19.2 — shared state polled by the exit handler after emitting
            // `before-quit`; reset to false here so a previous quit cycle never
            // leaks readiness into a fresh session.
            app.manage(QuitFlushState {
                ready: AtomicBool::new(false),
            });
            app.manage(cli_terminal::CliTerminalState::default());
            app.manage(CodeAssistantRuntimeState {
                configs: Mutex::new(BTreeSet::new()),
                status_streams: Mutex::new(BTreeMap::new()),
                status_specs: Mutex::new(BTreeMap::new()),
                status_snapshots: Mutex::new(BTreeMap::new()),
            });
            if std::env::var("STUDIO_TAURI_DISABLE_SIDECAR").as_deref() != Ok("1") {
                let resolved_resource_root = app
                    .path()
                    .resource_dir()
                    .unwrap_or_else(|_| sidecar::default_tauri_dir());
                let resource_root = sidecar::resource_root_for_runtime(resolved_resource_root);
                register_studio_resource_root(&resource_root);
                let config = sidecar::SidecarLaunchConfig::from_resource_root(resource_root)
                    .with_config_dir(resolve_config_dir());
                match sidecar::SidecarManager::start(config) {
                    Ok(manager) => app.manage(SidecarAppState {
                        manager: Mutex::new(Some(manager)),
                        startup_error: Mutex::new(None),
                    }),
                    Err(error) => app.manage(SidecarAppState {
                        manager: Mutex::new(None),
                        startup_error: Mutex::new(Some(format!(
                            "failed to start Python sidecar: {error}"
                        ))),
                    }),
                };
            } else {
                app.manage(SidecarAppState {
                    manager: Mutex::new(None),
                    startup_error: Mutex::new(Some("Python sidecar disabled".to_string())),
                });
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    let exiting = Arc::new(AtomicBool::new(false));
    app.run(move |app_handle, event| {
        if let tauri::RunEvent::WindowEvent {
            event: tauri::WindowEvent::CloseRequested { api, .. },
            ..
        } = &event
        {
            if exiting.swap(true, Ordering::SeqCst) {
                return;
            }
            api.prevent_close();
            shutdown_application(app_handle.clone(), "window-close");
            return;
        }

        if let tauri::RunEvent::ExitRequested { api, .. } = event {
            if exiting.swap(true, Ordering::SeqCst) {
                return;
            }
            api.prevent_exit();
            let app_handle = app_handle.clone();
            std::thread::spawn(move || {
                // R-F19.2 — give the frontend a budgeted window to flush any
                // in-flight debounced roles save before we tear down the
                // sidecar. We emit `before-quit`, then poll a shared
                // `QuitFlushState::ready` flag set by the `confirm_quit_ready`
                // tauri command (FE calls it after `flushRolesSave()`
                // resolves). If the flag isn't set within `QUIT_FLUSH_BUDGET`
                // (e.g. the FE is gone or hung), we proceed anyway so the user
                // is never trapped — and log a warning so silent loss is
                // visible per rules/logging.md.
                wait_for_quit_flush(&app_handle, QUIT_FLUSH_BUDGET);
                let mut code_assistant_configs = BTreeSet::new();
                if let Some(state) = app_handle.try_state::<CodeAssistantRuntimeState>() {
                    code_assistant_configs.extend(
                        state
                            .configs
                            .lock()
                            .expect("code assistant state poisoned")
                            .iter()
                            .cloned(),
                    );
                    stop_all_code_assistant_status_streams(&state);
                }
                code_assistant_configs.extend(discover_studio_ah_configs());
                cleanup_registered_code_assistants(code_assistant_configs);
                if let Some(state) = app_handle.try_state::<SidecarAppState>() {
                    if let Some(manager) =
                        state.manager.lock().expect("sidecar state poisoned").take()
                    {
                        manager.shutdown_blocking();
                    }
                }
                app_handle.exit(0);
            });
        }
    });
}

/// R-F19.2 helper — emit `before-quit` to all windows and block (up to
/// `budget`) waiting for the frontend to ack via `confirm_quit_ready`.
/// Returns true if the FE acked in time, false on timeout.
fn wait_for_quit_flush<R: tauri::Runtime>(app: &tauri::AppHandle<R>, budget: Duration) -> bool {
    let Some(state) = app.try_state::<QuitFlushState>() else {
        // Quit-flush state was never managed (e.g. setup failed); skip the
        // handshake instead of blocking forever.
        log::warn!("phase=quit action=flush-skip reason=quit_flush_state_missing");
        return false;
    };
    // Reset before emitting so a stale ack from a previous session can't be
    // mistaken for the current cycle's ack.
    state.ready.store(false, Ordering::SeqCst);
    if let Err(error) = app.emit("before-quit", ()) {
        log::warn!("phase=quit action=emit-before-quit-failed reason={error}");
        return false;
    }
    log::info!(
        "phase=quit action=emit-before-quit budget_ms={}",
        budget.as_millis()
    );

    let deadline = Instant::now() + budget;
    while Instant::now() < deadline {
        if state.ready.load(Ordering::SeqCst) {
            log::info!(
                "phase=quit action=flush-acked waited_ms={}",
                budget
                    .saturating_sub(deadline.saturating_duration_since(Instant::now()))
                    .as_millis()
            );
            return true;
        }
        std::thread::sleep(QUIT_FLUSH_POLL_INTERVAL);
    }
    log::warn!(
        "phase=quit action=flush-timeout budget_ms={} note=proceeding_without_ack",
        budget.as_millis()
    );
    false
}

fn shutdown_application<R: tauri::Runtime>(app_handle: tauri::AppHandle<R>, reason: &'static str) {
    std::thread::spawn(move || {
        log::info!("phase=shutdown action=start reason={reason}");
        // R-F19.2 — give the frontend a budgeted window to flush any
        // in-flight debounced roles save before we tear down the sidecar. We
        // emit `before-quit`, then poll a shared `QuitFlushState::ready` flag
        // set by the `confirm_quit_ready` tauri command (FE calls it after
        // `flushRolesSave()` resolves). If the flag isn't set within
        // `QUIT_FLUSH_BUDGET` (e.g. the FE is gone or hung), we proceed anyway
        // so the user is never trapped — and log a warning so silent loss is
        // visible per rules/logging.md.
        wait_for_quit_flush(&app_handle, QUIT_FLUSH_BUDGET);
        // Embedded terminals are local tmux clients: dropping them first is a
        // detach, so the ah cleanup below decides what actually stops.
        if let Some(terminals) = app_handle.try_state::<cli_terminal::CliTerminalState>() {
            cli_terminal::close_all(&terminals);
        }
        let mut code_assistant_configs = BTreeSet::new();
        if let Some(state) = app_handle.try_state::<CodeAssistantRuntimeState>() {
            code_assistant_configs.extend(
                state
                    .configs
                    .lock()
                    .expect("code assistant state poisoned")
                    .iter()
                    .cloned(),
            );
            stop_all_code_assistant_status_streams(&state);
        }
        code_assistant_configs.extend(discover_studio_ah_configs());
        cleanup_registered_code_assistants(code_assistant_configs);
        if let Some(state) = app_handle.try_state::<SidecarAppState>() {
            if let Some(manager) = state.manager.lock().expect("sidecar state poisoned").take() {
                manager.shutdown_blocking();
            }
        }
        log::info!("phase=shutdown action=exit reason={reason}");
        app_handle.exit(0);
    });
}

#[derive(Deserialize, Serialize, Debug, Clone, Copy, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
enum AhRuntimeState {
    Active,
    Inactive,
    Starting,
    Degraded,
}

#[derive(Deserialize, Serialize, Debug, Clone, PartialEq, Eq)]
struct AhSessionSnapshot {
    session_id: String,
    project_id: String,
    path: String,
    status: String,
    live_agents: u64,
    db_tracked_agents: u64,
    cleanup_required: bool,
    safe_to_cleanup: bool,
}

#[derive(Deserialize, Serialize, Debug, Clone, PartialEq, Eq)]
struct AhRuntimeSnapshot {
    schema_version: u64,
    runtime_state: AhRuntimeState,
    active: bool,
    ahd_alive: bool,
    sequence: u64,
    reason: Option<String>,
    config_path: Option<String>,
    /// 这套运行时的 tmux server 是否还在。死窗格活在 server 里，server 没了就什么都
    /// 没剩下——所以它才是"还有没有东西需要收尾"的判据（见
    /// `assistant_status_for_snapshot`），`ahd_alive` 不是。
    #[serde(default)]
    tmux_server_alive: bool,
    #[serde(default)]
    master_tmux_alive: bool,
    #[serde(default)]
    worker_tmux_alive: bool,
    #[serde(default)]
    sessions: Vec<AhSessionSnapshot>,
    #[serde(default)]
    state_dir: String,
}

fn parse_ah_runtime_snapshot(snapshot_json: &str) -> Result<AhRuntimeSnapshot, String> {
    let snapshot: AhRuntimeSnapshot = serde_json::from_str(snapshot_json)
        .map_err(|e| format!("Invalid JSON in snapshot: {e}"))?;

    if snapshot.schema_version != 2 {
        return Err(format!(
            "Unsupported schema version: {} (expected 2)",
            snapshot.schema_version
        ));
    }

    Ok(snapshot)
}

/// Project a typed runtime snapshot onto the lifecycle action Open/Attach should take.
///
/// Decided from the `runtime_state` PHASE, not `active` alone: keying on `active` collapses
/// every non-active phase to `StartFresh`, which would fire a duplicate `ah start` on a
/// `starting` runtime (Req 3.6 forbids it) and skip the cleanup-then-start path on a
/// `degraded` one (Req 3.7). Each phase maps to exactly one outcome:
/// - `Active`   → attach the existing runtime.
/// - `Starting` → hands-off: startup is in progress, take no lifecycle action (Req 3.6).
/// - `Degraded` → cleanup the stale sessions first; the Open flow resolves `CleanupStale`
///   to cleanup + a fresh start, so Open stays usable rather than three-buttons-dark
///   (Req 3.7/5.7).
/// - `Inactive` 且 ahd 仍在 → 这是残留(`lingering`)而不是干净的空位:ah 只在 ahd 退出时才
///   回收 tmux,所以运行时和 `remain-on-exit` 留下的死窗格都还在。一个 workspace 同一时刻
///   只允许一个 CLI 运行时存在,启动之前必须先把它清掉(决议 2026-08-02 D-A4),否则新的
///   master 会以 `new-window -d` 挂进同一个 tmux 会话,而 attach 落回那块死窗格。
/// - `Inactive` 且 ahd 已不在 → 运行时确实被回收过,直接启动。
fn reconcile_snapshot_lifecycle(snapshot: &AhRuntimeSnapshot) -> CodeAssistantLifecycleAction {
    match snapshot.runtime_state {
        AhRuntimeState::Active => CodeAssistantLifecycleAction::AttachExisting,
        AhRuntimeState::Starting => CodeAssistantLifecycleAction::HandsOff,
        AhRuntimeState::Degraded => CodeAssistantLifecycleAction::CleanupStale,
        AhRuntimeState::Inactive if snapshot.ahd_alive => {
            CodeAssistantLifecycleAction::CleanupStale
        }
        AhRuntimeState::Inactive => CodeAssistantLifecycleAction::StartFresh,
    }
}

/// The Open decision the live `prepare_code_assistant_open` entry consumes, driven by the typed
/// `runtime_state` phase from the events-primary/status-fallback plane — never `ah ps` text or
/// tmux probing (design.md:27/178/325). Replaces the deleted boolean `decide_code_assistant_open`
/// (task6.1-seam-decision-2026-07-10.md, master 裁决 2).
///
/// The requested runtime's phase decides the base action via `reconcile_snapshot_lifecycle`
/// (Active→attach, Degraded/lingering→cleanup-then-start, Inactive-with-ahd-gone→start fresh,
/// Starting→hands-off). `others` 的残留同样触发清理:一个 workspace 同一时刻只允许一个 CLI
/// 运行时存在,所以启动之前必须把全部残留清干净——否则本次启动完就凑成"某个助手有残留 +
/// 另一个正在跑"这个不允许的组合(决议 2026-08-02 D-A4)。而"另一个真的在跑"由
/// `RejectOtherActive` 单独拦住,优先于清理:那是让用户自己去关,不是替他关。
///
/// A `Starting` requested runtime is hands-off regardless of `others`: it is the requested
/// runtime's own phase that governs, so Open leaves the in-progress startup alone rather than
/// acting on a cross-assistant condition. (This resolves the `Starting`+other-active combination
/// the decision doc §四 left to this lane — hands-off wins.)
fn decide_code_assistant_open_v2(
    requested: Option<&AhRuntimeSnapshot>,
    others: &[AhRuntimeSnapshot],
) -> CodeAssistantOpenDecision {
    let requested_action = requested
        .map(reconcile_snapshot_lifecycle)
        .unwrap_or(CodeAssistantLifecycleAction::StartFresh);

    if requested_action == CodeAssistantLifecycleAction::HandsOff {
        return CodeAssistantOpenDecision::HandsOff;
    }

    let other_actions = others
        .iter()
        .map(reconcile_snapshot_lifecycle)
        .collect::<Vec<_>>();
    let has_stale = requested_action == CodeAssistantLifecycleAction::CleanupStale
        || other_actions
            .iter()
            .any(|action| *action == CodeAssistantLifecycleAction::CleanupStale);
    let other_active_count = other_actions
        .iter()
        .filter(|action| **action == CodeAssistantLifecycleAction::AttachExisting)
        .count();

    // 只允许一个 CLI 在跑:另一个助手真的在跑时一律拒绝,让用户自己先关掉它。这一条必须排在
    // 清理之前——"启动前清全部残留"针对的是残留,不能被扩大解释成"替用户关掉正在干活的 CLI"
    // (决议 2026-08-02 D-A4)。
    if requested_action != CodeAssistantLifecycleAction::AttachExisting && other_active_count > 0 {
        return CodeAssistantOpenDecision::RejectOtherActive;
    }

    if has_stale
        || (requested_action == CodeAssistantLifecycleAction::AttachExisting
            && other_active_count > 0)
    {
        CodeAssistantOpenDecision::CleanupStale
    } else if requested_action == CodeAssistantLifecycleAction::AttachExisting {
        CodeAssistantOpenDecision::AttachRequested
    } else if other_active_count > 0 {
        CodeAssistantOpenDecision::RejectOtherActive
    } else {
        CodeAssistantOpenDecision::StartFresh
    }
}

/// SSOT projection of ah's `runtime_state` phase onto the per-assistant `AssistantStatus`
/// the frontend renders (tasks.md:90, design.md:132-133, Req 5.6/6.1). This is the single
/// mapping every UI surface projects; `Error` is produced upstream on parse/identity
/// failure and never from a `runtime_state` value.
/// 把一帧运行时快照投影成面板呈现的助手状态。
///
/// `inactive` 这个 phase 只说明"没有活的会话"，它并不说明"这套运行时已经被回收"。`/exit`
/// 之后 ah 把会话标成终态却**不回收 tmux**（生产代码里回收 tmux 的唯一位置是 ahd 收到
/// SIGTERM 时的整体 `kill-server`），那块 `remain-on-exit` 死窗格还在，面板必须继续给
/// Close 而不是谎称可以重新打开 —— 这是 2026-08-02 决议 D-A1 要解决的问题，不变。
///
/// **判据取 `tmux_server_alive`，不取 `ahd_alive`（2026-08-04 修正）。** D-A1 原文推的是
/// "ah 只在 ahd 退出时才回收 tmux ⇒ `ahd_alive == true` 与 tmux 未回收是同一件事"，但这个
/// 蕴含只有一个方向：ahd 活着**不代表** tmux server 存在——它可以从来没建过，也可以被外部
/// 带走（机器重启把 tmux 全清掉、而 ahd 又被重新拉起，就是本机实测到的形状）。实测
/// 2026-08-04：Studio 管的 6 份 config 里有 4 份处于 `ahd_alive:true` +
/// `tmux_server_alive:false` + `ahd_has_inventory:false`，旧判据把它们全报成"运行中"，
/// 面板给出一个 attach 不到任何东西、也无事可关的 Close 控件。
///
/// 而"还有没有东西需要收尾"这件事，快照里本来就直接带着：死窗格活在 tmux server 里，
/// server 没了就什么都没剩下。所以 `Lingering` 的条件是 tmux server 仍在。
///
/// 判据同样不取 `sessions[].cleanup_required`：后者一旦为真便永远为真（ah 没有任何路径把
/// `master_pid` 清零），用它驱动 UI 会把面板永久钉死在"运行中"，Close 也解不开。
///
/// 注意这里只改**面板呈现**这条道。启动前该不该先清残留是另一条道
/// （`reconcile_snapshot_lifecycle`），它继续用 `ahd_alive`：游离的 ahd 即使没有 tmux
/// 也该在启动新运行时之前清掉（D-A4"一个 workspace 同一时刻只允许一个运行时"），
/// 那一层宁可多清，与"要不要告诉用户有东西在跑"是两个不同的问题。
fn assistant_status_for_snapshot(snapshot: &AhRuntimeSnapshot) -> AssistantStatus {
    match snapshot.runtime_state {
        AhRuntimeState::Active => AssistantStatus::Active,
        AhRuntimeState::Starting => AssistantStatus::Starting,
        AhRuntimeState::Degraded => AssistantStatus::Degraded,
        AhRuntimeState::Inactive if snapshot.tmux_server_alive => AssistantStatus::Lingering,
        AhRuntimeState::Inactive => AssistantStatus::Inactive,
    }
}

#[derive(Debug, Clone)]
struct SequenceArbiter {
    last_sequence: Option<u64>,
    last_session_id: Option<String>,
}

impl SequenceArbiter {
    fn new() -> Self {
        Self {
            last_sequence: None,
            last_session_id: None,
        }
    }

    fn accept(&mut self, snapshot: &AhRuntimeSnapshot) -> bool {
        let current_session_id = snapshot.sessions.first().map(|s| s.session_id.clone());
        let is_reset = if self.last_sequence.is_none() {
            true
        } else if snapshot.reason.as_deref() == Some("initial") {
            true
        } else if current_session_id != self.last_session_id {
            true
        } else {
            false
        };

        if is_reset {
            self.last_sequence = Some(snapshot.sequence);
            self.last_session_id = current_session_id;
            true
        } else {
            if let Some(last_seq) = self.last_sequence {
                if snapshot.sequence > last_seq {
                    self.last_sequence = Some(snapshot.sequence);
                    self.last_session_id = current_session_id;
                    true
                } else {
                    false
                }
            } else {
                self.last_sequence = Some(snapshot.sequence);
                self.last_session_id = current_session_id;
                true
            }
        }
    }
}

fn resolve_bootstrap_snapshot(
    status_json_result: Result<&str, &str>,
    events_snapshot_json: Option<&str>,
) -> Result<AhRuntimeSnapshot, String> {
    if let Some(events_json) = events_snapshot_json {
        parse_ah_runtime_snapshot(events_json)
    } else {
        match status_json_result {
            Ok(status_json) => parse_ah_runtime_snapshot(status_json),
            Err(stderr) => Err(stderr.to_string()),
        }
    }
}

fn verify_snapshot_identity(
    snapshot_json: &str,
    requested_config_path: &Path,
    requested_workspace_dir: &Path,
) -> Result<(), String> {
    let _ = requested_config_path;
    let snapshot = parse_ah_runtime_snapshot(snapshot_json)?;

    let requested_wsl = windows_path_to_wsl(requested_workspace_dir);
    let requested_wsl_path = Path::new(&requested_wsl);

    let slashed = requested_workspace_dir.to_string_lossy().replace('\\', "/");
    let expected_project_id = slashed
        .split('/')
        .last()
        .unwrap_or("")
        .to_string();

    if expected_project_id.is_empty() {
        return Err("Derived expected project_id is empty".to_string());
    }

    let state_dir_wsl = windows_path_to_wsl(Path::new(&snapshot.state_dir));
    let state_dir_wsl_path = Path::new(&state_dir_wsl);
    
    let hash = workspace_hash(requested_workspace_dir);
    let is_state_dir_under_workspace = state_dir_wsl_path.starts_with(requested_wsl_path)
        || state_dir_wsl.contains(&requested_wsl);
    let is_state_dir_matching_hash = state_dir_wsl.contains(&hash);

    if !is_state_dir_under_workspace && !is_state_dir_matching_hash {
        return Err(format!(
            "state_dir mismatch: snapshot state_dir '{}' (WSL: '{}') is not associated with requested workspace '{}' (WSL: '{}', Hash: '{}')",
            snapshot.state_dir, state_dir_wsl, requested_workspace_dir.display(), requested_wsl, hash
        ));
    }

    if !snapshot.sessions.is_empty() {
        let mut matched = false;
        for session in &snapshot.sessions {
            let session_path_wsl = windows_path_to_wsl(Path::new(&session.path));
            if session_path_wsl == requested_wsl && session.project_id == expected_project_id {
                matched = true;
                break;
            }
        }
        if !matched {
            return Err(format!(
                "session identity mismatch: expected project_id '{}' and path '{}' (WSL: '{}'), but got sessions: {:?}",
                expected_project_id, requested_workspace_dir.display(), requested_wsl, snapshot.sessions
            ));
        }
    }

    Ok(())
}

/// The events-primary/status-fallback typed snapshot an Open/Attach decision reads
/// (design.md:92-158, 裁决 1.4). A cached frame from this config's supervised `ah events`
/// stream wins (events-primary; the per-config stream already scopes it to this ahd). With no
/// frame yet it bootstraps from `ah status --json` and verifies the snapshot really describes
/// THIS workspace before any lifecycle decision consumes it. `None` means "no runtime info"
/// (ahd absent and uncached) — the caller treats that as start-fresh. It never parses `ah ps`
/// text or probes tmux (design.md:27/178/325).
fn resolve_open_snapshot(
    cached: Option<&AhRuntimeSnapshot>,
    config_path: &Path,
    workspace_dir: &Path,
) -> Option<AhRuntimeSnapshot> {
    if let Some(snapshot) = cached {
        return Some(snapshot.clone());
    }

    let status = run_ah_config_command_output(config_path, &["status", "--json"]).ok()?;
    let status_result: Result<&str, &str> = if status.success {
        Ok(status.stdout.as_str())
    } else {
        Err(status.stderr.as_str())
    };
    let snapshot = resolve_bootstrap_snapshot(status_result, None).ok()?;
    verify_snapshot_identity(status.stdout.as_str(), config_path, workspace_dir).ok()?;
    Some(snapshot)
}

/// The session ids Close/app-quit cleanup may escalate with `ah kill --session
/// <id> --force`, taken ONLY from the identity-checked snapshot's own `sessions[]`
/// and driven by ah's own per-session judgment — never Studio re-deriving
/// "non-terminal therefore kill" (Req 4.2/5.5, design.md:226).
///
/// A healthy ACTIVE session ah has NOT flagged (`cleanup_required:false`, carrying
/// `safe_to_cleanup:false` because it holds live work) must be spared; a terminal
/// CLOSED session needs no cleanup. `safe_to_cleanup` is ah's safety gate against
/// killing live work, NOT a kill trigger, so `!safe_to_cleanup` alone must never
/// escalate a kill — only ah's own `cleanup_required` flag selects a target. The
/// `BTreeSet` dedupes and orders the ids for a deterministic escalation set.
fn cleanup_target_session_ids(snapshot: &AhRuntimeSnapshot) -> BTreeSet<String> {
    snapshot
        .sessions
        .iter()
        .filter(|session| session.cleanup_required)
        .map(|session| session.session_id.clone())
        .collect()
}

/// The post-stop snapshot cleanup reads to decide `ah kill` targets (design.md:225
/// "Re-read the current snapshot ... after stop"), always through the typed
/// events-primary/status-fallback plane — never `ah ps` text or tmux probing
/// (design.md:178).
///
/// When the caller knows the workspace (Close, and the Open/Attach cleanup-stale
/// branches) it goes through `resolve_open_snapshot`, which bootstraps a fresh
/// `status --json` read and verifies the snapshot's own identity really matches
/// the requested workspace before any kill consumes it. The app-quit sweep has
/// only the config path (no workspace to disambiguate); `ah --config <path> status
/// --json` is already scoped to exactly that ahd, so it reads config-scoped
/// without the workspace identity gate.
fn resolve_cleanup_snapshot(
    config_path: &Path,
    workspace_dir: Option<&Path>,
) -> Option<AhRuntimeSnapshot> {
    if let Some(workspace_dir) = workspace_dir {
        return resolve_open_snapshot(None, config_path, workspace_dir);
    }
    let status = run_ah_config_command_output(config_path, &["status", "--json"]).ok()?;
    if !status.success {
        return None;
    }
    parse_ah_runtime_snapshot(&status.stdout).ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_path(name: &str) -> PathBuf {
        std::env::temp_dir().join(format!("skill-studio-tauri-{name}-{}", std::process::id()))
    }

    #[test]
    fn picker_starting_directory_creates_missing_default_directory() {
        let target = temp_path("picker-default");
        let _ = std::fs::remove_dir_all(&target);

        let selected = picker_starting_directory(Some(target.display().to_string()));

        assert_eq!(selected.as_deref(), Some(target.as_path()));
        assert!(target.is_dir());
        let _ = std::fs::remove_dir_all(&target);
    }

    #[test]
    fn picker_starting_directory_ignores_empty_default() {
        assert!(picker_starting_directory(Some("  ".to_string())).is_none());
        assert!(picker_starting_directory(None).is_none());
    }

    #[test]
    fn config_dir_override_honors_non_empty_value() {
        let resolved = config_dir_from_override(Some("/tmp/studio-iso".into()));
        assert_eq!(
            resolved.as_deref(),
            Some(std::path::Path::new("/tmp/studio-iso"))
        );
    }

    #[test]
    fn config_dir_override_ignores_empty_and_absent() {
        assert!(config_dir_from_override(Some("".into())).is_none());
        assert!(config_dir_from_override(None).is_none());
    }

    #[test]
    fn invoke_handler_registers_publish_package_writer_command() {
        let source = include_str!("lib.rs");
        assert!(
            source.contains("native_fs::publish_package_writer"),
            "publish package writer must be registered in the Tauri invoke handler"
        );
    }

    #[test]
    fn invoke_handler_registers_move_workspace_path_command() {
        let source = include_str!("lib.rs");
        assert!(
            source.contains("native_fs::move_workspace_path"),
            "move workspace path must be registered in the Tauri invoke handler"
        );
    }

    /// R-F19.2 — make sure the `confirm_quit_ready` command stays wired into
    /// the invoke handler (it's the frontend's only way to ack the
    /// `before-quit` flush handshake before sidecar shutdown).
    #[test]
    fn invoke_handler_registers_open_path_command() {
        let source = include_str!("lib.rs");
        assert!(
            source.contains("open_path,"),
            "open_path must be registered in the Tauri invoke handler"
        );
    }

    #[test]
    fn invoke_handler_registers_open_claude_code_command() {
        let source = include_str!("lib.rs");
        assert!(
            source.contains("open_claude_code,"),
            "open_claude_code must be registered in the Tauri invoke handler"
        );
    }

    #[test]
    fn invoke_handler_registers_open_codex_cli_command() {
        let source = include_str!("lib.rs");
        assert!(
            source.contains("open_codex_cli,"),
            "open_codex_cli must be registered in the Tauri invoke handler"
        );
    }

    #[test]
    fn invoke_handler_registers_code_assistant_lifecycle_commands() {
        let source = include_str!("lib.rs");
        assert!(
            source.contains("attach_code_assistant,"),
            "attach_code_assistant must be registered in the Tauri invoke handler"
        );
        assert!(
            source.contains("watch_code_assistant_status,"),
            "watch_code_assistant_status must be registered in the Tauri invoke handler"
        );
        assert!(
            source.contains("close_code_assistant,"),
            "close_code_assistant must be registered in the Tauri invoke handler"
        );
    }

    #[test]
    fn toml_string_escapes_control_characters_instead_of_breaking_the_line() {
        // A literal newline ends a TOML basic string early, so a value carrying
        // one produced a config `ah start` refused to parse.
        assert_eq!(toml_string("a\nb"), "\"a\\nb\"");
        assert_eq!(toml_string("a\tb"), "\"a\\tb\"");
        assert_eq!(toml_string("a\r\nb"), "\"a\\r\\nb\"");
        assert_eq!(toml_string("say \"hi\""), "\"say \\\"hi\\\"\"");
    }

    #[test]
    fn transient_config_parses_as_toml_with_a_bound_skill() {
        // The regression this file exists for: the identity injected into the
        // master prompt carried newlines, the config stopped parsing, and
        // `Open in CLI` died at `ah start` (exit 3) — while a
        // `cmd.contains("<skill id>")` assertion stayed happily green.
        let context = SessionSkillContext {
            skill_id: "exp-b-round4".to_string(),
            workspace_root: "D:\\coding\\skills\\exp-b-round4".to_string(),
        };

        for assistant in [CodeAssistant::Claude, CodeAssistant::Codex] {
            let content = transient_ah_config_content(assistant, None, Some(&context))
                .expect("config content");
            let parsed: toml::Table = toml::from_str(&content)
                .unwrap_or_else(|error| panic!("{assistant:?} transient config must parse: {error}"));
            let cmd = parsed["master"]["cmd"].as_str().expect("cmd string");
            assert!(cmd.contains("exp-b-round4"), "identity must survive escaping");
        }
    }

    #[test]
    fn master_prompt_tells_the_session_which_skill_it_is_bound_to() {
        // F3/F13: the session was never told its own skill_id, so the model
        // inferred one from the manifest name — and once operated on a different,
        // protected skill because the names matched (exp-B R0).
        let context = SessionSkillContext {
            skill_id: "exp-b-round3".to_string(),
            workspace_root: "/mnt/d/coding/skills/exp-b-round3".to_string(),
        };

        let prompt = master_prompt(Some(&context));

        assert!(prompt.starts_with(MOIRAI_MASTER_REPORT_PROMPT));
        assert!(prompt.contains("exp-b-round3"));
        assert!(prompt.contains("/mnt/d/coding/skills/exp-b-round3"));
    }

    #[test]
    fn master_prompt_stays_bare_when_the_workspace_is_not_a_registered_skill() {
        assert_eq!(master_prompt(None), MOIRAI_MASTER_REPORT_PROMPT);
    }

    #[test]
    fn master_cmd_carries_the_skill_identity_into_the_launched_command() {
        let context = SessionSkillContext {
            skill_id: "exp-b-round3".to_string(),
            workspace_root: "/mnt/d/coding/skills/exp-b-round3".to_string(),
        };

        for assistant in [CodeAssistant::Claude, CodeAssistant::Codex] {
            let cmd = assistant.master_cmd(None, Some(&context));
            assert!(
                cmd.contains("exp-b-round3"),
                "{assistant:?} master cmd must name the bound skill"
            );
        }
    }

    #[test]
    fn claude_master_cmd_rejects_interop_binaries() {
        let cmd = claude_master_cmd(None, None);

        assert!(cmd.contains("claude_target=$(readlink -f \"$claude_real\""));
        assert!(cmd.contains("case \"$claude_target\" in /mnt/*)"));
        assert!(cmd.contains("claude resolves to a Windows binary"));
        assert!(cmd.contains("HOME injection"));
        assert!(cmd.contains("scripts/install-claude-code-wsl.ps1"));
        assert!(cmd.contains("mkdir -p \"$HOME/.local/bin\" \"$HOME/.claude\""));
        assert!(cmd.contains("$STUDIO_AH_HOST_HOME/.claude/.credentials.json"));
        assert!(cmd.contains("$HOME/.claude/.credentials.json"));
    }

    #[test]
    fn master_cmd_carries_the_mcp_endpoint_itself_instead_of_inheriting_it() {
        // The master is spawned by ahd, and ahd does not inherit the launcher
        // shell's environment — measured on a live session: the daemon and every
        // process under it had zero STUDIO_* variables, so the guarded
        // --mcp-config block silently dropped and the CLI came up with "No MCP
        // servers configured" while the launcher believed it had wired the tool
        // surface. The endpoint therefore travels INSIDE the command string,
        // which ahd runs verbatim. (Same reasoning as build_ah_bash_script:
        // an in-script export is the only env a spawned shell is guaranteed to
        // see.)
        let endpoint = StudioMcpEndpoint {
            port: 8787,
            token: "tok-abc".to_string(),
        };

        for cmd in [
            claude_master_cmd(Some(&endpoint), None),
            codex_master_cmd(Some(&endpoint), None),
        ] {
            let url_at = cmd
                .find("export STUDIO_MCP_URL=")
                .unwrap_or_else(|| panic!("the endpoint must be baked into the command: {cmd}"));
            assert!(cmd.contains("http://127.0.0.1:8787/mcp"), "{cmd}");
            assert!(
                cmd.contains("export STUDIO_API_TOKEN="),
                "the token must be baked into the command: {cmd}"
            );
            assert!(cmd.contains("tok-abc"), "{cmd}");
            let guard_at = cmd
                .find("${STUDIO_MCP_URL:-}")
                .unwrap_or_else(|| panic!("the MCP block must still be guarded: {cmd}"));
            assert!(
                url_at < guard_at,
                "the export has to run BEFORE the guard reads it: {cmd}"
            );
        }

        // Sidecar unreachable: no endpoint, no exports, and the session still
        // starts (just without Studio tools).
        for cmd in [claude_master_cmd(None, None), codex_master_cmd(None, None)] {
            assert!(!cmd.contains("export STUDIO_MCP_URL="));
            assert!(!cmd.contains("export STUDIO_API_TOKEN="));
        }
    }

    #[test]
    fn claude_master_cmd_registers_studio_mcp_with_native_approvals() {
        // N5-3: the CLI surface gets the same Studio tools as the panel. Approval
        // is claude's OWN prompt (bypass flag dropped) — Studio does not build a
        // second approval system for a session the user is sitting in.
        let cmd = claude_master_cmd(None, None);

        assert!(cmd.contains("$HOME/.claude/studio-mcp.json"));
        assert!(cmd.contains("\"type\":\"http\""));
        assert!(cmd.contains("${STUDIO_MCP_URL}"));
        // The token reaches the CLI through env expansion, never as plaintext in
        // the config file (a skill repo's Local History would snapshot it).
        assert!(cmd.contains("${STUDIO_API_TOKEN}"));
        assert!(cmd.contains("--mcp-config"));
        assert!(cmd.contains("--allowedTools"));
        assert!(cmd.contains("mcp__studio__compile_skill"));
        assert!(
            !cmd.contains("--dangerously-skip-permissions"),
            "interactive Open in CLI must keep claude's native approval prompts"
        );
    }

    #[test]
    fn claude_master_cmd_skips_mcp_when_sidecar_unreachable() {
        // No STUDIO_MCP_URL (sidecar not up / non-mirrored network): the session
        // must still launch, just without the Studio tools — never hard-fail.
        let cmd = claude_master_cmd(None, None);

        assert!(cmd.contains("if [ -n \"${STUDIO_MCP_URL:-}\" ]"));
        assert!(cmd.contains("studio_mcp_args="));
    }

    #[test]
    fn codex_master_cmd_registers_studio_mcp_streamable_http() {
        // codex 0.142.5 speaks streamable HTTP natively (--url +
        // --bearer-token-env-var), so no stdio bridge is needed.
        let cmd = codex_master_cmd(None, None);

        assert!(cmd.contains("[mcp_servers.studio]"));
        assert!(cmd.contains("bearer_token_env_var = \"STUDIO_API_TOKEN\""));
        assert!(cmd.contains("${STUDIO_MCP_URL}"));
    }

    #[test]
    fn wsl_payload_exports_studio_mcp_env_when_sidecar_known() {
        // The payload carries the sidecar's port+token into WSL. WSL mirrored
        // networking reaches the Windows sidecar on localhost (verified on this
        // host); a non-mirrored distro simply gets no URL and no Studio tools.
        let payload = wsl_payload_script(
            "/mnt/d/ws",
            "/mnt/d/ws/ah.toml",
            CodeAssistant::Claude,
            None,
            None,
            Some(&StudioMcpEndpoint {
                port: 8787,
                token: "tkn-abc".to_string(),
            }),
            false,
        );

        assert!(payload.contains("export STUDIO_MCP_URL=\"http://127.0.0.1:8787/mcp\""));
        assert!(payload.contains("export STUDIO_API_TOKEN=\"tkn-abc\""));
    }

    #[test]
    fn wsl_payload_patches_transient_config_with_claude_shared_credentials() {
        // ah >= 1.7.0 refuses to start claude-provider agents unless
        // providers.claude.shared_credentials_dir is set. Only the launcher's
        // shell knows the WSL $HOME, so the payload patches Studio's OWN
        // transient ah.toml right before `ah start`.
        let payload = wsl_payload_script(
            "/mnt/d/ws",
            "/mnt/c/Users/u/AppData/Local/Temp/skill-studio-ah/abc/claude/ah.toml",
            CodeAssistant::Claude,
            None,
            None,
            None,
            true,
        );

        assert!(payload.contains("[providers.claude]"));
        assert!(payload.contains("shared_credentials_dir"));
        assert!(payload.contains("$HOME/.claude"));
    }

    #[test]
    fn wsl_payload_never_patches_a_user_owned_ah_toml() {
        // A checked-in workspace ah.toml belongs to the user; if it is missing
        // the provider section, ah's own diagnostic must surface untouched.
        let payload = wsl_payload_script(
            "/mnt/d/ws",
            "/mnt/d/ws/ah.toml",
            CodeAssistant::Claude,
            None,
            None,
            None,
            false,
        );

        assert!(!payload.contains("[providers.claude]"));
    }

    #[test]
    fn codex_wsl_payload_never_patches_claude_provider_config() {
        let payload = wsl_payload_script(
            "/mnt/d/ws",
            "/mnt/c/Users/u/AppData/Local/Temp/skill-studio-ah/abc/codex/ah.toml",
            CodeAssistant::Codex,
            None,
            None,
            None,
            true,
        );

        assert!(!payload.contains("[providers.claude]"));
    }

    /// 决议 2026-08-02 D-B1/D-B2/D-B5 — Claude CLI 的自更新只有在宿主 HOME、沙箱之外
    /// 才可能生效(ah 给每个会话指定临时 HOME,更新落进去就随会话删掉),所以 Open 的
    /// payload 必须在 `ah start` 之前调用官方安装器入口 `claude install latest`,
    /// 并且失败不得阻断打开。
    #[test]
    fn wsl_open_payload_refreshes_claude_cli_before_ah_start() {
        let payload = wsl_payload_script(
            "/mnt/d/ws",
            "/mnt/c/Users/u/AppData/Local/Temp/skill-studio-ah/abc/claude/ah.toml",
            CodeAssistant::Claude,
            None,
            None,
            None,
            true,
        );

        let update_index = payload
            .find("claude install latest")
            .expect("Open must call the OFFICIAL installer entry, not a hand-rolled version check");
        let start_index = payload
            .find("start --wait")
            .expect("the Open payload still starts ah");
        assert!(
            update_index < start_index,
            "the refresh must run in the host HOME BEFORE ah start hands claude a throwaway sandbox HOME"
        );
        assert!(
            payload.contains("timeout 300 claude install latest"),
            "the refresh is bounded so a stalled download cannot hang the launch (D-B5)"
        );
        assert!(
            payload.contains("STUDIO_CLAUDE_UPDATE_STAMP"),
            "the 24h throttle stamp gates the refresh so every Open does not re-download (D-B4)"
        );
    }

    /// 决议 2026-08-02 D-B2/D-B3 — attach 连的是已在运行的会话(升级无意义且拖慢),
    /// codex 的分发路径不同(Windows 侧为权威),两者都不得带上这段。
    #[test]
    fn claude_cli_refresh_is_scoped_to_the_claude_open_path() {
        let attach_payload = wsl_attach_payload_script(
            "/mnt/c/Users/u/AppData/Local/Temp/skill-studio-ah/abc/claude/ah.toml",
            "/mnt/d/ws",
            CodeAssistant::Claude,
        );
        assert!(
            !attach_payload.contains("claude install latest"),
            "attach reuses a running session; refreshing there only delays the attach"
        );

        let codex_payload = wsl_payload_script(
            "/mnt/d/ws",
            "/mnt/c/Users/u/AppData/Local/Temp/skill-studio-ah/abc/codex/ah.toml",
            CodeAssistant::Codex,
            None,
            None,
            None,
            true,
        );
        assert!(
            !codex_payload.contains("claude install latest"),
            "codex's distribution is Windows-authoritative and out of this decision's scope"
        );
    }

    #[test]
    fn unix_launcher_patches_transient_config_with_claude_shared_credentials() {
        let script = unix_code_assistant_launcher_script(
            Path::new("/ws"),
            Path::new("/tmp/skill-studio-ah/abc/claude/ah.toml"),
            CodeAssistant::Claude,
            true,
        );

        assert!(script.contains("[providers.claude]"));
        assert!(script.contains("shared_credentials_dir"));
    }

    #[test]
    fn wsl_payload_omits_studio_mcp_env_when_sidecar_unknown() {
        let payload = wsl_payload_script(
            "/mnt/d/ws",
            "/mnt/d/ws/ah.toml",
            CodeAssistant::Claude,
            None,
            None,
            None,
            false,
        );

        assert!(!payload.contains("STUDIO_MCP_URL"));
        assert!(!payload.contains("STUDIO_API_TOKEN"));
    }

    #[test]
    fn codex_master_cmd_rejects_interop_binaries_and_prefers_standalone() {
        let cmd = codex_master_cmd(None, None);
        let standalone = "$STUDIO_AH_HOST_HOME/.codex/packages/standalone/current/bin/codex";
        let standalone_index = cmd
            .find(standalone)
            .expect("codex master should prefer the native standalone install");
        let path_lookup_index = cmd
            .find("command -v codex")
            .expect("codex master should still fall back to PATH lookup");

        assert!(
            standalone_index < path_lookup_index,
            "native standalone install must be checked before hijackable PATH entries"
        );
        assert!(cmd.contains("codex_target=$(readlink -f \"$codex_real\""));
        assert!(cmd.contains("case \"$codex_target\" in /mnt/*)"));
        assert!(cmd.contains("codex resolves to a Windows binary"));
        assert!(cmd.contains("HOME injection"));
        assert!(cmd.contains("scripts/install-claude-code-wsl.ps1"));
    }

    #[test]
    fn moirai_launch_prompt_triggers_intro_skill_without_scripted_answer() {
        assert_eq!(
            MOIRAI_MASTER_REPORT_PROMPT,
            "使用 moirai-intro 介绍你自己。"
        );
        for leaked_answer in ["Clotho", "Lachesis", "Atropos", "standby", "ah 状态"] {
            assert!(
                !MOIRAI_MASTER_REPORT_PROMPT.contains(leaked_answer),
                "launch prompt should trigger the intro skill, not script the answer"
            );
        }
        let intro = std::fs::read_to_string(
            studio_agents_dir()
                .expect("agents dir")
                .join("skills")
                .join("moirai-intro")
                .join("SKILL.md"),
        )
        .expect("moirai-intro skill asset");
        assert!(intro.contains("name: moirai-intro"));
        // surface-neutral (R5.4): the CLI status verb comes from the surface
        // context, the skill itself references it without asserting mechanics
        assert!(intro.contains("ah ps"));
    }

    #[test]
    fn transient_ah_config_starts_moirai_team() {
        let config =
            transient_ah_config_content(CodeAssistant::Claude, None, None).expect("transient claude ah config");

        assert!(config.contains("version = \"1\""));
        assert!(config.contains("[master]"));
        assert!(
            config.contains("window_size = \"follow\""),
            "ah 1.3.0 defaults master tmux sizing to fixed; Studio must opt into follow"
        );
        // IS_SANDBOX (root escape hatch) + the auto-report prompt; NOT
        // skip-permissions (#536: claude's own approval prompt is the human
        // gate), --continue (aborts on a fresh workspace), or /remote-control.
        assert!(config.contains("cmd = \"bash -c "));
        assert!(config.contains("STUDIO_AH_HOST_HOME"));
        assert!(config.contains("export IS_SANDBOX=1"));
        assert!(config.contains("ln -sfn"));
        assert!(config.contains("$HOME/.local/bin/claude"));
        assert!(
            config.contains("$STUDIO_AH_HOST_HOME/.claude.json"),
            "Claude sandbox must reuse the host preseeded trust/onboarding file"
        );
        assert!(config.contains("$HOME/.claude.json"));
        // PR #536: the interactive master deliberately DROPS skip-permissions —
        // claude's own approval prompt is the human gate for a session the user
        // sits in front of (lib.rs claude_master_cmd doc).
        assert!(!config.contains("--dangerously-skip-permissions"));
        assert!(config.contains(MOIRAI_MASTER_REPORT_PROMPT));
        assert!(config.contains("skills = [\"moirai-intro\"]"));
        assert!(!config.contains("--continue"));
        assert!(!config.contains("/remote-control"));
        assert!(!config.contains("[agents.studio]"));
        assert!(config.contains("[agents.clotho]"));
        assert!(config
            .contains("skills = [\"domain-analysis\", \"graph-design\", \"agent-prompt-design\"]"));
        assert!(config.contains("[agents.lachesis]"));
        assert!(config.contains("skills = [\"compile-error-repair\", \"graph-design\"]"));
        assert!(config.contains("[agents.atropos]"));
        assert!(config.contains("skills = [\"eval-judgement\", \"agent-prompt-design\"]"));
        assert_eq!(config.matches("provider = \"claude\"").count(), 4);
        // ah >= 1.3.4 injects worker sandbox env natively; Studio only keeps
        // the master-side escape hatch inside the generated shell command.
        assert!(!config.contains("[env]"));
        assert!(!config.contains("IS_SANDBOX = \"1\""));
        assert!(!config.contains("[sandbox]"));
        assert!(
            !config.contains("additional_ro_binds"),
            "ah 1.3.0 still maps additional_ro_binds to systemd-run --user --scope BindReadOnlyPaths, which WSL rejects"
        );
    }

    #[test]
    fn transient_ah_config_starts_codex_moirai_team() {
        let config =
            transient_ah_config_content(CodeAssistant::Codex, None, None).expect("transient codex ah config");

        assert!(config.contains("version = \"1\""));
        assert!(config.contains("[master]"));
        assert!(config.contains("window_size = \"follow\""));
        assert!(config.contains("cmd = \"bash -c "));
        assert!(config.contains("STUDIO_AH_HOST_HOME"));
        assert!(config.contains("$HOME/.local/bin/codex"));
        assert!(config.contains("$HOME/.codex/auth.json"));
        assert!(config.contains("$HOME/.codex/AGENTS.md"));
        assert!(config.contains("$HOME/.agents/skills"));
        assert!(config.contains("rm -rf \\\"$HOME/.agents/skills\\\""));
        assert!(config.contains("--dangerously-bypass-approvals-and-sandbox"));
        assert!(
            config.contains("--dangerously-bypass-hook-trust"),
            "Codex master must not stop on the hook trust gate"
        );
        assert!(
            config.contains("$HOME/.codex/config.toml"),
            "Codex master must write the sandbox config file Codex actually reads"
        );
        assert!(
            config.contains("codex_trust_header"),
            "Codex master must derive a per-project trust table from the workspace path"
        );
        assert!(
            config.contains("trust_level = \\\"trusted\\\""),
            "Codex master must trust the current sandbox project before launching Codex"
        );
        assert!(
            config.contains("[mcp_servers.codex_apps]"),
            "Codex master must configure the codex_apps MCP startup timeout"
        );
        assert!(
            config.contains("startup_timeout_sec = 120"),
            "Codex master must raise codex_apps MCP startup timeout above Codex's 30s default"
        );
        assert!(config.contains(MOIRAI_MASTER_REPORT_PROMPT));
        assert!(config.contains("skills = [\"moirai-intro\"]"));
        assert!(config.contains("[agents.clotho]"));
        assert!(config
            .contains("skills = [\"domain-analysis\", \"graph-design\", \"agent-prompt-design\"]"));
        assert!(config.contains("[agents.lachesis]"));
        assert!(config.contains("skills = [\"compile-error-repair\", \"graph-design\"]"));
        assert!(config.contains("[agents.atropos]"));
        assert!(config.contains("skills = [\"eval-judgement\", \"agent-prompt-design\"]"));
        assert_eq!(config.matches("provider = \"codex\"").count(), 4);
        assert!(!config.contains("[env]"));
        assert!(!config.contains("IS_SANDBOX = \"1\""));
        assert!(!config.contains("--dangerously-skip-permissions"));
    }

    fn asset_body_without_meta_comments(text: &str) -> String {
        // scaffold words are allowed ONLY in meta-instruction comments (the
        // source-file editing header), never in persona prose (R2.9/R2.10)
        let mut body = String::new();
        let mut rest = text;
        while let Some(start) = rest.find("<!--") {
            body.push_str(&rest[..start]);
            match rest[start..].find("-->") {
                Some(end) => rest = &rest[start + end + 3..],
                None => rest = "",
            }
        }
        body.push_str(rest);
        body
    }

    #[test]
    fn role_assets_keep_persona_free_of_scaffold_terms() {
        let assets_dir = studio_agents_dir().expect("agents dir");
        for role in ["moirai", "clotho", "lachesis", "atropos"] {
            let text = std::fs::read_to_string(assets_dir.join("roles").join(format!("{role}.md")))
                .expect("role asset");
            let body = asset_body_without_meta_comments(&text).to_lowercase();
            for leaked_term in ["ah ask", "copilot", " worker", "master"] {
                assert!(
                    !body.contains(leaked_term),
                    "role {role} persona prose leaks scaffold term `{leaked_term}`"
                );
            }
        }
    }

    #[test]
    fn transient_ah_config_omits_systemd_scope_ro_binds() {
        let config =
            transient_ah_config_content(CodeAssistant::Claude, None, None).expect("transient claude ah config");

        assert!(!config.contains("additional_ro_binds"));
        assert!(!config.contains("BindReadOnlyPaths"));
    }

    #[test]
    fn launchers_reject_ah_before_runtime_inventory_support() {
        let windows_payload = wsl_payload_script(
            "/mnt/d/skill",
            "/mnt/c/tmp/ah.toml",
            CodeAssistant::Claude,
            None,
            Some("/mnt/c/Users/u/.claude"),
            None,
            false,
        );
        assert!(windows_payload.contains("ah_version="));
        assert!(windows_payload.contains("requires ah >= 1.3.4"));

        let unix_payload = unix_code_assistant_launcher_script(
            Path::new("/tmp/skill"),
            Path::new("/tmp/ah.toml"),
            CodeAssistant::Claude,
            false,
        );
        assert!(unix_payload.contains("ah_version="));
        assert!(unix_payload.contains("requires ah >= 1.3.4"));
    }

    // ── studio-ah-state-contract-v1 task 2 (version gate) RED tests ──────────
    //
    // Authored by g1 (泳道1 gatekeeper) test-first: g1-m1 turns these GREEN by
    // adding ONLY the production code named below and must NOT edit this test.
    // Contract seam g1-m1 must implement for `test_version_gate_rejects_below_1_4_0`:
    //
    //   /// The single-source ah version gate. Trims a bare `ah version` string and
    //   /// compares it to the one 1.4.0 floor constant. `Ok(())` = supported;
    //   /// `Err(diagnostic)` = blocked (too old OR unparseable), actionable text.
    //   /// start/attach/status/cleanup AND the events subscription all call THIS.
    //   fn ah_version_gate(version_output: &str) -> Result<(), String>
    //
    // See .kiro/specs/studio-ah-state-contract-v1/tasks.md task 2 (lines 48-55).

    /// Req 1.1/1.6/5.4: the ah runtime floor is 1.4.0. A `< 1.4.0` runtime is
    /// blocked at the single-source gate; because start/attach/status/cleanup AND
    /// the `ah events --format json` subscription all consult that one gate before
    /// acting, a blocked runtime yields no events subscription.
    ///
    /// RED when written: `ah_version_gate` does not exist yet — the only version
    /// check today lives inside the launcher shell templates — so this fails to
    /// COMPILE until g1-m1 adds the Rust gate. Anchored to the task-1 boundary
    /// version fixtures (contract inputs), not to internal state: reverting
    /// g1-m1's comparison logic (e.g. off-by-one at the floor) turns it red again.
    ///
    /// The "no events subscription is spawned" half is the direct consequence of
    /// this gate returning `Err`: `start_code_assistant_status_stream`
    /// (lib.rs:1335) must call `ah_version_gate` before entering its respawn loop.
    /// That wiring is a Req-1.6/5.4 acceptance rollback check (revert the events-
    /// path gate call → an unsupported ah spawns `ah events` again) — a pure unit
    /// test can't observe subprocess non-spawn without a live WSL/ah + Tauri
    /// AppHandle, so the gate's `Err` verdict is the load-bearing unit assertion.
    #[test]
    fn test_version_gate_rejects_below_1_4_0() {
        use ah_contract_fixtures::{
            AH_VERSION_MIN_SUPPORTED, AH_VERSION_SUPPORTED, AH_VERSION_UNSUPPORTED,
        };

        // Below the 1.4.0 floor → blocked with an actionable diagnostic. The
        // "1.3.4\n" fixture keeps its trailing newline so the gate's trim is
        // exercised (Req 1.1/1.6, fail-fast diagnostic Req 1.2/1.7).
        let rejected = ah_version_gate(AH_VERSION_UNSUPPORTED);
        assert!(
            rejected.is_err(),
            "ah 1.3.4 is below the 1.4.0 floor and must be blocked (Req 1.1/5.4)"
        );
        assert!(
            !rejected.unwrap_err().is_empty(),
            "a blocked version must return an actionable diagnostic, not fail silently (Req 1.2/1.7)"
        );

        // The floor itself and newer pass — proves the gate is a real comparison,
        // not a constant-reject that would 'block' events for every version.
        assert!(
            ah_version_gate(AH_VERSION_MIN_SUPPORTED).is_ok(),
            "exactly 1.4.0 is the supported floor and must pass (Req 1.1)"
        );
        assert!(
            ah_version_gate(AH_VERSION_SUPPORTED).is_ok(),
            "1.5.0 is above the floor and must pass"
        );
    }

    /// Req 1.8: the version probe is ONE bare `ah version` command whose output is
    /// trimmed — no `ah --version | awk '{print $2}'` second-token parse path
    /// anywhere. Each generated launcher/attach script is the real artifact the
    /// subprocess runs, so it is the contract boundary this asserts against.
    ///
    /// RED when written: all four templates currently emit
    /// `ah --version 2>/dev/null | awk '{print $2}'` (lib.rs:1760/1842/1909/1966),
    /// so the bare-form and no-`--version`/no-`print $2` assertions fail today and
    /// go green only once g1-m1 rewrites the templates. Reverting that template
    /// change re-reds it (the string is regenerated from the production template).
    #[test]
    fn test_version_parse_uses_bare_ah_version() {
        let scripts = [
            wsl_payload_script(
                "/mnt/d/skill",
                "/mnt/c/tmp/ah.toml",
                CodeAssistant::Claude,
                None,
                Some("/mnt/c/Users/u/.claude"),
                None,
                false,
            ),
            wsl_attach_payload_script("/mnt/c/tmp/ah.toml", "/mnt/d/skill", CodeAssistant::Claude),
            unix_code_assistant_launcher_script(
                Path::new("/tmp/skill"),
                Path::new("/tmp/ah.toml"),
                CodeAssistant::Claude,
                false,
            ),
            unix_code_assistant_attach_launcher_script(
                Path::new("/tmp/skill"),
                Path::new("/tmp/ah.toml"),
                CodeAssistant::Claude,
            ),
        ];

        for script in &scripts {
            assert!(
                script.contains("ah version"),
                "version probe must be the bare `ah version` command (Req 1.8):\n{script}"
            );
            assert!(
                !script.contains("ah --version"),
                "the `ah --version` form must be gone — Req 1.8 probes bare `ah version`:\n{script}"
            );
            assert!(
                !script.contains("print $2"),
                "the awk second-token parse (`print $2`) must be gone (Req 1.8):\n{script}"
            );
        }
    }

    // ── studio-ah-state-contract-v1 task 3 (snapshot identity check) RED tests ──
    //
    // Authored by g1 (泳道1 gatekeeper) test-first: g1-m1 turns these GREEN by
    // adding ONLY the production code named below and must NOT edit this test.
    // Contract seam g1-m1 must implement for both identity tests:
    //
    //   /// Validate that a received ah snapshot belongs to the config Studio
    //   /// actually requested (Req 2.7/4.8). AUTHORITATIVE identity is the
    //   /// snapshot's `state_dir` + session identity
    //   /// (`sessions[].session_id`/`path`/`project_id`); `config_path` is
    //   /// ADVISORY ONLY — it is `null` on a config-less daemon and echoed
    //   /// straight back to the requested path (NF1), so a `config_path` match
    //   /// carries zero discriminating power and must NOT decide identity.
    //   /// Studio independently derives the expected identity from
    //   /// `requested_workspace_dir` (basename ⇒ the platform-neutral
    //   /// `project_id` anchor; the dir itself ⇒ the expected worktree path).
    //   /// ALL path comparison (`state_dir`, `sessions[].path`) is canonicalized
    //   /// across the Windows↔WSL boundary via `windows_path_to_wsl`, never raw
    //   /// string equality. `Ok(())` = identity matches ⇒ snapshot may be
    //   /// trusted; `Err(diagnostic)` = mismatch ⇒ snapshot MUST be discarded
    //   /// with an actionable diagnostic (used for no UI or cleanup decision).
    //   fn verify_snapshot_identity(
    //       snapshot_json: &str,
    //       requested_config_path: &Path,
    //       requested_workspace_dir: &Path,
    //   ) -> Result<(), String>
    //
    // See .kiro/specs/studio-ah-state-contract-v1/tasks.md task 3 (lines 57-64)
    // and requirements.md Req 2.7 / 4.8 / 5.10. The two task-1 identity fixtures
    // (ah_contract_fixtures::IDENTITY_*) are the frozen contract inputs — real ah
    // CLI output shapes (NF1 was CAPTURED verbatim in task 0), not internal state.
    //
    // RED when written: `verify_snapshot_identity` does not exist yet, so the test
    // crate fails to COMPILE until g1-m1 adds the Rust seam (same RED mechanism as
    // task 2's `ah_version_gate`). The two tests are each other's controls — an
    // "always Err" impl reds `test_identity_canonicalizes_windows_wsl_path`, an
    // "always Ok" or `config_path`-only impl reds
    // `test_identity_rejects_config_path_match_state_dir_mismatch` — so no trivial
    // constant implementation can turn the pair GREEN.

    /// Req 5.10(a) / 2.7 / 4.8 — the NF1 echo-through failure form. The fixture's
    /// snapshot echoes the REQUESTED `config_path` (`/tmp/ah-fixture-nf1/ah.toml`)
    /// straight back, yet its authoritative `state_dir`/session identity belongs to
    /// a DIFFERENT live daemon (project `feat-studio-ah-state-contract-impl`). A
    /// `config_path`-only check would wrongly ACCEPT this; the identity check must
    /// DISCARD it with a diagnostic because the authoritative identity does not
    /// match the requested `ah-fixture-nf1` config.
    ///
    /// Anchored to the CAPTURED task-0 contract input (`IDENTITY_NF1_ECHO_MISMATCH`,
    /// `Provenance::Captured`), not to internal state. Rollback self-check: if
    /// g1-m1's comparison regresses to trusting `config_path` (or accepts
    /// unconditionally), the echoed match is accepted and this test reds again.
    #[test]
    fn test_identity_rejects_config_path_match_state_dir_mismatch() {
        use ah_contract_fixtures::IDENTITY_NF1_ECHO_MISMATCH;
        let f = &IDENTITY_NF1_ECHO_MISMATCH;

        // Precondition the fixture guarantees (documents WHY a config_path check is
        // the trap): the snapshot's config_path DOES match the requested path.
        assert!(
            f.snapshot_json.contains(f.requested_config_path),
            "fixture precondition: the NF1 snapshot must echo the requested config_path \
             so this test proves a config_path match is not trusted"
        );

        let verdict = verify_snapshot_identity(
            f.snapshot_json,
            Path::new(f.requested_config_path),
            Path::new(f.requested_workspace_dir),
        );

        assert!(
            verdict.is_err(),
            "NF1 echo: config_path matches but state_dir/session identity is another \
             live daemon — the snapshot MUST be discarded, not accepted (Req 2.7/5.10a)"
        );
        assert!(
            !verdict.unwrap_err().is_empty(),
            "a discarded snapshot must carry an actionable diagnostic, not fail silently (Req 4.8)"
        );
    }

    /// Req 5.10(b) / 2.7 — cross-platform canonical acceptance. A Windows host
    /// requests `C:\Users\dev\myproj` while the WSL-side ah reports the same target
    /// as `/mnt/c/Users/dev/myproj`. Raw string comparison of those two paths FAILS;
    /// the identity check must ACCEPT after canonicalizing across the Windows↔WSL
    /// boundary (and via the platform-neutral `project_id` basename `myproj`).
    ///
    /// Anchored to the `IDENTITY_WINDOWS_WSL_CANONICAL_MATCH` fixture. The assert
    /// below re-proves that raw equality would reject this pair, so an accept can
    /// only come from real canonicalization/project_id matching, never from a raw
    /// string compare. Rollback self-check: revert canonicalization to raw string
    /// path equality (with no project_id anchor) and this accept turns to reject → red.
    #[test]
    fn test_identity_canonicalizes_windows_wsl_path() {
        use ah_contract_fixtures::IDENTITY_WINDOWS_WSL_CANONICAL_MATCH;
        let f = &IDENTITY_WINDOWS_WSL_CANONICAL_MATCH;

        // Precondition: raw string comparison of the requested Windows workspace dir
        // against the WSL snapshot path does NOT match — so acceptance is only
        // possible through cross-platform canonicalization, not raw equality.
        assert!(
            f.snapshot_json.contains("/mnt/c/Users/dev/myproj"),
            "fixture precondition: snapshot carries the /mnt/c WSL form of the request"
        );
        assert_ne!(
            f.requested_workspace_dir, "/mnt/c/Users/dev/myproj",
            "fixture precondition: the C:\\ request differs from the /mnt/c snapshot as raw strings"
        );

        let verdict = verify_snapshot_identity(
            f.snapshot_json,
            Path::new(f.requested_config_path),
            Path::new(f.requested_workspace_dir),
        );

        assert!(
            verdict.is_ok(),
            "C:\\ request vs /mnt/c WSL snapshot for the same canonical target must be \
             accepted after Windows↔WSL canonicalization — raw string compare is forbidden \
             (Req 2.7/5.10b); got diagnostic: {verdict:?}"
        );
    }

    // ── studio-ah-state-contract-v1 tasks 3 (remaining) + 4 RED tests ────────────
    //
    // Authored by g1 (泳道1 gatekeeper) test-first. tasks 3 and 4 are a single batch
    // (tasks.md:57/66 「须与任务 X 同批落地」): task 3's typed parser + snapshot-driven
    // decision plane are useless without task 4's events-primary + sequence arbitration,
    // and shipping task 3 alone would leave `status` as a mid-state decision surface —
    // forbidden by the spec. So both are RED here in one PR; g1-m1 turns them GREEN by
    // adding ONLY the production seams named below and must NOT edit this test file.
    //
    // Contract seams g1-m1 must implement (crate scope; derive PartialEq+Eq+Debug on the
    // enum, Debug is not required on the structs). Field model = design.md:237-273
    // (corrected against real 1.4.0/1.5.0 CLI output per F8), fields listed in
    // tasks.md:60. RED mechanism = the same compile-time E0425/E0412 as task 2's
    // `ah_version_gate` and task 3's `verify_snapshot_identity`: none of these symbols
    // exist yet, so the whole lib-test target fails to COMPILE until g1-m1 adds them.
    //
    //   /// The four-value runtime phase (design.md Data Models). A typed enum, never a
    //   /// stringly value nor a Studio-invented reduction back to a bool (Req 3.8).
    //   enum AhRuntimeState { Active, Inactive, Starting, Degraded }
    //
    //   /// One session inside a parsed snapshot. Identity + cleanup-eligibility fields
    //   /// are consumed directly, never re-derived (Req 2.6/2.7/4.2). `live_agents` is
    //   /// the real field name — NOT `active_agents` (design F8).
    //   struct AhSessionSnapshot {
    //       session_id: String, project_id: String, path: String, status: String,
    //       live_agents: u64, db_tracked_agents: u64,
    //       cleanup_required: bool, safe_to_cleanup: bool,
    //   }
    //
    //   /// A parsed, schema-validated ah v1.4.0+ runtime snapshot (one `status --json`
    //   /// stdout, or one `events --format json` JSONL line). `config_path` is ADVISORY
    //   /// ONLY (Req 2.7). Top-level tmux-health (`master_tmux_alive`/`worker_tmux_alive`)
    //   /// and `config_path` MUST be serde-optional/defaulted so the reduced
    //   /// SEQUENCE_*/daemon_absent frames (which omit them) still parse; the full
    //   /// SNAPSHOT_* fixtures carry them. Per tasks.md:60 the parser must also cover
    //   /// `ahd_alive`/`sequence`/`reason`/`config_path`/`sessions[].session_id/path/
    //   /// project_id` (g1-m1 may add `state_dir`/`agents`/`workspace_path` too).
    //   struct AhRuntimeSnapshot {
    //       schema_version: u64, runtime_state: AhRuntimeState,
    //       active: bool, ahd_alive: bool, sequence: u64,
    //       reason: Option<String>, config_path: Option<String>,
    //       master_tmux_alive: bool, worker_tmux_alive: bool,
    //       sessions: Vec<AhSessionSnapshot>,
    //   }
    //
    //   /// Parse + schema-validate. `Ok` only when `schema_version == 2`; `Err(diag)` on
    //   /// an unknown schema (must NOT default-pass to a healthy read) or invalid JSON
    //   /// (Req 2.4/2.5).
    //   fn parse_ah_runtime_snapshot(snapshot_json: &str) -> Result<AhRuntimeSnapshot, String>
    //
    //   /// Reduce an (identity-checked) typed snapshot to the normal-path lifecycle
    //   /// action, sourcing active / terminal-session state from the snapshot's OWN
    //   /// fields — never from `ah ps` text (`ah_ps_output_has_inventory` /
    //   /// `extract_ah_session_ids`) or tmux probing (task 3: remove ps/tmux from the
    //   /// decision plane). active → AttachExisting; inactive/all-terminal → StartFresh.
    //   /// (starting/degraded phase handling is task 6, out of scope here.)
    //   fn reconcile_snapshot_lifecycle(snapshot: &AhRuntimeSnapshot) -> CodeAssistantLifecycleAction
    //
    //   /// Stream-scoped applied-`sequence` cache (Req 2.1/5.13). `accept` returns true
    //   /// if the snapshot was applied, false if dropped as stale. Within one unchanged
    //   /// stream an older-or-equal `sequence` is dropped; but a `reason:"initial"`
    //   /// baseline, a freshly (re)established subscription, or a changed
    //   /// `sessions[].session_id` UNCONDITIONALLY resets the cache and applies.
    //   struct SequenceArbiter { /* private */ }
    //   impl SequenceArbiter { fn new() -> Self; fn accept(&mut self, snapshot: &AhRuntimeSnapshot) -> bool }
    //
    //   /// Arbitrate the bootstrap read: `status --json` result (Ok=stdout JSON,
    //   /// Err=stderr from a non-zero exit) vs an available `events` snapshot line. When
    //   /// an events snapshot is present it WINS — a `status --json` stderr failure must
    //   /// never be surfaced as the authoritative error while a structured events
    //   /// snapshot is available (Req 2.3/5.11).
    //   fn resolve_bootstrap_snapshot(
    //       status_json_result: Result<&str, &str>,
    //       events_snapshot_json: Option<&str>,
    //   ) -> Result<AhRuntimeSnapshot, String>
    //
    // See tasks.md tasks 3 (lines 57-64) + 4 (lines 66-75), design.md:195-330,
    // requirements.md Req 2.1/2.7/3.5/3.8/5.11/5.13. Every fixture consumed
    // (`ah_contract_fixtures::*`) is a frozen task-1 contract input — real CLI output
    // shapes, not internal state. These tests are NOT self-anchored: reverting g1-m1's
    // parser/decision/arbiter logic reds them again (per-test rollback notes below).

    /// Parse a frozen fixture snapshot under the typed parser, panicking with a clear
    /// message if it fails — every fixture fed here is documented well-formed
    /// schema_version:2, so a parse failure means the parser seam regressed, not bad data.
    fn parse_snapshot_or_panic(json: &str) -> AhRuntimeSnapshot {
        parse_ah_runtime_snapshot(json)
            .expect("frozen schema_version:2 fixture must parse under the typed parser")
    }

    /// Task 3 (tasks.md:57-62) — the typed parser projects `active`, `runtime_state`
    /// (as a typed phase), the session list, and master/worker health straight out of
    /// the structured snapshot, and REJECTS an unsupported schema instead of
    /// default-passing. Anchored to the frozen full-schema fixtures; a parser that
    /// dropped the phase enum, mislabelled `live_agents`, or silently accepted schema 999
    /// reds this.
    #[test]
    fn test_typed_snapshot_parser_projects_phase_sessions_and_health() {
        use ah_contract_fixtures::{
            SNAPSHOT_ACTIVE, SNAPSHOT_DEGRADED, SNAPSHOT_STARTING, SNAPSHOT_TERMINAL_CLOSED,
            SNAPSHOT_UNSUPPORTED_SCHEMA,
        };

        // active — runtime_state=Active, active=true, ahd alive, one live-fleet session,
        // master + worker tmux healthy (health sourced from the snapshot, not a tmux probe).
        let active = parse_snapshot_or_panic(SNAPSHOT_ACTIVE);
        assert_eq!(active.runtime_state, AhRuntimeState::Active);
        assert!(active.active);
        assert!(active.ahd_alive);
        assert!(
            active.master_tmux_alive,
            "master health must come from the snapshot's own field, not list_tmux_sessions"
        );
        assert!(
            active.worker_tmux_alive,
            "worker health must come from the snapshot's own field, not list_tmux_sessions"
        );
        assert_eq!(active.sessions.len(), 1);
        let s = &active.sessions[0];
        assert_eq!(s.session_id, "sess_6ddea78e-0ea9-4f00-9b9a-15226e3cce28");
        assert_eq!(s.project_id, "feat-studio-ah-state-contract-impl");
        assert_eq!(s.status, "ACTIVE");

        // starting — hands-off phase: active=false, and the session is not cleanup-eligible
        // (nothing to clean, must be left alone — Req 3.6, verified downstream by task 6).
        let starting = parse_snapshot_or_panic(SNAPSHOT_STARTING);
        assert_eq!(starting.runtime_state, AhRuntimeState::Starting);
        assert!(!starting.active);
        assert!(!starting.sessions[0].cleanup_required);
        assert!(!starting.sessions[0].safe_to_cleanup);

        // degraded — master tmux dead in the snapshot, one ACTIVE session with
        // live_agents=10 and cleanup_required=true (the cleanup-then-open shape, Req 3.7).
        let degraded = parse_snapshot_or_panic(SNAPSHOT_DEGRADED);
        assert_eq!(degraded.runtime_state, AhRuntimeState::Degraded);
        assert!(!degraded.active);
        assert!(
            !degraded.master_tmux_alive,
            "degraded's dead master tmux must be read from the snapshot, not re-probed"
        );
        let ds = &degraded.sessions[0];
        assert_eq!(ds.status, "ACTIVE");
        assert_eq!(
            ds.live_agents, 10,
            "the real v2 field is live_agents (=10), NOT active_agents (design F8)"
        );
        assert!(ds.cleanup_required);

        // terminal CLOSED — ahd alive, active=false, session terminal ⇒ open-able (Req 3.2).
        let closed = parse_snapshot_or_panic(SNAPSHOT_TERMINAL_CLOSED);
        assert_eq!(closed.runtime_state, AhRuntimeState::Inactive);
        assert!(!closed.active);
        assert!(closed.ahd_alive);
        assert_eq!(closed.sessions[0].status, "CLOSED");

        // unsupported schema — MUST be an Err with a diagnostic, never a silent healthy
        // read that falls back to local probing (Req 2.5). This is the load-bearing
        // fail-closed assertion of the parser.
        let unsupported = parse_ah_runtime_snapshot(SNAPSHOT_UNSUPPORTED_SCHEMA);
        assert!(
            unsupported.is_err(),
            "schema_version:999 must be rejected, not silently accepted as active (Req 2.5)"
        );
        assert!(
            !unsupported.unwrap_err().is_empty(),
            "an unsupported-schema rejection must carry an actionable diagnostic"
        );
    }

    /// 决议 2026-08-02 D-A1/D-A2 — `/exit` 让 CLI 进程退出后,ah 把会话标成终态却不回收
    /// tmux(生产代码里回收 tmux 的唯一位置是 ahd 收到 SIGTERM 时的整体清理),于是
    /// `runtime_state` 落到 `inactive` 而 ahd、tmux server 和那块 remain-on-exit 死窗格
    /// 都还在。此时 UI 若投影成 `inactive`(前端渲染 `Open in CLI`)就是在撒谎,再点 Open
    /// 只会 attach 回那块死窗格。判据取 `ahd_alive` 而非 `sessions[].cleanup_required`:
    /// 后者一旦为真便永远为真(ah 无处清零 `master_pid`),会把 UI 永久钉死。
    #[test]
    fn test_lingering_runtime_is_not_projected_as_openable() {
        use ah_contract_fixtures::{
            SNAPSHOT_DAEMON_ABSENT, SNAPSHOT_INACTIVE, SNAPSHOT_TERMINAL_CLOSED,
        };

        for (name, fixture) in [
            ("SNAPSHOT_TERMINAL_CLOSED", SNAPSHOT_TERMINAL_CLOSED),
            ("SNAPSHOT_INACTIVE", SNAPSHOT_INACTIVE),
        ] {
            let snapshot = parse_snapshot_or_panic(fixture);
            // 前置:fixture 真的是"phase=inactive 且 tmux server 仍在"这一形状——死窗格
            // 活在 server 里,server 还在才谈得上有东西需要收尾。
            assert_eq!(
                snapshot.runtime_state,
                AhRuntimeState::Inactive,
                "{name} precondition: the phase really is inactive"
            );
            assert!(
                snapshot.tmux_server_alive,
                "{name} precondition: the tmux server still holds this runtime"
            );

            let ui = assistant_status_for_snapshot(&snapshot);
            assert_eq!(
                serde_json::to_value(ui).expect("AssistantStatus serializes to its wire tag"),
                serde_json::Value::String("lingering".to_string()),
                "{name}: the tmux server (and its dead pane) was never reaped, so the \
                 UI must keep offering Close instead of claiming the runtime is gone and openable"
            );
        }

        // 对照组:ahd 真的没了,运行时才算被回收,Open 才是诚实的 —— 两个不同结果证明这是
        // 真投影,不是恒返回 `lingering` 的常量。
        let absent = parse_snapshot_or_panic(SNAPSHOT_DAEMON_ABSENT);
        assert!(!absent.ahd_alive, "precondition: the daemon really is gone");
        assert_eq!(
            assistant_status_for_snapshot(&absent),
            AssistantStatus::Inactive,
            "with ahd gone ah's shutdown path already ran kill-server, so Open is honest again"
        );
    }

    /// 2026-08-04 修正 D-A1:`ahd_alive` 不能代表"tmux 还没被回收"。
    ///
    /// 真机取证(本机 WSL,`ah 1.7.0`):Studio 管的 6 份 config 里有 4 份处于
    /// `runtime_state:"inactive"` + `ahd_alive:true` + `tmux_server_alive:false` +
    /// `ahd_has_inventory:false`——机器重启把 tmux 全带走、ahd 又被重新拉起之后的形状。
    /// 旧判据把这 4 份全报成"运行中",面板给出一个 attach 不到任何东西、也无事可关的
    /// Close 控件。而"还有没有东西需要收尾"这件事快照里直接带着:死窗格活在 tmux server
    /// 里,server 没了就什么都没剩下。
    ///
    /// 回滚自检:把判据改回 `snapshot.ahd_alive`,本例立刻红;而上一条
    /// `test_lingering_runtime_is_not_projected_as_openable` 证明 `/exit` 留下死窗格
    /// (server 仍在)的场景没有被这次修正牺牲掉——两条一起才是完整的判据。
    #[test]
    fn test_ahd_alive_without_a_tmux_server_is_not_lingering() {
        use ah_contract_fixtures::SNAPSHOT_AHD_ALIVE_TMUX_GONE;

        let snapshot = parse_snapshot_or_panic(SNAPSHOT_AHD_ALIVE_TMUX_GONE);
        assert_eq!(snapshot.runtime_state, AhRuntimeState::Inactive, "前置:phase 是 inactive");
        assert!(snapshot.ahd_alive, "前置:ahd 确实还活着——这正是旧判据会误判的原因");
        assert!(!snapshot.tmux_server_alive, "前置:tmux server 已经不在了");

        assert_eq!(
            assistant_status_for_snapshot(&snapshot),
            AssistantStatus::Inactive,
            "没有 tmux server 就没有窗格可 attach、也没有东西需要回收,面板不得谎称有 CLI 在跑"
        );
    }

    /// 面板呈现改了判据,**启动前的清理没有跟着改**:游离的 ahd 即使没有 tmux,也该在启动
    /// 新运行时之前被清掉(D-A4「一个 workspace 同一时刻只允许一个运行时」)。那一层宁可
    /// 多清,与"要不要告诉用户有东西在跑"是两个不同的问题。
    ///
    /// 回滚自检:把 `reconcile_snapshot_lifecycle` 也改成看 `tmux_server_alive`,本例
    /// 立刻红——它会退化成 `StartFresh`,把那个游离 daemon 留在原地。
    #[test]
    fn test_stray_daemon_without_tmux_is_still_cleaned_before_starting() {
        use ah_contract_fixtures::SNAPSHOT_AHD_ALIVE_TMUX_GONE;

        let snapshot = parse_snapshot_or_panic(SNAPSHOT_AHD_ALIVE_TMUX_GONE);
        assert_eq!(
            reconcile_snapshot_lifecycle(&snapshot),
            CodeAssistantLifecycleAction::CleanupStale,
            "生命周期这条道仍看 ahd_alive:游离 daemon 必须在启动之前清掉"
        );
    }

    /// 因果验证(AGENTS.md 铁律)——`ah stop` 只是把停止命令送达 ahd:ahd 先回 RPC,再自发
    /// SIGTERM,真正的 `kill-session` / `tmux kill-server` / 删 socket 发生在信号处理路径里。
    /// 所以"命令返回"不能证明运行时已被回收。Close 若在确认之前就对外宣布已清理,面板会在
    /// 残留还在时把控件变回 `Open in CLI`,破坏"控件可开 ⇒ 残留已清"这条不变量
    /// (决议 2026-08-02 D-A1;PM 澄清 2026-08-02:一个 CLI 关闭时就应该把残留清干净)。
    #[test]
    fn test_close_waits_until_the_ah_runtime_is_actually_gone() {
        use ah_contract_fixtures::{SNAPSHOT_DAEMON_ABSENT, SNAPSHOT_TERMINAL_CLOSED};

        let lingering = parse_snapshot_or_panic(SNAPSHOT_TERMINAL_CLOSED);
        assert!(lingering.ahd_alive, "前置:这一帧的 ahd 仍在应答");

        // ahd 还在应答的那几轮都不算数,直到探测不到它才算确认。
        let mut probed = 0;
        let confirmed = wait_until_ah_runtime_gone(
            |_| {
                probed += 1;
                (probed < 3).then(|| lingering.clone())
            },
            5,
        );
        assert!(confirmed, "ahd 消失之后必须确认成功");
        assert_eq!(
            probed, 3,
            "确认之前每一轮都要重新探测,不能只读第一帧就下结论"
        );

        // 快照自报 ahd 不在,同样算确认(读得到帧但 ahd_alive=false)。
        let absent = parse_snapshot_or_panic(SNAPSHOT_DAEMON_ABSENT);
        assert!(!absent.ahd_alive, "前置:这一帧自报 ahd 不在");
        assert!(
            wait_until_ah_runtime_gone(|_| Some(absent.clone()), 1),
            "快照自报 ahd 不在时即可确认,不必等到探测失败"
        );

        // 卡住不退的 ahd:用满上限仍未确认,必须如实返回 false,不能假装已经清干净。
        let mut attempts = 0;
        let never = wait_until_ah_runtime_gone(
            |_| {
                attempts += 1;
                Some(lingering.clone())
            },
            4,
        );
        assert!(!never, "ahd 没退就不能宣布已清理");
        assert_eq!(attempts, 4, "上限必须被真正用满,而不是提前放弃");
    }

    /// Task 3 (tasks.md:63) — the normal decision plane consumes a TYPED snapshot, not
    /// `ah ps` text. `reconcile_snapshot_lifecycle` takes `&AhRuntimeSnapshot`, so it
    /// structurally cannot reach `ah_ps_output_has_inventory` / `extract_ah_session_ids`
    /// or tmux probing; the two differing outcomes prove it is a real projection of the
    /// snapshot's `active`/session-terminal state, not a constant. (The full removal of
    /// the ps/tmux path from `inspect_ah_runtime` is the gatekeeper's diff-audit item;
    /// this test pins the new snapshot-driven seam.)
    #[test]
    fn test_decision_plane_consumes_typed_snapshot_not_ps_text() {
        use ah_contract_fixtures::{SNAPSHOT_ACTIVE, SNAPSHOT_TERMINAL_CLOSED};

        let active = parse_snapshot_or_panic(SNAPSHOT_ACTIVE);
        assert_eq!(
            reconcile_snapshot_lifecycle(&active),
            CodeAssistantLifecycleAction::AttachExisting,
            "an active snapshot attaches — decided from runtime_state/active, not ps inventory"
        );

        // 会话终态但 ahd 还活着 ⇒ 运行时(tmux + 死窗格)没被回收,这是残留而不是"干净的空位":
        // 用户裁决 2026-08-02(第二轮)——启动任何 CLI 之前必须把全部残留清干净,所以它先清后启,
        // 不是直接 StartFresh。
        let closed = parse_snapshot_or_panic(SNAPSHOT_TERMINAL_CLOSED);
        assert!(closed.ahd_alive, "前置:这一帧的 ahd 仍在,残留未被回收");
        assert_eq!(
            reconcile_snapshot_lifecycle(&closed),
            CodeAssistantLifecycleAction::CleanupStale,
            "a lingering runtime is reaped before starting — decided from the snapshot itself, \
             not from re-derived `ah ps` inventory"
        );

        // Control: the two outcomes differ, so this is a genuine projection of snapshot
        // state and not a constant that would 'pass' for any input.
        assert_ne!(
            reconcile_snapshot_lifecycle(&active),
            reconcile_snapshot_lifecycle(&closed)
        );
    }

    /// Task 4 (tasks.md:67, Req 2.1/5.13) — a `reason:"initial"`/`sequence:1` frame that
    /// arrives AFTER the stream advanced past 1 triggers an UNCONDITIONAL reset and is
    /// applied, in both the same-session and changed-session cases. A naive global-max
    /// guard (1 ≤ 3 ⇒ drop) would pin the UI on the stale state forever; asserting the
    /// reset frame applies reds that naive implementation. Its control is
    /// `test_sequence_guard_within_stream` (a genuinely-older frame is still dropped).
    #[test]
    fn test_sequence_reset_on_reason_initial() {
        use ah_contract_fixtures::{
            SEQUENCE_RESET_FRAME_NEW_SESSION, SEQUENCE_RESET_FRAME_SAME_SESSION,
            SEQUENCE_STREAM_FRAMES,
        };

        // ── Branch 1: same-session reason:"initial" reset ──
        // Advance one stream 1→2→3; each strictly-newer in-stream frame applies.
        let mut arb = SequenceArbiter::new();
        for (i, &frame) in SEQUENCE_STREAM_FRAMES.iter().enumerate() {
            assert!(
                arb.accept(&parse_snapshot_or_panic(frame)),
                "in-stream frame #{} (sequence {}) is strictly newer and must apply",
                i + 1,
                i + 1
            );
        }
        // Fresh baseline: sequence:1 / reason:"initial", SAME session_id, but a genuinely
        // newer state (the stack has CLOSED). Must reset-and-apply, not be dropped.
        let reset_same = parse_snapshot_or_panic(SEQUENCE_RESET_FRAME_SAME_SESSION);
        assert_eq!(
            reset_same.runtime_state,
            AhRuntimeState::Inactive,
            "fixture precondition: the same-session reset frame carries the newer CLOSED state"
        );
        assert!(
            arb.accept(&reset_same),
            "reason:\"initial\"/sequence:1 after the stream advanced past 1 must reset-and-apply, \
             NOT be dropped by the older-or-equal guard (Req 2.1/5.13)"
        );

        // ── Branch 2: changed sessions[].session_id reset ──
        // NOTE (fixture gap, flagged not self-fixed): SEQUENCE_RESET_FRAME_NEW_SESSION
        // carries a changed session_id AND reason:"initial"/sequence:1 together, so this
        // branch exercises the changed-session-id reset trigger but does not ISOLATE it
        // from the reason:"initial" trigger — both fire. A fixture with a changed
        // session_id under a NON-initial reason would isolate it; none exists, and adding
        // one is task-1 scope (raised to master via .lane-question, not self-added here).
        let mut arb2 = SequenceArbiter::new();
        for &frame in SEQUENCE_STREAM_FRAMES {
            assert!(arb2.accept(&parse_snapshot_or_panic(frame)));
        }
        let reset_new = parse_snapshot_or_panic(SEQUENCE_RESET_FRAME_NEW_SESSION);
        assert!(
            arb2.accept(&reset_new),
            "a sequence:1 frame carrying a changed sessions[].session_id is an independent \
             unconditional-reset trigger and must apply (Req 2.1/5.13)"
        );
    }

    /// Task 4 (tasks.md:67, Req 5.13 second half) — WITHIN one unchanged stream, a
    /// genuinely-older `sequence` is still dropped. This is the control that keeps
    /// `test_sequence_reset_on_reason_initial` honest: the reset there is lifted ONLY by
    /// a reset trigger, not by weakening the monotonic guard into accept-everything.
    #[test]
    fn test_sequence_guard_within_stream() {
        use ah_contract_fixtures::SEQUENCE_STREAM_FRAMES;

        // Advance the stream 1→2→3.
        let mut arb = SequenceArbiter::new();
        for &frame in SEQUENCE_STREAM_FRAMES {
            assert!(arb.accept(&parse_snapshot_or_panic(frame)));
        }

        // Replay frame #2 (sequence:2, reason:"tmux_changed" — NOT a reset, SAME session):
        // a genuinely-older in-stream frame. Applied cache is at 3 with no reset trigger,
        // so the monotonic guard MUST drop it.
        let stale = parse_snapshot_or_panic(SEQUENCE_STREAM_FRAMES[1]);
        assert_eq!(stale.sequence, 2);
        assert_ne!(
            stale.reason.as_deref(),
            Some("initial"),
            "fixture precondition: the stale replay frame is not an initial reset"
        );
        assert!(
            !arb.accept(&stale),
            "an older sequence within the same unchanged stream must be dropped, not applied \
             (Req 5.13); only a reset trigger (initial / new subscription / changed session) \
             lifts the monotonic guard"
        );
    }

    /// Task 4 (tasks.md:67, Req 5.11) — when `ah status --json` fails with a non-zero exit
    /// and unstructured stderr while an `events` subscription yields a structured
    /// `daemon_absent` snapshot, the decision follows the events snapshot, NOT the status
    /// stderr text. The primary case reds a "status-stderr-as-authoritative-error"
    /// implementation (it would return Err ⇒ the `.expect` fails); the control case reds a
    /// "hardcoded daemon_absent constant" implementation (it would ignore the real events
    /// content ⇒ ahd_alive:true assertion fails).
    #[test]
    fn test_daemon_absent_prefers_events_over_status_stderr() {
        use ah_contract_fixtures::{SNAPSHOT_DAEMON_ABSENT, SNAPSHOT_INACTIVE};

        // Real daemon-absent shape (task0 §2b): `ah status --json` exits non-zero with a
        // human-readable stderr and NO JSON; `ah events --format json` yields the
        // structured daemon_absent snapshot. Studio must decide off the events snapshot.
        let status_failure: Result<&str, &str> =
            Err("error: ahd is not running for this config (no daemon)\n");

        let resolved = resolve_bootstrap_snapshot(status_failure, Some(SNAPSHOT_DAEMON_ABSENT));
        let snap = resolved.expect(
            "an available structured daemon_absent events snapshot must win over the status \
             stderr — the stderr must NOT be surfaced as the authoritative error (Req 5.11)",
        );
        assert!(!snap.ahd_alive, "daemon_absent: ahd is not alive");
        assert!(
            !snap.active,
            "daemon_absent resolves to inactive-startable, never an error state (Req 2.3)"
        );
        assert_eq!(snap.runtime_state, AhRuntimeState::Inactive);
        assert!(snap.sessions.is_empty());

        // Control: the resolver forwards the ACTUAL events snapshot content, not a
        // hardcoded daemon_absent. Pair the same status failure with an ahd-alive/inactive
        // events snapshot; the resolved state must reflect ahd_alive:true.
        let status_failure_2: Result<&str, &str> = Err("error: ahd is not running\n");
        let resolved_alive = resolve_bootstrap_snapshot(status_failure_2, Some(SNAPSHOT_INACTIVE))
            .expect("an available events snapshot must resolve, not error on the status stderr");
        assert!(
            resolved_alive.ahd_alive,
            "the resolver must return the events snapshot's real content (ahd_alive:true here), \
             proving it is not a constant daemon_absent"
        );
    }

    // ── studio-ah-state-contract-v1 task 6 (Open/Attach redo: starting/degraded) RED ──
    //
    // Authored by g1 (泳道1 gatekeeper) test-first per the lane's TDD contract: g1-m1
    // (antigravity) turns these GREEN by reworking the Open/Attach decision to cover the
    // `starting`/`degraded` phases, and MUST NOT edit this test file. Anchored to the TYPED
    // decision plane (`reconcile_snapshot_lifecycle`, the task-3/4 seam that
    // `test_decision_plane_consumes_typed_snapshot_not_ps_text` already exercises) plus a
    // new phase→UI-status projection seam — never to a `starting`/`degraded` internal flag.
    //
    // The gap these pin (current production, lib.rs:3252-3258): `reconcile_snapshot_lifecycle`
    // decides on `active` ALONE, so EVERY non-active phase collapses to `StartFresh`. That is
    // the exact bug — `starting` would fire a duplicate `ah start` (Req 3.6 forbids it) and
    // `degraded` would skip the cleanup-then-open path (Req 3.7). These tests fail until g1-m1
    // teaches the decision plane the two phases.
    //
    // One new production seam g1-m1 must add (crate scope, PURE — no subprocess, no live
    // fleet), the compile-time RED (E0425) mechanism used by tasks 2/3/4/8:
    //
    //   /// SSOT phase→UI-status projection (tasks.md:90, design.md:132-133, Req 5.6/6.1).
    //   /// Maps ah's `runtime_state` phase to the per-assistant `AssistantStatus` the
    //   /// frontend renders: Active→Active, Inactive→Inactive, Starting→Starting,
    //   /// Degraded→Degraded. `Error` is produced upstream (parse / identity failure),
    //   /// never from a runtime_state value. This is the single mapping every UI surface
    //   /// projects — task 8's payload and task 9's button states layer on top of it.
    //   fn assistant_status_for_runtime_state(state: AhRuntimeState) -> AssistantStatus

    /// Req 5.6 / 3.6 — a `starting` runtime is HANDS-OFF: Studio runs no cleanup, starts no
    /// duplicate runtime, raises no error, and the UI shows a distinct `starting` state (not
    /// error, not a stale/degraded projection). Req 3.6 keeps Open/Attach/Close all disabled
    /// while starting ("no action taken"), so the decision for a starting snapshot must be
    /// NONE of the three lifecycle actions — start, attach, or cleanup. Anchored to the typed
    /// decision plane + the phase→status wire projection, both fed the frozen task-1
    /// `SNAPSHOT_STARTING` fixture.
    /// Rollback self-check: revert g1-m1's starting branch so `reconcile_snapshot_lifecycle`
    /// falls back to the `active`-only rule → starting decides `StartFresh` → the "no
    /// duplicate start" assertion reds; regress the projection to active/inactive-only → the
    /// `"starting"` wire assertion reds. Not self-anchored: it reads the same frozen fixture
    /// the parser test consumes and asserts on the decision/wire outputs, not on itself.
    #[test]
    fn test_starting_is_hands_off() {
        use ah_contract_fixtures::SNAPSHOT_STARTING;

        let starting = parse_snapshot_or_panic(SNAPSHOT_STARTING);
        // Precondition: the fixture really is the starting phase (Req 3.6 input shape).
        assert_eq!(starting.runtime_state, AhRuntimeState::Starting);

        // Hands-off decision: no duplicate start, no cleanup, and no attach either — Req 3.6
        // keeps every lifecycle control disabled while startup is in progress ("no action
        // taken"), so a starting snapshot must map to a distinct no-action outcome, i.e. none
        // of the three existing lifecycle actions.
        let action = reconcile_snapshot_lifecycle(&starting);
        assert_ne!(
            action,
            CodeAssistantLifecycleAction::StartFresh,
            "starting must NOT start a duplicate runtime (Req 3.6: 'shall not start a duplicate')"
        );
        assert_ne!(
            action,
            CodeAssistantLifecycleAction::CleanupStale,
            "starting must NOT run cleanup — startup is in progress and must be left alone (Req 3.6)"
        );
        assert_ne!(
            action,
            CodeAssistantLifecycleAction::AttachExisting,
            "starting takes NO action (Req 3.6 keeps Open/Attach/Close disabled), so it must not attach either"
        );

        // UI projection: a starting phase shows a distinct `starting` state on the wire —
        // never `error`, never a stale `degraded` projection (Req 5.6). Asserted on the
        // serialized wire tag, so a Rust rename cannot dodge the frontend contract.
        let ui = assistant_status_for_snapshot(&starting);
        assert_eq!(
            serde_json::to_value(ui).expect("AssistantStatus serializes to its wire tag"),
            serde_json::Value::String("starting".to_string()),
            "starting phase projects to the `starting` wire status the frontend renders (Req 5.6)"
        );
        assert_ne!(
            ui,
            AssistantStatus::Error,
            "starting is a real phase, not an error state (Req 5.6/3.6: 'shall not report an error')"
        );
        assert_ne!(
            ui,
            AssistantStatus::Degraded,
            "starting must not be projected as a stale degraded state (Req 5.6)"
        );
    }

    /// Req 5.7 / 3.7 — a `degraded` runtime with `cleanup_required=true` on a session must
    /// leave the user a WORKING Open path (cleanup-then-start), never a fully-disabled button
    /// set. The typed decision for such a snapshot is `CleanupStale`, which the Open flow
    /// (`prepare_code_assistant_open`, lib.rs:2591-2593) resolves to cleanup + a fresh start —
    /// so Open stays usable. Anchored to the typed decision plane fed the frozen task-1
    /// `SNAPSHOT_DEGRADED` fixture (recorded shape: session ACTIVE, master tmux dead,
    /// cleanup_required=true).
    /// Rollback self-check: revert g1-m1's degraded branch so `reconcile_snapshot_lifecycle`
    /// falls back to the `active`-only rule → degraded decides `StartFresh` (skips cleanup) →
    /// the `CleanupStale` assertion reds. Control: active still attaches and terminal still
    /// starts fresh (test_decision_plane_consumes_typed_snapshot_not_ps_text), so this is a
    /// real projection of the degraded phase, not a constant.
    #[test]
    fn test_degraded_exposes_working_open() {
        use ah_contract_fixtures::SNAPSHOT_DEGRADED;

        let degraded = parse_snapshot_or_panic(SNAPSHOT_DEGRADED);
        // Preconditions: this fixture is the Req 5.7 degraded + cleanup_required shape.
        assert_eq!(degraded.runtime_state, AhRuntimeState::Degraded);
        assert!(
            degraded.sessions.iter().any(|s| s.cleanup_required),
            "Req 5.7 requires cleanup_required=true on at least one session to drive cleanup-then-open"
        );

        // Working Open path: degraded decides CleanupStale, which the Open flow turns into
        // cleanup + a fresh start (lib.rs:2591-2593). Open is therefore available — not the
        // three-buttons-dark deadlock the prior spec wording produced (Req 3.7/5.7).
        assert_eq!(
            reconcile_snapshot_lifecycle(&degraded),
            CodeAssistantLifecycleAction::CleanupStale,
            "degraded must expose a working cleanup-then-start Open path, not zero actions (Req 3.7/5.7)"
        );
    }

    /// Task 6.1 (task6.1-seam-decision-2026-07-10.md, master 裁决 2) — the Open decision the
    /// LIVE `prepare_code_assistant_open` entry consumes must be driven by the typed
    /// `AhRuntimeSnapshot` phase, not the old boolean `ah ps`/tmux plane. `decide_code_assistant_open_v2`
    /// takes `Option<&AhRuntimeSnapshot>` (requested) + `&[AhRuntimeSnapshot]` (others) and returns the
    /// existing `CodeAssistantOpenDecision` enum, so its return value IS the contract boundary
    /// `prepare_code_assistant_open`'s `match` branches on (attach / start / cleanup / hands-off).
    ///
    /// COMPILE-TIME RED (expected, master 裁决 4): `decide_code_assistant_open_v2` and the new
    /// `CodeAssistantOpenDecision::HandsOff` variant do not exist yet, so the whole `cargo test --lib`
    /// fails to COMPILE until g2 implements them — the standard TDD intermediate state, not a defect.
    ///
    /// 用户裁决 2026-08-02(第二轮):**一个 workspace 同一时刻只允许一个 CLI 运行时存在**,
    /// **启动任何 CLI 之前必须把全部残留清干净**。"某个助手有残留 + 另一个正在跑"这个组合
    /// 本身就是不允许的状态——它之所以会出现,正是因为上一次启动没清残留;把启动前清残留做实,
    /// 这个组合就不再产生。
    ///
    /// 三条边界各自独立:
    /// - 请求方自己有残留 → 先清后启(否则 attach/start 会落到上一轮的死窗格);
    /// - 另一个助手有残留 → 同样先清后启(否则启动完就凑成那个不允许的组合);
    /// - 另一个助手**真的在跑** → 拒绝,让用户先关它。只允许一个在跑,而"清残留"不该被扩大成
    ///   "替用户关掉正在干活的 CLI"。
    #[test]
    fn test_open_cleans_every_residual_runtime_before_starting() {
        use ah_contract_fixtures::{
            SNAPSHOT_ACTIVE_CODEX, SNAPSHOT_DAEMON_ABSENT, SNAPSHOT_TERMINAL_CLOSED,
        };

        let lingering = parse_snapshot_or_panic(SNAPSHOT_TERMINAL_CLOSED);
        let reaped = parse_snapshot_or_panic(SNAPSHOT_DAEMON_ABSENT);
        let other_lingering = [parse_snapshot_or_panic(SNAPSHOT_TERMINAL_CLOSED)];
        let other_running = [parse_snapshot_or_panic(SNAPSHOT_ACTIVE_CODEX)];

        // 前置:两帧确实是"残留"与"已回收"的对照。
        assert_eq!(lingering.runtime_state, AhRuntimeState::Inactive);
        assert!(lingering.ahd_alive, "残留的前提:ahd 还在");
        assert_eq!(reaped.runtime_state, AhRuntimeState::Inactive);
        assert!(!reaped.ahd_alive, "已回收的前提:ahd 不在了");
        assert_eq!(other_running[0].runtime_state, AhRuntimeState::Active);

        assert_eq!(
            decide_code_assistant_open_v2(Some(&lingering), &[]),
            CodeAssistantOpenDecision::CleanupStale,
            "请求方自己的残留必须先清,否则启动/attach 会落到上一轮的死窗格"
        );
        assert_eq!(
            decide_code_assistant_open_v2(Some(&reaped), &other_lingering),
            CodeAssistantOpenDecision::CleanupStale,
            "另一个助手的残留同样要先清,否则本次启动完就凑成「残留 + 在跑」这个不允许的组合"
        );
        assert_eq!(
            decide_code_assistant_open_v2(Some(&lingering), &other_running),
            CodeAssistantOpenDecision::RejectOtherActive,
            "另一个助手真的在跑时只拒绝,不替用户关掉它——只允许一个在跑"
        );

        // 对照组:两边都确实被回收过才直接启动,证明这不是恒返回 CleanupStale 的常量。
        assert_eq!(
            decide_code_assistant_open_v2(Some(&reaped), &[]),
            CodeAssistantOpenDecision::StartFresh,
            "没有任何残留时不该凭空跑一次清理"
        );
    }

    /// This test pins the single-runtime (no others) phase→decision map. The starting branch mirrors
    /// `test_starting_is_hands_off`'s style: a starting REQUESTED runtime must resolve to a distinct
    /// no-action outcome (`HandsOff`), never a duplicate start / cleanup / attach / reject. The `assert_ne!`
    /// controls prove the four phases yield genuinely different decisions (real projection, not a constant).
    #[test]
    fn test_open_decision_v2_maps_requested_phase() {
        use ah_contract_fixtures::{
            SNAPSHOT_ACTIVE, SNAPSHOT_DAEMON_ABSENT, SNAPSHOT_DEGRADED, SNAPSHOT_STARTING,
        };

        let active = parse_snapshot_or_panic(SNAPSHOT_ACTIVE);
        // 真 inactive = ahd 也不在了(运行时确实被回收过)。`SNAPSHOT_INACTIVE` 的 ahd 还活着,
        // 那是残留(lingering),归 test_open_cleans_every_residual_runtime_before_starting 覆盖。
        let inactive = parse_snapshot_or_panic(SNAPSHOT_DAEMON_ABSENT);
        let degraded = parse_snapshot_or_panic(SNAPSHOT_DEGRADED);
        let starting = parse_snapshot_or_panic(SNAPSHOT_STARTING);

        // Fixture preconditions: each frozen snapshot really carries the phase under test.
        assert_eq!(active.runtime_state, AhRuntimeState::Active);
        assert_eq!(inactive.runtime_state, AhRuntimeState::Inactive);
        assert!(!inactive.ahd_alive, "真 inactive 的前提:ahd 已经不在了");
        assert_eq!(degraded.runtime_state, AhRuntimeState::Degraded);
        assert_eq!(starting.runtime_state, AhRuntimeState::Starting);

        // Active → attach the existing runtime.
        assert_eq!(
            decide_code_assistant_open_v2(Some(&active), &[]),
            CodeAssistantOpenDecision::AttachRequested,
            "active requested runtime attaches — decided from runtime_state, not `ah ps` inventory"
        );
        // Inactive (ahd gone, nothing left to reap) → start fresh.
        assert_eq!(
            decide_code_assistant_open_v2(Some(&inactive), &[]),
            CodeAssistantOpenDecision::StartFresh,
            "inactive requested runtime starts fresh — sessions are terminal (Req 3.5)"
        );
        // Degraded (cleanup_required) → cleanup-then-start; Open stays usable (Req 3.7/5.7).
        assert_eq!(
            decide_code_assistant_open_v2(Some(&degraded), &[]),
            CodeAssistantOpenDecision::CleanupStale,
            "degraded requested runtime cleans up then starts — Open must stay usable, not three-buttons-dark (Req 3.7/5.7)"
        );

        // Starting → hands-off: startup is in progress, so Open takes NO lifecycle action —
        // not a duplicate start, not cleanup, not attach, not a reject (Req 3.6). A starting
        // phase must map to a distinct no-action outcome, i.e. none of the four acting decisions.
        let starting_decision = decide_code_assistant_open_v2(Some(&starting), &[]);
        assert_eq!(
            starting_decision,
            CodeAssistantOpenDecision::HandsOff,
            "starting requested runtime is hands-off — Open takes no action while startup is in progress (Req 3.6)"
        );
        assert_ne!(
            starting_decision,
            CodeAssistantOpenDecision::StartFresh,
            "starting must NOT start a duplicate runtime (Req 3.6: 'shall not start a duplicate')"
        );
        assert_ne!(
            starting_decision,
            CodeAssistantOpenDecision::CleanupStale,
            "starting must NOT run cleanup — startup is in progress and must be left alone (Req 3.6)"
        );
        assert_ne!(
            starting_decision,
            CodeAssistantOpenDecision::AttachRequested,
            "starting takes no action, so Open must not attach a not-yet-ready runtime (Req 3.6)"
        );
        assert_ne!(
            starting_decision,
            CodeAssistantOpenDecision::RejectOtherActive,
            "starting is about the requested runtime's own phase, not a cross-assistant rejection (Req 3.6)"
        );

        // Control: the four phases yield four genuinely different decisions — this is a real
        // projection of the snapshot phase, not a constant that would 'pass' for any input.
        assert_ne!(
            decide_code_assistant_open_v2(Some(&active), &[]),
            decide_code_assistant_open_v2(Some(&inactive), &[])
        );
        assert_ne!(
            decide_code_assistant_open_v2(Some(&inactive), &[]),
            decide_code_assistant_open_v2(Some(&degraded), &[])
        );
        assert_ne!(
            decide_code_assistant_open_v2(Some(&degraded), &[]),
            starting_decision
        );
    }

    /// Task 6.1 (master 裁决 2, cross-assistant arbitration) — the new decision function copies
    /// `decide_code_assistant_open`'s single-ahd-per-workspace arbitration over `others`, swapping the
    /// "is the other active" judgment from the boolean plane to the typed snapshot's `runtime_state`.
    /// Anchored to the same behaviors the old `open_decision_enforces_single_ahd_per_workspace` pins,
    /// so the cutover preserves the guardrail rather than silently dropping it.
    ///
    /// COMPILE-TIME RED (expected): references the not-yet-built `decide_code_assistant_open_v2`.
    ///
    /// Scope (test-author honesty, per decision doc §四): master fixed the inactive+other-active and
    /// active+other-active cases; the `Starting` requested + other-active combination is left to g2
    /// (hands-off vs. copied reject has genuine tension master did not settle) and is intentionally
    /// NOT asserted here.
    #[test]
    fn test_open_decision_v2_arbitrates_other_active_runtime() {
        use ah_contract_fixtures::{
            SNAPSHOT_ACTIVE, SNAPSHOT_ACTIVE_CODEX, SNAPSHOT_DAEMON_ABSENT,
        };

        let requested_active = parse_snapshot_or_panic(SNAPSHOT_ACTIVE);
        // 请求方没有任何运行时(ahd 也不在),排除"请求方自己也有残留"这个变量,
        // 这里单测的就是「另一个真的在跑」这一条仲裁。
        let requested_inactive = parse_snapshot_or_panic(SNAPSHOT_DAEMON_ABSENT);
        // A DIFFERENT assistant's runtime that is active (distinct workspace/session_id).
        let other_active = [parse_snapshot_or_panic(SNAPSHOT_ACTIVE_CODEX)];
        assert_eq!(other_active[0].runtime_state, AhRuntimeState::Active);

        // Inactive requested but another assistant is already active → reject: one ahd per workspace.
        assert_eq!(
            decide_code_assistant_open_v2(Some(&requested_inactive), &other_active),
            CodeAssistantOpenDecision::RejectOtherActive,
            "another active assistant blocks starting a second one (single-ahd guard, copied from decide_code_assistant_open)"
        );
        // Both requested and another are active → cleanup the duplicate stack (matches old
        // decide_code_assistant_open(Some(active), &[active]) == CleanupStale).
        assert_eq!(
            decide_code_assistant_open_v2(Some(&requested_active), &other_active),
            CodeAssistantOpenDecision::CleanupStale,
            "two active runtimes for one workspace resolve to CleanupStale, same as the old boolean-plane arbitration"
        );
        // No requested runtime and nothing else active → start fresh (unwrap default preserved).
        assert_eq!(
            decide_code_assistant_open_v2(None, &[]),
            CodeAssistantOpenDecision::StartFresh,
            "no requested snapshot and no active others starts fresh (unwrap_or(StartFresh) preserved)"
        );
    }

    #[test]
    fn claude_wsl_payload_links_windows_credentials() {
        // The Windows .credentials.json is the single auth file; WSL root links
        // to it instead of copying it or requiring a second WSL login.
        let payload = wsl_payload_script(
            "/mnt/d/skill",
            "/mnt/c/tmp/ah.toml",
            CodeAssistant::Claude,
            None,
            Some("/mnt/c/Users/u/.claude"),
            None,
            false,
        );
        assert!(payload.contains("WIN_CLAUDE_HOME='/mnt/c/Users/u/.claude'"));
        assert!(payload.contains("ln -sfn \"$WIN_CLAUDE_HOME/.credentials.json\""));
        assert!(payload.contains("Windows Claude login was not found"));
        assert!(payload.contains(".claude/.credentials.json"));
        assert!(!payload.contains("CLAUDE_CODE_OAUTH_TOKEN"));
        assert!(!payload.contains("setup-token"));
        assert!(!payload.contains("claude /login"));

        // Codex has its own auth sync (Windows auth.json copy); the Claude
        // bridge must not leak into its payload.
        let codex_payload = wsl_payload_script(
            "/mnt/d/skill",
            "/mnt/c/tmp/ah.toml",
            CodeAssistant::Codex,
            Some("/mnt/c/Users/u/.codex"),
            None,
            None,
            false,
        );
        assert!(!codex_payload.contains("WIN_CLAUDE_HOME"));
        assert!(codex_payload.contains("auth.json"));
    }

    #[test]
    fn generated_ah_config_prepares_moirai_workspace_files() {
        let root = temp_path("moirai-workspace");
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();

        let config = ah_config_for_workspace(&root, CodeAssistant::Claude, None, None)
            .expect("generated transient ah config");

        assert!(config.is_file());
        let master_rules = root.join(".ah").join("rules").join("master.md");
        let clotho_rules = root.join(".ah").join("rules").join("clotho.md");
        let domain_skill = root
            .join(".ah")
            .join("skills")
            .join("domain-analysis")
            .join("SKILL.md");
        let eval_skill = root
            .join(".ah")
            .join("skills")
            .join("eval-judgement")
            .join("SKILL.md");
        let intro_skill = root
            .join(".ah")
            .join("skills")
            .join("moirai-intro")
            .join("SKILL.md");

        assert!(master_rules.is_file());
        assert!(clotho_rules.is_file());
        assert!(domain_skill.is_file());
        assert!(eval_skill.is_file());
        assert!(intro_skill.is_file());
        let master = std::fs::read_to_string(master_rules).unwrap();
        assert!(master.contains("studio-ah-managed hash:"));
        assert!(master.contains("MoirAI"));
        let domain = std::fs::read_to_string(domain_skill).unwrap();
        assert!(domain.starts_with("---\n"));
        assert!(domain.contains("name: domain-analysis"));
        assert!(domain.contains("studio-ah-managed hash:"));
        let eval = std::fs::read_to_string(eval_skill).unwrap();
        assert!(eval.contains("name: eval-judgement"));
        let intro = std::fs::read_to_string(intro_skill).unwrap();
        assert!(intro.contains("name: moirai-intro"));
        assert!(intro.contains("ah ps"));
        // knowledge base materializes alongside rules and skills
        let kb_hub = root.join(".ah").join("knowledge").join("KB-00-hub.md");
        assert!(kb_hub.is_file());
        // rules carry the R1.4 on-disk assembly markers
        let clotho = std::fs::read_to_string(clotho_rules).unwrap();
        assert!(clotho.contains("assembled-by=studio"));
        assert!(clotho.contains("BEGIN assembled-section source=roles/clotho.md"));
        assert!(clotho.contains("BEGIN assembled-section source=operating-manual.md"));
        assert!(clotho.contains("BEGIN assembled-section source=contexts/cli.md"));

        let _ = std::fs::remove_dir_all(&root);
        if let Some(parent) = config.parent() {
            let _ = std::fs::remove_dir_all(parent);
        }
    }

    #[test]
    fn existing_ah_config_is_respected_without_generating_studio_files() {
        let root = temp_path("user-ah-config");
        let child = root.join("child");
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&child).unwrap();
        std::fs::write(root.join("ah.toml"), "version = \"1\"\n").unwrap();

        let config =
            ah_config_for_workspace(&child, CodeAssistant::Claude, None, None).expect("existing ah config");

        assert_eq!(config, root.join("ah.toml"));
        assert!(!root.join(".ah").exists());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn status_config_lookup_does_not_generate_transient_workspace_files() {
        let root = temp_path("status-ah-config");
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();
        let transient = transient_ah_config_path(&root, CodeAssistant::Codex);
        let transient_dir = transient.parent().unwrap().to_path_buf();
        let _ = std::fs::remove_dir_all(&transient_dir);

        assert!(ah_config_for_status(&root, CodeAssistant::Codex).is_none());
        assert!(!root.join(".ah").exists());

        std::fs::create_dir_all(&transient_dir).unwrap();
        std::fs::write(
            &transient,
            transient_ah_config_content(CodeAssistant::Codex, None, None).expect("codex config"),
        )
        .unwrap();

        assert_eq!(
            ah_config_for_status(&root, CodeAssistant::Codex).as_deref(),
            Some(transient.as_path())
        );
        let _ = std::fs::remove_dir_all(&root);
        let _ = std::fs::remove_dir_all(transient_dir.parent().unwrap());
    }

    #[test]
    fn close_cleanup_requires_master_and_worker_tmux_to_be_gone() {
        assert!(code_assistant_shutdown_is_complete(
            AhLifecycleSnapshot::new(false, false, false)
        ));
        assert!(!code_assistant_shutdown_is_complete(
            AhLifecycleSnapshot::new(false, true, false)
        ));
        assert!(!code_assistant_shutdown_is_complete(
            AhLifecycleSnapshot::new(false, false, true)
        ));
        assert!(!code_assistant_shutdown_is_complete(
            AhLifecycleSnapshot::new(true, false, false)
        ));
    }

    #[test]
    fn ah_events_status_aggregation_is_display_only() {
        // Startup-window snapshots (inventory ACTIVE while the master tmux pane
        // is still cold-starting) are indistinguishable from stale leftovers, so
        // event snapshots must ONLY drive the status display — never cleanup.
        // Cleanup stays on user actions: prepare_code_assistant_open,
        // attach (CleanupStale), Close, and app quit.
        use ah_contract_fixtures::{SNAPSHOT_ACTIVE, SNAPSHOT_DAEMON_ABSENT, SNAPSHOT_STARTING};

        let workspace = PathBuf::from("/tmp/studio-skill");
        let claude_config = workspace.join(".claude-ah.toml");
        let codex_config = workspace.join(".codex-ah.toml");
        let specs = BTreeMap::from([
            (
                claude_config.clone(),
                CodeAssistantStatusSpec {
                    workspace_root: workspace.clone(),
                    assistant: CodeAssistant::Claude,
                },
            ),
            (
                codex_config.clone(),
                CodeAssistantStatusSpec {
                    workspace_root: workspace,
                    assistant: CodeAssistant::Codex,
                },
            ),
        ]);

        // task 6.1 cutover: the status cache is now the typed `AhRuntimeSnapshot` plane, so this
        // feeds frozen typed fixtures (was the old boolean `AhLifecycleSnapshot::new(...)`); the
        // display-only contract is unchanged. claude active; codex 的运行时确实被回收过。
        //
        // codex 两次都喂一帧真实的 daemon-absent 快照,而不是"不给快照"——决议 2026-08-03
        // D-C3 起,"没有帧"投影为 `unknown`,那是关于 Studio 观测状态的陈述,不是这条
        // display-only 契约要断言的运行时事实。
        let snapshots = BTreeMap::from([
            (claude_config.clone(), parse_snapshot_or_panic(SNAPSHOT_ACTIVE)),
            (
                codex_config.clone(),
                parse_snapshot_or_panic(SNAPSHOT_DAEMON_ABSENT),
            ),
        ]);
        let v = serde_json::to_value(code_assistant_status_from_snapshots(&specs, &snapshots))
            .expect("payload must serialize to the frontend wire shape");
        assert_eq!(v["claude"]["status"], "active");
        assert_eq!(v["codex"]["status"], "inactive");

        // The startup window (session STARTING, master tmux not yet alive) now projects as the
        // distinct `starting` phase — the typed plane no longer collapses it to `inactive`. It is
        // still display-only: reaching this phase never triggers cleanup.
        let starting = BTreeMap::from([
            (claude_config, parse_snapshot_or_panic(SNAPSHOT_STARTING)),
            (codex_config, parse_snapshot_or_panic(SNAPSHOT_DAEMON_ABSENT)),
        ]);
        let v_starting =
            serde_json::to_value(code_assistant_status_from_snapshots(&specs, &starting))
                .expect("payload must serialize to the frontend wire shape");
        assert_eq!(v_starting["claude"]["status"], "starting");
        assert_eq!(v_starting["codex"]["status"], "inactive");
    }

    #[test]
    fn opened_config_status_spec_is_authoritative_for_requested_assistant() {
        let workspace = PathBuf::from("/tmp/studio-skill");
        let config = workspace.join("ah.toml");
        let state = CodeAssistantRuntimeState {
            configs: Mutex::new(BTreeSet::from([config.clone()])),
            status_streams: Mutex::new(BTreeMap::new()),
            status_specs: Mutex::new(BTreeMap::from([(
                config.clone(),
                CodeAssistantStatusSpec {
                    workspace_root: workspace.clone(),
                    assistant: CodeAssistant::Codex,
                },
            )])),
            status_snapshots: Mutex::new(BTreeMap::new()),
        };

        let specs = next_status_specs_for_workspace(&state, &workspace);

        assert_eq!(
            specs.get(&config).map(|spec| spec.assistant),
            Some(CodeAssistant::Codex),
            "the config returned by open_codex_cli is the status identity source; discovery must not relabel it as Claude"
        );
    }

    // ── studio-ah-state-contract-v1 task 8 (per-assistant status payload) RED tests ──
    //
    // Authored by g2 (泳道2 gatekeeper) test-first: g2-m1 turns these GREEN by adding
    // ONLY the production code named below and must NOT edit this test file.
    //
    // Task 8 reshapes the `code-assistant-status-changed` payload from the two-boolean
    // `{claude:bool,codex:bool}` (lib.rs:157-160) into the per-assistant shape of
    // design.md:290-297 / Req 6.1-6.2, and DELETES the claude-wins suppression
    // (lib.rs:1342-1344). Contract seams g2-m1 must implement (crate scope; the payload
    // MUST stay `Serialize` — it crosses to the frontend via `app.emit`):
    //
    //   /// The five-value per-assistant runtime status (design.md:293). MUST serialize to
    //   /// the lowercase wire tokens the frontend union consumes
    //   /// (`'inactive'|'starting'|'active'|'degraded'|'error'`) — `#[serde(rename_all="lowercase")]`,
    //   /// never the PascalCase variant name. (This projection from AhLifecycleSnapshot only
    //   /// emits active/inactive today; the richer phases arrive when task 6/9 feed the typed
    //   /// snapshot in — the enum still declares all five.)
    //   enum AssistantStatus { Inactive, Starting, Active, Degraded, Error }
    //
    //   /// One assistant's slot in the reshaped payload (design.md:295-297). Serializes
    //   /// camelCase → `{ status, reason?, readOnly }`; `reason` is `skip_serializing_if` None.
    //   struct AssistantState { status: AssistantStatus, reason: Option<String>, read_only: bool }
    //
    //   /// The reshaped payload: replaces `{claude:bool,codex:bool}` OUTRIGHT (no dual format),
    //   /// one AssistantState per assistant — both keys always present.
    //   struct CodeAssistantStatus { claude: AssistantState, codex: AssistantState }
    //
    //   /// Ownership classification for a config path — task 5's seam, referenced here so the
    //   /// payload's readOnly is SOURCED from the single ownership authority, never a
    //   /// Studio-local guess. read_only==true ⇔ workspace-owned (find_ah_config walk-up);
    //   /// false ⇔ Studio-managed temp config. Declared+implemented by task 5, so these tests
    //   /// are compile-time RED (E0425 `classify_config_ownership` / E0433 `ConfigOwnership`)
    //   /// until task 5 lands it — the same RED mechanism as task 2/3/4.
    //   fn classify_config_ownership(config_path: &Path) -> ConfigOwnership
    //   struct ConfigOwnership { read_only: bool, /* … */ }
    //
    // `code_assistant_status_from_snapshots(specs, snapshots)` keeps its inputs but returns the
    // reshaped payload: per (config, spec) it maps the snapshot to AssistantState.status and
    // carries read_only = classify_config_ownership(config).read_only. Assertions are on the
    // SERIALIZED wire payload (what the frontend actually receives), not internal fields, so a
    // rename of the Rust types cannot dodge the contract. See tasks.md task 8 (104-109),
    // design.md:290-301, requirements.md Req 5.12 / 6.1 / 6.2.

    /// Req 6.2 / 5.12: each of Claude and Codex reports its own real state — including both
    /// active at once — with the claude-wins suppression (lib.rs:1342-1344) gone. Anchored to
    /// the serialized `code-assistant-status-changed` payload (the frontend contract boundary).
    /// Rollback self-check: restore `if claude { codex = inactive }` and the dual-active
    /// assertion reds; a constant `"active"` impl reds on the control case (claude active,
    /// codex not → codex must be `"inactive"`).
    #[test]
    fn test_payload_reports_claude_codex_independently() {
        use ah_contract_fixtures::SNAPSHOT_ACTIVE;

        let workspace = PathBuf::from("/tmp/studio-skill");
        let claude_config = workspace.join(".claude-ah.toml");
        let codex_config = workspace.join(".codex-ah.toml");
        let specs = BTreeMap::from([
            (
                claude_config.clone(),
                CodeAssistantStatusSpec {
                    workspace_root: workspace.clone(),
                    assistant: CodeAssistant::Claude,
                },
            ),
            (
                codex_config.clone(),
                CodeAssistantStatusSpec {
                    workspace_root: workspace.clone(),
                    assistant: CodeAssistant::Codex,
                },
            ),
        ]);

        // Both stacks active simultaneously (Req 5.12 "both active" pairing — the typed
        // `runtime_state: active` snapshot, task 6.1 having retyped the cache from the old
        // boolean plane; the serialized-payload assertions are unchanged).
        let both_active = BTreeMap::from([
            (claude_config.clone(), parse_snapshot_or_panic(SNAPSHOT_ACTIVE)),
            (codex_config.clone(), parse_snapshot_or_panic(SNAPSHOT_ACTIVE)),
        ]);
        let v = serde_json::to_value(code_assistant_status_from_snapshots(&specs, &both_active))
            .expect("payload must serialize to the frontend wire shape");
        assert_eq!(v["claude"]["status"], "active", "claude active reports active");
        assert_eq!(
            v["codex"]["status"], "active",
            "codex active reports its OWN active state — no claude-wins suppression (Req 6.2)"
        );

        // Control: claude active, codex 的运行时确实被回收过（daemon-absent 快照）→ 逐助手
        // 推导必须报 codex `inactive`（defeats a constant-`active` impl that would fake the
        // pair above, and proves both keys are always present）。
        //
        // 这里必须喂一帧**真实的** daemon-absent 快照，不能靠"不给 codex 快照"来制造
        // inactive：决议 2026-08-03 D-C3 起，"没有帧"投影为 `unknown` 而不是 `inactive`。
        let mixed = BTreeMap::from([
            (claude_config, parse_snapshot_or_panic(SNAPSHOT_ACTIVE)),
            (
                codex_config,
                parse_snapshot_or_panic(ah_contract_fixtures::SNAPSHOT_DAEMON_ABSENT),
            ),
        ]);
        let v2 = serde_json::to_value(code_assistant_status_from_snapshots(&specs, &mixed))
            .expect("payload must serialize to the frontend wire shape");
        assert_eq!(v2["claude"]["status"], "active");
        assert_eq!(
            v2["codex"]["status"], "inactive",
            "codex with no active stack is inactive — proves the state is derived per assistant"
        );
    }

    /// Req 6.1 / 5.12: the payload carries a per-assistant `readOnly` ownership flag — true for
    /// a workspace-owned config, false for a Studio-managed temp config — sourced from the
    /// single ownership authority (task 5's `classify_config_ownership`). Anchored to the frozen
    /// task-1 ownership fixtures + the serialized wire payload. Rollback self-check: hardcode
    /// `readOnly:false` (or drop the field) and the workspace-owned assertion reds; the two
    /// fixtures are opposite classes so no constant satisfies both.
    #[test]
    fn test_payload_carries_readonly_flag() {
        use ah_contract_fixtures::{CONFIG_STUDIO_MANAGED, CONFIG_WORKSPACE_OWNED, SNAPSHOT_ACTIVE};

        // Frozen fixture facts: one workspace-owned config (readOnly:true) + one Studio-managed
        // temp config (readOnly:false).
        assert!(CONFIG_WORKSPACE_OWNED.read_only, "workspace-owned fixture is readOnly:true");
        assert!(!CONFIG_STUDIO_MANAGED.read_only, "Studio-managed temp fixture is readOnly:false");

        // readOnly must be SOURCED from the ownership authority, not a Studio-local guess.
        // Referencing classify_config_ownership here is the compile-time RED seam (task 5) and
        // proves the payload agrees with the real classifier for each config.
        assert_eq!(
            classify_config_ownership(&CONFIG_WORKSPACE_OWNED.resolved_config_path()).read_only,
            CONFIG_WORKSPACE_OWNED.read_only,
            "classifier must agree with the frozen workspace-owned class"
        );
        assert_eq!(
            classify_config_ownership(&CONFIG_STUDIO_MANAGED.resolved_config_path()).read_only,
            CONFIG_STUDIO_MANAGED.read_only,
            "classifier must agree with the frozen Studio-managed class"
        );

        // Claude on the workspace-owned config, Codex on the Studio-managed config; both active
        // (readOnly is orthogonal to running state — a workspace-owned stack can be attached
        // for observation).
        let claude_config = CONFIG_WORKSPACE_OWNED.resolved_config_path();
        let codex_config = CONFIG_STUDIO_MANAGED.resolved_config_path();
        let claude_workspace = claude_config
            .parent()
            .expect("config path has a parent dir")
            .to_path_buf();
        let codex_workspace = codex_config
            .parent()
            .expect("config path has a parent dir")
            .to_path_buf();
        let specs = BTreeMap::from([
            (
                claude_config.clone(),
                CodeAssistantStatusSpec {
                    workspace_root: claude_workspace,
                    assistant: CodeAssistant::Claude,
                },
            ),
            (
                codex_config.clone(),
                CodeAssistantStatusSpec {
                    workspace_root: codex_workspace,
                    assistant: CodeAssistant::Codex,
                },
            ),
        ]);
        let snapshots = BTreeMap::from([
            (claude_config, parse_snapshot_or_panic(SNAPSHOT_ACTIVE)),
            (codex_config, parse_snapshot_or_panic(SNAPSHOT_ACTIVE)),
        ]);

        let v = serde_json::to_value(code_assistant_status_from_snapshots(&specs, &snapshots))
            .expect("payload must serialize to the frontend wire shape");
        assert_eq!(
            v["claude"]["readOnly"], true,
            "workspace-owned config → readOnly:true so the UI can render Detach / disabled-Open (Req 6.1)"
        );
        assert_eq!(
            v["codex"]["readOnly"], false,
            "Studio-managed temp config → readOnly:false so the normal lifecycle controls show (Req 6.1)"
        );
    }

    // ── 决议 2026-08-03(status-stream ownership)RED tests ──
    //
    // 缺陷 C:CLI 在跑,面板却渲染 `Open in CLI`。取证见
    // `.kiro/specs/studio-ah-state-contract-v1/decision-2026-08-03-status-stream-ownership.md`
    // 一.2:ah 侧 `runtime_state:"active"`,而 Studio 侧一个 `ah events` 生产者都不剩。
    // 根因是所有权错误——生产者的生死被 React 订阅者的 teardown 决定(D-C1),叠加
    // "尚未观测"被投影成 `inactive` 这句断言(D-C3)。
    //
    // 下面的测试锁住两条不变量:
    //   ① 生产者集合只由「当前被观察的 workspace」决定,订阅者来去不改变它(D-C1/D-C2);
    //   ② 有 spec 但没有任何快照帧 ⇒ `unknown`,绝不是 `inactive`(D-C3)。

    /// 判据 C-1:同一 workspace 连续 watch,已在跑的生产者不得被停掉再重启。
    ///
    /// 回滚自检:把 `stop` 改成「registered 全停」,本例立刻红——它正是缺陷 C 里
    /// 「teardown 杀掉活着的订阅者的生产者」那条路径的纯函数形态。
    #[test]
    fn test_watch_is_idempotent_for_a_live_producer() {
        let config = PathBuf::from("/tmp/ws-a/claude/ah.toml");
        let registered = BTreeSet::from([config.clone()]);
        let running = BTreeSet::from([config.clone()]);
        let watched = BTreeSet::from([config.clone()]);

        let plan = plan_status_streams(&registered, &running, &watched);

        assert!(
            plan.start.is_empty(),
            "生产者已在跑,重复 watch 不得再起一个"
        );
        assert!(
            plan.stop.is_empty(),
            "重复 watch 不得停掉正在被观察的生产者(缺陷 C 的核心不变量)"
        );
    }

    /// 判据 C-1 的对照组:没有生产者时必须起一个,证明上一条不是恒空。
    #[test]
    fn test_watch_starts_a_missing_producer() {
        let claude = PathBuf::from("/tmp/ws-a/claude/ah.toml");
        let codex = PathBuf::from("/tmp/ws-a/codex/ah.toml");
        let watched = BTreeSet::from([claude.clone(), codex.clone()]);

        let plan = plan_status_streams(&BTreeSet::new(), &BTreeSet::new(), &watched);

        assert_eq!(plan.start, vec![claude, codex], "缺席的生产者要补齐");
        assert!(plan.stop.is_empty(), "没有多余的生产者可停");
    }

    /// 判据 C-4:切到另一个 workspace 时,只停别的 workspace 的生产者,新的要起来。
    /// Studio 同一时刻只显示一个工作区,这条就是删掉 unwatch 之后生产者数量的上界(D-C2)。
    #[test]
    fn test_watching_another_workspace_stops_only_the_other_producers() {
        let ws_a = PathBuf::from("/tmp/ws-a/claude/ah.toml");
        let ws_b = PathBuf::from("/tmp/ws-b/claude/ah.toml");
        let registered = BTreeSet::from([ws_a.clone()]);
        let running = BTreeSet::from([ws_a.clone()]);
        let watched = BTreeSet::from([ws_b.clone()]);

        let plan = plan_status_streams(&registered, &running, &watched);

        assert_eq!(plan.start, vec![ws_b], "新观察的 workspace 要有生产者");
        assert_eq!(plan.stop, vec![ws_a], "旧 workspace 的生产者才是该停的那个");
    }

    /// 判据 C-4 的另一半:本 workspace 里已经消失的 config(临时配置被删)也要停掉,
    /// 否则生产者会挂在一个不存在的配置上空转。
    #[test]
    fn test_plan_stops_a_config_that_left_this_workspace() {
        let kept = PathBuf::from("/tmp/ws-a/claude/ah.toml");
        let gone = PathBuf::from("/tmp/ws-a/codex/ah.toml");
        let registered = BTreeSet::from([kept.clone(), gone.clone()]);
        let running = BTreeSet::from([kept.clone(), gone.clone()]);
        let watched = BTreeSet::from([kept]);

        let plan = plan_status_streams(&registered, &running, &watched);

        assert!(plan.start.is_empty());
        assert_eq!(plan.stop, vec![gone]);
    }

    /// 2026-08-04 真机复现的回归:Close 之后面板永久停在 `unknown`、Open 控件禁用点不动。
    ///
    /// 根因是"清空快照缓存"这个动作本身:`ah stop` 杀掉 ahd 之后,该 config 的 `ah events`
    /// 子进程不退出、只是永远不再发帧(实测存活 3 分钟以上、零重生),所以被清空的缓存再也
    /// 没有东西能填回来。修法是让"确认消失"走**重开观察流**这一条路——因此代码里不应再
    /// 存在任何"只清缓存、不重开流"的入口。这条测试把那个入口的消失钉住。
    ///
    /// 回滚自检:把 `clear_status_snapshots_for_workspace` 加回来,本例立刻红。
    #[test]
    fn no_cache_clearing_entry_survives_without_restarting_the_observer() {
        let source = include_str!("lib.rs");
        assert!(
            source.contains("fn restart_status_streams_for_workspace"),
            "确认运行时消失之后,必须由重开观察流来接管"
        );
        // needle 在运行期拼出来,否则 `include_str!` 会把这条断言自己的字面量也算进去。
        let clear_only_entry = format!("fn clear_status_snapshots{}", "_for_workspace");
        assert!(
            !source.contains(&clear_only_entry),
            "只清缓存不重开流的入口必须彻底消失——它会把面板永久钉在 unknown"
        );
    }

    /// 判据 C-3:不存在任何"订阅者可以停掉共享生产者"的命令入口。
    /// 断言范围严格限定在 `generate_handler!` 注册块内,避免把本测试自己的文本算进去。
    #[test]
    fn invoke_handler_exposes_no_subscriber_driven_teardown_command() {
        let source = include_str!("lib.rs");
        let start = source
            .find("generate_handler![")
            .expect("invoke handler registry must exist");
        let registry = &source[start..];
        let end = registry
            .find("])")
            .expect("invoke handler registry must be closed");
        let registry = &registry[..end];

        assert!(
            registry.contains("watch_code_assistant_status,"),
            "watch(确保生产者存在)仍然是前端唯一的订阅入口"
        );
        assert!(
            !registry.contains("unwatch"),
            "决议 2026-08-03 D-C1:视图的卸载不得销毁共享的数据源,因此不存在反向命令"
        );
    }

    /// 判据 C-5:有 spec 但一帧快照都没拿到 ⇒ `unknown`。
    ///
    /// `inactive` 在本契约里是一句断言(「该 config 的 ah 运行时确实被回收过」,
    /// 见 2026-08-02 决议 D-A1/D-A4 决策表末行),把"还没观测到"塞进这句断言,就是
    /// 缺陷 C 在界面上的可见形态:面板给出一个可点击但语义错误的 Open 入口。
    ///
    /// 回滚自检:把投影改回 `.unwrap_or(AssistantStatus::Inactive)`,本例立刻红。
    #[test]
    fn test_spec_without_a_frame_projects_unknown_not_inactive() {
        let workspace = PathBuf::from("/tmp/studio-skill");
        let claude_config = workspace.join(".claude-ah.toml");
        let specs = BTreeMap::from([(
            claude_config,
            CodeAssistantStatusSpec {
                workspace_root: workspace,
                assistant: CodeAssistant::Claude,
            },
        )]);

        let v = serde_json::to_value(code_assistant_status_from_snapshots(&specs, &BTreeMap::new()))
            .expect("payload must serialize to the frontend wire shape");

        assert_eq!(
            v["claude"]["status"], "unknown",
            "有配置但还没有任何快照 = 尚未观测,不得冒充「确定没有在跑」"
        );
    }

    /// 判据 C-6(对照组,证明 `unknown` 不是恒定值):磁盘上根本没有 ah 配置的助手,
    /// 是一次真实观测——没有配置就没有 Studio 管理的运行时——仍然是 `inactive`。
    #[test]
    fn test_assistant_without_a_config_stays_inactive() {
        let workspace = PathBuf::from("/tmp/studio-skill");
        let claude_config = workspace.join(".claude-ah.toml");
        let specs = BTreeMap::from([(
            claude_config.clone(),
            CodeAssistantStatusSpec {
                workspace_root: workspace,
                assistant: CodeAssistant::Claude,
            },
        )]);
        let snapshots = BTreeMap::from([(
            claude_config,
            parse_snapshot_or_panic(ah_contract_fixtures::SNAPSHOT_ACTIVE),
        )]);

        let v = serde_json::to_value(code_assistant_status_from_snapshots(&specs, &snapshots))
            .expect("payload must serialize to the frontend wire shape");

        assert_eq!(v["claude"]["status"], "active", "前置:claude 侧确有帧");
        assert_eq!(
            v["codex"]["status"], "inactive",
            "codex 根本没有 spec ⇒ 没有配置 ⇒ 真实观测到「没有运行时」,不是 unknown"
        );
    }

    /// 判据 D-C4:bootstrap 只在该 config 一帧都没有时播种。
    /// 子进程重生(`events-exited-respawning`)时缓存里已有帧,不得再跨 WSL 读一次
    /// `status --json` 拖慢重连。
    #[test]
    fn test_bootstrap_seeds_only_when_the_cache_has_no_frame() {
        let config = PathBuf::from("/tmp/ws-a/claude/ah.toml");
        let empty: BTreeMap<PathBuf, AhRuntimeSnapshot> = BTreeMap::new();
        let seeded = BTreeMap::from([(
            config.clone(),
            parse_snapshot_or_panic(ah_contract_fixtures::SNAPSHOT_ACTIVE),
        )]);

        assert!(
            needs_bootstrap_seed(&empty, &config),
            "冷启动:没有任何帧才需要 status --json 播种"
        );
        assert!(
            !needs_bootstrap_seed(&seeded, &config),
            "已有帧(含重生场景)不得重复播种"
        );
    }

    // ── studio-ah-state-contract-v1 task 5 (ownership guard + env clamp) RED tests ──
    //
    // Authored by g1 (泳道1 gatekeeper) test-first for the cross-lane hand-off: g2
    // turns these GREEN by adding ONLY the production seams named below and must NOT
    // edit this test file. This task is "护栏先行" (tasks.md:23/77): the ownership
    // classifier + env clamp MUST land before any task (6/7) can emit `ah start`/
    // `stop`/`kill`, so there is never a "can fire lifecycle commands but the guard
    // is not wired" middle state.
    //
    // Two production seams g2 must implement (crate scope), both PURE (no subprocess,
    // no live-fleet touch) so these tests are compile-time RED (E0425) until g2 lands
    // them — the same RED mechanism as tasks 2/3/4/8:
    //
    //   /// Lifecycle-command entry guard (tasks.md:79/82, Req 5.9). Lifecycle commands
    //   /// (`start`/`stop`/`kill`) may run ONLY against a Studio-managed temp config;
    //   /// a workspace-owned config discovered by walking up (`find_ah_config`) is
    //   /// read-only. Ownership MUST be sourced from the single authority
    //   /// `classify_config_ownership` (底座一/SSOT), never a second guess. Ok(()) for
    //   /// Studio-managed; Err(diagnostic) for workspace-owned. Read-only commands
    //   /// (status/events/observational attach) do NOT pass through this guard.
    //   /// g2 must call it at the top of every start/stop/kill entry point
    //   /// (`cleanup_code_assistant_config`/`force_cleanup_ah_runtime`/the start path)
    //   /// BEFORE any subprocess — the gatekeeper verifies that wiring at GREEN.
    //   fn ensure_lifecycle_command_allowed(config_path: &Path) -> Result<(), String>
    //
    //   /// The bash `-c` script the Windows `wsl.exe -e bash -lc` path runs for an ah
    //   /// command (tasks.md:81, Req 4.7 / 坑洞 3.5). Extracted from
    //   /// `run_ah_config_command_output` (lib.rs:965) and reused by
    //   /// `spawn_ah_events_command` (lib.rs:995) so both call sites carry the clamp.
    //   /// It MUST clamp `AH_STATE_DIR`/`CCBD_STATE_DIR`/`XDG_STATE_HOME` INSIDE the
    //   /// script string itself (`export AH_STATE_DIR=""; …`), not via Rust
    //   /// `Command::env` — a `-lc` login shell re-sources the user profile AFTER
    //   /// inheriting Command::env and would overwrite it. Pure string builder →
    //   /// testable on Linux even though the wsl.exe path is Windows-only.
    //   fn build_ah_bash_script(config_path: &Path, ah_args: &[&str]) -> String

    /// Req 5.9 / 4.6: a workspace-owned ah config (walked-up `ah.toml`) is read-only —
    /// it must REFUSE `start`/`stop`/`kill` — while a Studio-managed temp config allows
    /// the full lifecycle; and read-only status/events discovery is NOT gated by
    /// ownership. Anchored to the frozen task-1 ownership fixtures + the single
    /// ownership authority (`classify_config_ownership`). Kept fully pure so no `ah stop`
    /// is ever fired at the operator's live fleet while the guard is still absent.
    /// Rollback self-check: an always-Ok guard reds the workspace-owned refusal; an
    /// always-Err guard reds the Studio-managed allow; the two fixtures are opposite
    /// classes so no constant satisfies the ownership-authority consistency loop.
    #[test]
    fn test_lifecycle_only_on_studio_managed_config() {
        use ah_contract_fixtures::{
            ALL_CONFIG_OWNERSHIP_FIXTURES, CONFIG_STUDIO_MANAGED, CONFIG_WORKSPACE_OWNED,
        };

        // Frozen fixture facts: workspace-owned = read-only, Studio-managed temp = lifecycle-ok.
        assert!(CONFIG_WORKSPACE_OWNED.read_only, "workspace-owned fixture is readOnly:true");
        assert!(!CONFIG_STUDIO_MANAGED.read_only, "Studio-managed temp fixture is readOnly:false");

        // A workspace-owned config REFUSES lifecycle commands; a Studio-managed temp
        // config allows them.
        assert!(
            ensure_lifecycle_command_allowed(&CONFIG_WORKSPACE_OWNED.resolved_config_path())
                .is_err(),
            "workspace-owned config must refuse start/stop/kill (Req 5.9)"
        );
        assert!(
            ensure_lifecycle_command_allowed(&CONFIG_STUDIO_MANAGED.resolved_config_path())
                .is_ok(),
            "Studio-managed temp config allows the full lifecycle (Req 4.6 class b)"
        );

        // The guard's verdict MUST be sourced from the single ownership authority:
        // lifecycle-allowed ⇔ NOT read-only, for every registered ownership class.
        for f in ALL_CONFIG_OWNERSHIP_FIXTURES {
            let path = f.resolved_config_path();
            let allowed = ensure_lifecycle_command_allowed(&path).is_ok();
            assert_eq!(
                allowed,
                !classify_config_ownership(&path).read_only,
                "lifecycle permission must derive from classify_config_ownership, not a second guess"
            );
            assert_eq!(allowed, !f.read_only, "guard must agree with the frozen ownership class");
        }

        // Read-only status/events discovery is NOT gated by ownership: the SAME
        // workspace-owned config is still surfaced for observation (status), yet its
        // lifecycle commands stay refused. Built on a throwaway temp workspace so the
        // real fleet is never touched.
        let workspace = temp_path("lifecycle-guard-workspace");
        let _ = std::fs::remove_dir_all(&workspace);
        std::fs::create_dir_all(&workspace).unwrap();
        let discovered_config = workspace.join("ah.toml");
        std::fs::write(
            &discovered_config,
            transient_ah_config_content(CodeAssistant::Claude, None, None).expect("transient claude ah config"),
        )
        .unwrap();

        let status_config = ah_config_for_status(&workspace, CodeAssistant::Claude)
            .expect("read-only status discovery still surfaces the workspace ah.toml");
        assert_eq!(
            status_config, discovered_config,
            "status/events observation is unaffected by ownership"
        );
        assert!(
            classify_config_ownership(&status_config).read_only,
            "a walked-up ah.toml outside the Studio temp namespace is workspace-owned"
        );
        assert!(
            ensure_lifecycle_command_allowed(&status_config).is_err(),
            "same config: observable via status/events, but start/stop/kill refused (Req 5.9)"
        );

        let _ = std::fs::remove_dir_all(&workspace);
    }

    /// Req 4.7 / 坑洞 3.5: the ah bash `-c` script must clamp `AH_STATE_DIR`,
    /// `CCBD_STATE_DIR`, and `XDG_STATE_HOME` INSIDE the script string itself
    /// (`export AH_STATE_DIR=""; …`), before the ah command runs — a `-lc` login shell
    /// re-sources the user profile after inheriting `Command::env`, so a Rust-side
    /// `Command::env` clamp would be silently overwritten. Anchored to the pure builder
    /// `build_ah_bash_script`, the exact string the Windows `wsl.exe -e bash -lc` path
    /// executes. Rollback self-check: drop the in-string clamp (or move it to
    /// `Command::env`) and the `export …=""` assertions red; the ordering assertion
    /// reds if the clamp is emitted after the ah command.
    #[test]
    fn test_env_clamp_in_bash_string() {
        let config = Path::new("/tmp/skill-studio-ah/0123456789abcdef/claude/ah.toml");
        let script = build_ah_bash_script(config, &["status", "--json"]);

        for clamp in [
            r#"export AH_STATE_DIR="""#,
            r#"export CCBD_STATE_DIR="""#,
            r#"export XDG_STATE_HOME="""#,
        ] {
            assert!(
                script.contains(clamp),
                "state-dir env must be clamped in the bash -c string, missing `{clamp}`\nscript: {script}"
            );
        }

        // The clamp must be exported BEFORE the ah invocation reads the environment.
        let clamp_at = script
            .find(r#"export AH_STATE_DIR="""#)
            .expect("AH_STATE_DIR clamp present");
        let ah_at = script.find("ah --config").expect("ah command present in the script");
        assert!(
            clamp_at < ah_at,
            "state-dir clamp must precede the ah command so ah reads the clamped env\nscript: {script}"
        );

        // Regression guard: the refactored builder still carries the existing env
        // shaping and the requested config + ah args.
        assert!(
            script.contains("SYSTEMD_LOG_LEVEL=err"),
            "existing SYSTEMD_LOG_LEVEL shaping must survive the refactor\nscript: {script}"
        );
        assert!(script.contains("ah.toml"), "script targets the requested config path");
        assert!(
            script.contains("status") && script.contains("--json"),
            "script carries the requested ah args"
        );
    }

    // ── studio-ah-state-contract-v1 task 7 (Close / app-quit cleanup) RED tests ──
    //
    // Authored by g2 (泳道2 gatekeeper) test-first from the brief/spec contract — NOT
    // read off any implementation. g2-m1 turns these GREEN by rebuilding the cleanup
    // path and must NOT edit this test file. Task 6.1 (tasks.md:119) deliberately left
    // `force_cleanup_ah_runtime`'s session selection to task 7 ("目标 session id 来自
    // identity-checked 快照里 `cleanup_required`/非 `safe_to_cleanup` 的 session ...
    // 须与任务 7 协调"), so the two tests below pin exactly that hand-off + the
    // ownership boundary at app-quit.
    //
    // Two RED signals, two mechanisms (both safe — no live-fleet touch):
    //
    //   (1) A NEW pure seam g2-m1 must add and `force_cleanup_ah_runtime` must consume
    //       (crate scope, no subprocess) — compile-time RED (E0425) until it lands, the
    //       same RED mechanism as tasks 2/3/4/5/8. `force_cleanup_ah_runtime` today
    //       kills every `ah ps`-derived + tmux session id (lib.rs:1129-1173); the
    //       rebuild must instead escalate `ah kill --session <id> --force` to ONLY the
    //       session ids this selector returns (design.md:226, Req 4.2/5.5). The
    //       gatekeeper's GREEN-time diff audit verifies the wiring (this function is
    //       actually called and the ps/tmux session-id path is deleted) — the shim
    //       existing but unused would be caught there, not here.
    //
    //         /// The session ids Close/app-quit escalation may `ah kill --session <id>
    //         /// --force`, taken ONLY from the identity-checked snapshot's own
    //         /// `sessions[]` and driven by ah's per-session cleanup judgment — never
    //         /// Studio re-deriving "non-terminal therefore kill" (Req 4.2/5.5,
    //         /// design.md:226). A session ah has NOT flagged `cleanup_required` (a
    //         /// healthy ACTIVE stack is `cleanup_required:false, safe_to_cleanup:false`
    //         /// per task0-cli-evidence-2026-07-10.md:166 — live work, must be spared)
    //         /// is not a target; `!safe_to_cleanup` alone must never escalate a kill.
    //         fn cleanup_target_session_ids(snapshot: &AhRuntimeSnapshot) -> Vec<String>
    //
    //   (2) The EXISTING app-quit/Close orchestrator `cleanup_workspace_code_assistants`
    //       (lib.rs:1240, called by `close_code_assistant` and the quit paths) — a
    //       behavioral RED: given a workspace whose only ah config is workspace-owned
    //       (repo-root `ah.toml`), it must transparently skip it (touch nothing) and
    //       return `Ok(closed_any=false)` (Req 5.9/4.6, tasks.md:129). Today the task-5
    //       ownership guard's `Err` propagates through the loop's `?` and ABORTS the
    //       whole quit cleanup — so the assertion `is_ok()` reds now. Safe: the guard
    //       short-circuits before any `ah`/`tmux` subprocess, so no lifecycle command is
    //       ever issued at the operator's own fleet while this runs RED.
    //
    // See tasks.md task 7 (124-131), design.md:137-152 (Close cleanup) + 219-229
    // (Cleanup orchestrator), requirements.md Req 4.2/5.5/5.9/4.6.

    /// A multi-session snapshot the way one ahd can legitimately hold several sessions,
    /// composed from the real per-session shapes captured in task0-cli-evidence
    /// (2026-07-10): a healthy ACTIVE session (`cleanup_required:false,
    /// safe_to_cleanup:false`, line 166), a degraded ACTIVE session that ah HAS flagged
    /// for cleanup (`cleanup_required:true`, the `runtime_state:"degraded"` shape), and a
    /// cleanly-terminal CLOSED session (`cleanup_required:false, safe_to_cleanup:true`).
    /// Only the middle session is a cleanup target; the other two are the discriminators
    /// that separate the ah-flag-driven rule from a Studio "non-terminal ⇒ kill" guess.
    const SNAPSHOT_MULTI_SESSION_MIXED_CLEANUP: &str = r#"{
      "schema_version": 2, "event": "snapshot", "sequence": 1, "reason": "initial",
      "runtime_state": "degraded", "active": false, "ahd_alive": true,
      "ahd_has_inventory": true, "config_path": null, "workspace_path": null,
      "state_dir": "/root/.local/state/ah/f2647adf", "tmux_socket": "ahd-5a709091c406a3fa",
      "tmux_server_alive": true, "master_tmux_alive": false, "worker_tmux_alive": true,
      "worker_tmux_expected_count": 16, "agents": [],
      "sessions": [
        {"session_id": "sess_live-a1a1a1a1-0000-4000-8000-000000000001",
         "project_id": "live-session-workspace",
         "path": "/root/agent-harness/.worktrees/live-session-workspace",
         "status": "ACTIVE", "master_state": "BUSY", "master_tmux_alive": true,
         "db_tracked_agents": 6, "live_agents": 6,
         "cleanup_required": false, "safe_to_cleanup": false},
        {"session_id": "sess_deg-b2b2b2b2-0000-4000-8000-000000000002",
         "project_id": "degraded-session-workspace",
         "path": "/root/agent-harness/.worktrees/degraded-session-workspace",
         "status": "ACTIVE", "master_state": null, "master_tmux_alive": false,
         "db_tracked_agents": 10, "live_agents": 10,
         "cleanup_required": true, "safe_to_cleanup": true},
        {"session_id": "sess_closed-c3c3c3c3-0000-4000-8000-000000000003",
         "project_id": "closed-session-workspace",
         "path": "/root/agent-harness/.worktrees/closed-session-workspace",
         "status": "CLOSED", "master_state": null, "master_tmux_alive": false,
         "db_tracked_agents": 0, "live_agents": 0,
         "cleanup_required": false, "safe_to_cleanup": true}
      ],
      "jobs": [], "job_events": [], "job_event_cursor": 0
    }"#;

    /// Req 5.5 / 4.2 — when cleanup escalates over a snapshot with MULTIPLE sessions, it
    /// must `ah kill --session <id> --force` ONLY the sessions ah itself flagged for
    /// cleanup, taken from the snapshot's own `sessions[]` — never re-derive "this
    /// session is non-terminal, therefore kill" in Studio (design.md:226, F8). The
    /// fixture pairs the exact real shapes: a live ACTIVE session ah did NOT flag
    /// (`cleanup_required:false`) must be SPARED even though its status is non-terminal,
    /// a degraded ACTIVE session ah DID flag (`cleanup_required:true`) is the only
    /// target, and a terminal CLOSED session is spared. Target set = exactly the one
    /// cleanup-required session id.
    ///
    /// COMPILE-TIME RED (expected): `cleanup_target_session_ids` does not exist yet, so
    /// the whole `cargo test --lib` fails to compile (E0425) until g2-m1 adds it and
    /// wires `force_cleanup_ah_runtime` to it — the standard TDD intermediate state.
    ///
    /// Rollback self-check (not self-anchored): the current `ah ps`/tmux path kills
    /// every discovered session id → includes the live + closed sessions → reds the two
    /// "must be spared" assertions. A `!safe_to_cleanup` predicate targets the live
    /// session (`safe_to_cleanup:false`) → reds. A "non-terminal ⇒ kill" predicate
    /// targets the live ACTIVE session → reds. Only ah's own `cleanup_required` flag
    /// yields exactly {degraded}, so reverting to any Studio-side re-derivation reds it.
    #[test]
    fn test_cleanup_targets_only_cleanup_required_sessions() {
        let snapshot = parse_snapshot_or_panic(SNAPSHOT_MULTI_SESSION_MIXED_CLEANUP);

        // Preconditions: the fixture carries the three discriminating real shapes.
        let live = snapshot
            .sessions
            .iter()
            .find(|s| s.session_id.starts_with("sess_live-"))
            .expect("fixture has a live session");
        let degraded = snapshot
            .sessions
            .iter()
            .find(|s| s.session_id.starts_with("sess_deg-"))
            .expect("fixture has a degraded session");
        let closed = snapshot
            .sessions
            .iter()
            .find(|s| s.session_id.starts_with("sess_closed-"))
            .expect("fixture has a closed session");
        assert_eq!(live.status, "ACTIVE");
        assert!(
            !live.cleanup_required && !live.safe_to_cleanup,
            "the live session mirrors the real healthy-ACTIVE shape (cleanup_required:false, safe_to_cleanup:false) — must be spared"
        );
        assert!(
            degraded.status == "ACTIVE" && degraded.cleanup_required,
            "the degraded session is the only one ah flagged cleanup_required — the sole kill target"
        );
        assert_eq!(closed.status, "CLOSED");

        let targets: BTreeSet<String> = cleanup_target_session_ids(&snapshot)
            .into_iter()
            .collect();

        // The one cleanup-required session IS targeted.
        assert!(
            targets.contains(&degraded.session_id),
            "the cleanup_required session must be escalated for `ah kill` (Req 5.5/4.2)"
        );
        // A non-terminal (ACTIVE) session ah did NOT flag for cleanup is SPARED — this is
        // the load-bearing defeat of "非终态即 kill" (Req 4.2: prefer ah's own fields).
        assert!(
            !targets.contains(&live.session_id),
            "a live ACTIVE session ah did not flag (cleanup_required:false) must NOT be killed — no 'non-terminal therefore kill' (Req 5.5/4.2)"
        );
        // A cleanly-terminal CLOSED session is spared (nothing to clean).
        assert!(
            !targets.contains(&closed.session_id),
            "a terminal CLOSED session needs no cleanup and must not be killed"
        );
        // Complete contract: escalation targets EXACTLY the cleanup-required session ids
        // present in the snapshot — no more (defeats kill-all-found), no fewer, and every
        // target is a snapshot session id (Req 4.2 'only session ids present in the snapshot').
        assert_eq!(
            targets,
            BTreeSet::from([degraded.session_id.clone()]),
            "cleanup escalation must target exactly the snapshot's cleanup_required session ids, driven by ah's judgment not Studio's"
        );
    }

    /// Req 5.9 / 4.6 — Close and app quit must never issue a lifecycle command
    /// (`ah stop`/`ah kill`) against a workspace-owned config (a walked-up repo-root
    /// `ah.toml` that belongs to the operator's own fleet), and a workspace-owned config
    /// discovered in the cleanup set must be transparently SKIPPED, not turned into an
    /// error that aborts the whole quit (tasks.md:129 "只清理 Studio ... 不触碰
    /// workspace-owned config"). Driven through the REAL app-quit/Close orchestrator
    /// `cleanup_workspace_code_assistants` (called by `close_code_assistant`, lib.rs:2727,
    /// and the quit paths at 2543/2608) over a hermetic throwaway workspace whose only ah
    /// config is workspace-owned — the operator's live fleet is never touched.
    ///
    /// RED now (behavioral): today the task-5 ownership guard returns `Err` for the
    /// workspace-owned config and that `Err` propagates through the loop's `?`, so
    /// `cleanup_workspace_code_assistants` returns `Err` and the `is_ok()` assertion
    /// reds. Safe: the guard short-circuits before any `ah`/`tmux` subprocess, so no
    /// lifecycle command is ever issued while this runs RED. Task 7 makes it green by
    /// skipping read-only (workspace-owned) configs from the lifecycle cleanup instead of
    /// aborting on them.
    ///
    /// Not a blanket no-op: the ownership authority must still DISTINGUISH the classes —
    /// a workspace-owned config refuses lifecycle commands while a Studio-managed temp
    /// config allows them (asserted purely via `ensure_lifecycle_command_allowed` on the
    /// frozen task-1 fixtures), so the skip is selective, not "never clean anything".
    #[test]
    fn test_quit_leaves_workspace_owned_config_untouched() {
        use ah_contract_fixtures::{CONFIG_STUDIO_MANAGED, CONFIG_WORKSPACE_OWNED};

        // The skip must be OWNERSHIP-selective, sourced from the single authority: a
        // workspace-owned config refuses lifecycle commands; a Studio-managed temp config
        // allows them (pure, no subprocess — defeats an "always Ok, clean nothing" impl).
        assert!(CONFIG_WORKSPACE_OWNED.read_only, "workspace-owned fixture is readOnly:true");
        assert!(!CONFIG_STUDIO_MANAGED.read_only, "Studio-managed temp fixture is readOnly:false");
        assert!(
            ensure_lifecycle_command_allowed(&CONFIG_WORKSPACE_OWNED.resolved_config_path())
                .is_err(),
            "workspace-owned config must refuse start/stop/kill (Req 5.9)"
        );
        assert!(
            ensure_lifecycle_command_allowed(&CONFIG_STUDIO_MANAGED.resolved_config_path())
                .is_ok(),
            "Studio-managed temp config allows the full lifecycle — the skip is selective, not blanket"
        );

        // Hermetic workspace whose only ah config is workspace-owned (a walked-up
        // `ah.toml` outside the Studio temp namespace). Never touches the real fleet.
        let workspace = temp_path("quit-workspace-owned");
        let _ = std::fs::remove_dir_all(&workspace);
        std::fs::create_dir_all(&workspace).unwrap();
        let discovered_config = workspace.join("ah.toml");
        std::fs::write(
            &discovered_config,
            transient_ah_config_content(CodeAssistant::Claude, None, None).expect("transient claude ah config"),
        )
        .unwrap();

        // Fixture precondition: the walked-up config really classifies workspace-owned.
        let status_config = ah_config_for_status(&workspace, CodeAssistant::Claude)
            .expect("read-only status discovery still surfaces the workspace ah.toml");
        assert_eq!(status_config, discovered_config);
        assert!(
            classify_config_ownership(&status_config).read_only,
            "a walked-up ah.toml outside the Studio temp namespace is workspace-owned"
        );

        // The real app-quit/Close cleanup path must SKIP the workspace-owned config and
        // return cleanly — never abort the quit, never report having closed it, never
        // issue a lifecycle command against the operator's own fleet (Req 5.9/4.6).
        let cleanup = cleanup_workspace_code_assistants(&workspace).expect(
            "quit/Close cleanup over a workspace-owned config must skip it and return Ok, \
             not abort the whole cleanup with the ownership guard's Err (Req 5.9/4.6)",
        );
        assert!(
            !cleanup.closed_any,
            "no workspace-owned runtime was closed — Close/quit issues no `ah stop`/`ah kill` against it (Req 5.9)"
        );

        let _ = std::fs::remove_dir_all(&workspace);
    }

    #[test]
    fn ah_ps_probe_extracts_tmux_socket_label_and_session_ids() {
        let output = r#"
Sessions
sess_alpha  running
sess_beta,  done

💡 To inspect live tmux sessions: tmux -L ahd-57379dc91a921eed ls
"#;

        assert_eq!(
            extract_tmux_socket_label(output).as_deref(),
            Some("ahd-57379dc91a921eed")
        );
        assert_eq!(
            extract_ah_session_ids(output),
            vec!["sess_alpha".to_string(), "sess_beta".to_string()]
        );
    }

    #[test]
    fn ah_ps_probe_requires_session_inventory_not_just_success() {
        let empty_output = "";
        let active_output = r#"
sessions
+-------------------------------------------+-------------------+
| session_id                                | project_id        |
+-------------------------------------------+-------------------+
| sess_77674378-4680-45fc-9d3c-dc83af81cb23 | text-segmentation |
+-------------------------------------------+-------------------+

💡 To inspect live tmux sessions: tmux -L ahd-0b624d24e71a6307 ls
"#;

        assert!(!ah_ps_output_has_inventory(empty_output));
        assert!(ah_ps_output_has_inventory(active_output));
    }

    #[test]
    fn generated_workspace_files_refuse_unmanaged_collisions() {
        let root = temp_path("moirai-collision");
        let rules = root.join(".ah").join("rules");
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&rules).unwrap();
        std::fs::write(rules.join("master.md"), "user-owned rules\n").unwrap();

        let error = prepare_studio_ah_workspace(&root).expect_err("collision must fail");

        assert!(error.contains("refusing to overwrite unmanaged ah file"));
        assert!(error.contains("master.md"));
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn generated_workspace_files_refuse_modified_managed_files() {
        let root = temp_path("moirai-modified-managed");
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();
        prepare_studio_ah_workspace(&root).expect("initial managed files");
        let master_rules = root.join(".ah").join("rules").join("master.md");
        let mut edited = std::fs::read_to_string(&master_rules).unwrap();
        edited.push_str("\nuser edit\n");
        std::fs::write(&master_rules, edited).unwrap();

        let error = prepare_studio_ah_workspace(&root).expect_err("modified managed file fails");

        assert!(error.contains("modified Studio-managed ah file"));
        assert!(error.contains("master.md"));
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn find_ah_config_walks_up_from_workspace() {
        let root = temp_path("ah-config-root");
        let child = root.join("child").join("nested");
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&child).unwrap();
        std::fs::write(
            root.join("ah.toml"),
            transient_ah_config_content(CodeAssistant::Claude, None, None).expect("claude config"),
        )
        .unwrap();

        let found = find_ah_config(&child).expect("ah config found");

        assert_eq!(found, root.join("ah.toml"));
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn windows_path_to_wsl_maps_drive_to_mnt() {
        assert_eq!(
            windows_path_to_wsl(Path::new(r"C:\Users\Test User\skill")),
            "/mnt/c/Users/Test User/skill"
        );
        assert_eq!(windows_path_to_wsl(Path::new(r"D:\a\b")), "/mnt/d/a/b");
        assert_eq!(windows_path_to_wsl(Path::new(r"\\?\D:\a\b")), "/mnt/d/a/b");
    }

    #[test]
    fn wsl_payload_starts_ah_then_attaches_master() {
        let script = wsl_payload_script(
            "/mnt/c/Users/Test User/skill",
            "/mnt/c/Users/Test User/AppData/Local/Temp/ah.toml",
            CodeAssistant::Claude,
            None,
            Some("/mnt/c/Users/Test User/.claude"),
            None,
            false,
        );

        assert!(script.contains("WS='/mnt/c/Users/Test User/skill'"));
        assert!(script.contains("CFG='/mnt/c/Users/Test User/AppData/Local/Temp/ah.toml'"));
        // external-imports gate: repos whose root CLAUDE.md `@`-imports a file
        // outside the skill's cwd (e.g. this repo's AGENTS.md) would otherwise
        // block the master on an "Allow external CLAUDE.md file imports?" prompt.
        assert!(script.contains("hasClaudeMdExternalIncludesApproved"));
        assert!(script.contains("hasClaudeMdExternalIncludesWarningShown"));
        // pre-accepts the per-workspace folder-trust gate so the master doesn't block
        assert!(script.contains("hasTrustDialogAccepted"));
        assert!(script.contains("cd \"$WS\""));
        assert!(script.contains("ah --config \"$CFG\" start --wait"));
        assert!(script.contains("status=$?"));
        assert!(script.contains("ah start failed with exit code %s"));
        assert!(script.contains("ah --config \"$CFG\" attach master"));
    }

    #[test]
    fn wsl_payload_syncs_codex_auth_from_windows_home() {
        let script = wsl_payload_script(
            "/mnt/c/Users/Test User/skill",
            "/mnt/c/Users/Test User/AppData/Local/Temp/ah.toml",
            CodeAssistant::Codex,
            Some("/mnt/c/Users/Test User/.codex"),
            None,
            None,
            false,
        );

        assert!(script.contains("WIN_CODEX_HOME='/mnt/c/Users/Test User/.codex'"));
        assert!(script.contains("cp \"$WIN_CODEX_HOME/auth.json\" \"$HOME/.codex/auth.json\""));
        assert!(script.contains("chmod 600 \"$HOME/.codex/auth.json\""));
        assert!(script.contains("Run Codex login on Windows first"));
        assert!(script.contains("Starting Codex through ah"));
    }

    #[test]
    fn launcher_command_runs_the_payload_without_an_outer_console() {
        // ah-orchestration-design.md §10 D2: the embedded PTY runs the payload
        // itself — no PowerShell window, no terminal emulator in between.
        let script = Path::new(r"C:\Users\Test User\AppData\Local\Temp\open-claude-code.sh");
        let command = launcher_command_for_script(script);

        if cfg!(target_os = "windows") {
            assert_eq!(command.program, "wsl.exe");
            assert_eq!(command.args[0], "-e");
            assert_eq!(command.args[1], "bash");
            assert!(command.args[2].starts_with("/mnt/"));
        } else {
            assert_eq!(command.program, script.display().to_string());
            assert!(command.args.is_empty());
        }
        assert!(!command.program.contains("powershell"));
        assert!(!command.program.contains("cmd"));
    }

    #[test]
    fn cli_terminal_owner_key_is_stable_per_workspace_and_assistant() {
        // The OWNER is stable, so reopening replaces that pair's previous
        // client; the session ids minted under it are not (a remount must not
        // be able to kill the session a newer mount just started).
        let root =
            Path::new(r"D:\coding\skills\story-deconstruction-v3\subgraph\text-segmentation");
        let owner = cli_terminal_owner_key(root, CodeAssistant::Codex);

        assert!(owner.starts_with("codex-"));
        assert_eq!(owner, cli_terminal_owner_key(root, CodeAssistant::Codex));
        assert_ne!(owner, cli_terminal_owner_key(root, CodeAssistant::Claude));
        assert_ne!(
            owner,
            cli_terminal_owner_key(Path::new(r"D:\coding\skills\other"), CodeAssistant::Codex)
        );
    }

    #[test]
    fn every_launcher_enables_tmux_mouse_before_attaching() {
        // §10 D6: tmux defaults to `mouse off` and ah sets no tmux options, so
        // the wheel would scroll nothing in the embedded terminal. Each
        // launcher opts the workspace's own tmux server in, by session-path
        // discovery rather than by recomputing ah's socket hash.
        let scripts = [
            wsl_payload_script(
                "/mnt/d/skill",
                "/mnt/c/tmp/ah.toml",
                CodeAssistant::Claude,
                None,
                None,
                None,
                false,
            ),
            wsl_attach_payload_script("/mnt/c/tmp/ah.toml", "/mnt/d/skill", CodeAssistant::Claude),
            unix_code_assistant_launcher_script(
                Path::new("/tmp/skill"),
                Path::new("/tmp/ah.toml"),
                CodeAssistant::Claude,
                false,
            ),
            unix_code_assistant_attach_launcher_script(
                Path::new("/tmp/skill"),
                Path::new("/tmp/ah.toml"),
                CodeAssistant::Claude,
            ),
        ];

        for script in &scripts {
            let mouse_at = script
                .find("set-option -g mouse on")
                .unwrap_or_else(|| panic!("launcher must enable tmux mouse mode:\n{script}"));
            let attach_at = script
                .find("attach master")
                .unwrap_or_else(|| panic!("launcher must attach the master pane:\n{script}"));
            assert!(
                mouse_at < attach_at,
                "mouse mode must be set BEFORE attaching (afterwards the shell is blocked):\n{script}"
            );
            assert!(
                script.contains("list-sessions -F '#{session_path}'"),
                "the tmux server must be found by session path, never by recomputing ah's socket hash:\n{script}"
            );
            assert!(
                !script.contains("ahd-<"),
                "no hand-rolled copy of ah's socket naming:\n{script}"
            );
        }
    }

    #[test]
    fn wsl_attach_payload_only_attaches_master() {
        let script = wsl_attach_payload_script(
            "/mnt/c/Users/Test User/AppData/Local/Temp/ah.toml",
            "/mnt/d/coding/skills/text-segmentation",
            CodeAssistant::Codex,
        );

        assert!(script.contains("Attaching Codex master pane"));
        assert!(script.contains("ah --config \"$CFG\" attach master"));
        assert!(!script.contains("start --wait"));
        assert!(!script.contains("Starting Codex through ah"));
    }

    #[test]
    fn window_close_goes_through_code_assistant_shutdown_cleanup() {
        let source = include_str!("lib.rs");

        assert!(
            source.contains("tauri::WindowEvent::CloseRequested"),
            "clicking the native window close button must not bypass shutdown cleanup"
        );
        assert!(source.contains("api.prevent_close();"));
        assert!(source.contains("shutdown_application(app_handle.clone(), \"window-close\")"));
        assert!(source.contains("cleanup_registered_code_assistants(code_assistant_configs);"));
    }

    #[test]
    fn unix_launcher_runs_ah_start_then_attach_master() {
        let script = unix_code_assistant_launcher_script(
            Path::new("/tmp/skill root"),
            Path::new("/tmp/studio ah/ah.toml"),
            CodeAssistant::Claude,
            false,
        );

        assert!(script.starts_with("#!/bin/sh"));
        assert!(script.contains("cd '/tmp/skill root'"));
        assert!(script.contains("command -v ah"));
        assert!(script.contains("ah --config '/tmp/studio ah/ah.toml' start --wait"));
        assert!(script.contains("ah --config '/tmp/studio ah/ah.toml' attach master"));
    }

    #[test]
    fn unix_attach_launcher_does_not_start_ah() {
        let script = unix_code_assistant_attach_launcher_script(
            Path::new("/tmp/skill"),
            Path::new("/tmp/studio ah/ah.toml"),
            CodeAssistant::Claude,
        );

        assert!(script.starts_with("#!/bin/sh"));
        assert!(script.contains("Attaching Claude Code master pane"));
        assert!(script.contains("ah --config '/tmp/studio ah/ah.toml' attach master"));
        assert!(!script.contains("start --wait"));
    }

    #[test]
    fn invoke_handler_registers_confirm_quit_ready_command() {
        let source = include_str!("lib.rs");
        assert!(
            source.contains("confirm_quit_ready,"),
            "confirm_quit_ready must be registered in the Tauri invoke handler"
        );
    }

    /// R-F19.2 — quit-flush handshake budget is small enough to never trap a
    /// user (well under 5s) but large enough to comfortably cover the 300ms
    /// debounce + a local loopback PUT round-trip.
    #[test]
    fn quit_flush_budget_is_bounded() {
        assert!(QUIT_FLUSH_BUDGET >= Duration::from_millis(500));
        assert!(QUIT_FLUSH_BUDGET <= Duration::from_millis(5000));
        assert!(QUIT_FLUSH_POLL_INTERVAL < QUIT_FLUSH_BUDGET);
    }

    #[test]
    fn file_manager_argument_uses_the_separator_the_file_manager_accepts() {
        // Studio builds workspace paths with forward slashes. Explorer treats such
        // a path as unresolvable and opens Documents instead — silently, so the
        // only symptom is the wrong folder appearing.
        let mixed = Path::new("D:/coding/skills/demo/.workspace/import_files");

        // Compared as text, not as PathBuf: on Windows both separators are path
        // separators, so two PathBufs differing only in slash direction are equal
        // and an assertion on them passes without the conversion ever happening.
        // What reaches Explorer is the argument string, so that is what is checked.
        let rendered = file_manager_argument(mixed).to_string_lossy().into_owned();

        if cfg!(target_os = "windows") {
            assert_eq!(rendered, r"D:\coding\skills\demo\.workspace\import_files");
        } else {
            assert_eq!(rendered, "D:/coding/skills/demo/.workspace/import_files");
        }
    }

    #[test]
    fn existing_path_rejects_missing_paths() {
        let missing = temp_path("missing-path");
        let _ = std::fs::remove_dir_all(&missing);

        let error = existing_path(&missing.display().to_string()).expect_err("missing path");

        assert!(error.contains("path does not exist"));
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn macos_menu_spec_restores_default_edit_menu() {
        assert_eq!(
            macos_edit_menu_labels(),
            &["Undo", "Redo", "Cut", "Copy", "Paste", "Select All"]
        );
        assert!(
            macos_edit_menu_labels().contains(&"Select All"),
            "Select All should remain available from the native Edit menu"
        );
        assert!(
            macos_edit_menu_labels().contains(&"Copy"),
            "Copy should remain available from the native Edit menu"
        );
    }
}
