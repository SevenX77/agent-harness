mod native_fs;
mod sidecar;

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::io::{BufRead, BufReader};
use std::path::Path;
use std::path::PathBuf;
use std::process::{Child, Command, Output, Stdio};
use std::sync::{
    atomic::{AtomicBool, Ordering},
    mpsc, Arc, Mutex,
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
const AH_SHUTDOWN_POLL_INTERVAL: Duration = Duration::from_millis(150);
const AH_SHUTDOWN_POLL_ATTEMPTS: usize = 12;

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
    status_snapshots: Mutex<BTreeMap<PathBuf, AhLifecycleSnapshot>>,
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
#[serde(rename_all = "camelCase")]
struct CodeAssistantStatus {
    claude: bool,
    codex: bool,
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

fn existing_directory(path: &str) -> Result<PathBuf, String> {
    let target = existing_path(path)?;
    if !target.is_dir() {
        return Err(format!("path is not a directory: {}", target.display()));
    }
    Ok(target)
}

fn find_ah_config(start_dir: &Path) -> Option<PathBuf> {
    let current = if start_dir.is_file() {
        start_dir.parent()?
    } else {
        start_dir
    };
    let candidate = current.join("ah.toml");
    candidate.is_file().then_some(candidate)
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

fn studio_ah_config_path(workspace_root: &Path) -> PathBuf {
    workspace_root.join("ah.toml")
}

fn studio_ah_temp_root() -> PathBuf {
    std::env::temp_dir().join("skill-studio-ah")
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

    fn master_cmd(self) -> String {
        match self {
            Self::Claude => claude_master_cmd(),
            Self::Codex => codex_master_cmd(),
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
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum CodeAssistantOpenDecision {
    StartFresh,
    AttachRequested,
    RejectOtherActive,
    CleanupStale,
}

#[derive(Clone, Debug)]
struct AhRuntimeProbe {
    snapshot: AhLifecycleSnapshot,
    tmux_socket_label: Option<String>,
    tmux_sessions: Vec<String>,
    session_ids: Vec<String>,
}

impl AhRuntimeProbe {
    fn empty() -> Self {
        Self {
            snapshot: AhLifecycleSnapshot::new(false, false, false),
            tmux_socket_label: None,
            tmux_sessions: Vec::new(),
            session_ids: Vec::new(),
        }
    }
}

fn code_assistant_lifecycle_is_active(snapshot: AhLifecycleSnapshot) -> bool {
    snapshot.ahd_has_inventory && snapshot.master_tmux_alive
}

fn reconcile_code_assistant_lifecycle(
    snapshot: AhLifecycleSnapshot,
) -> CodeAssistantLifecycleAction {
    if code_assistant_lifecycle_is_active(snapshot) {
        CodeAssistantLifecycleAction::AttachExisting
    } else if snapshot.ahd_has_inventory || snapshot.master_tmux_alive || snapshot.worker_tmux_alive
    {
        CodeAssistantLifecycleAction::CleanupStale
    } else {
        CodeAssistantLifecycleAction::StartFresh
    }
}

fn code_assistant_shutdown_is_complete(snapshot: AhLifecycleSnapshot) -> bool {
    !snapshot.ahd_has_inventory && !snapshot.master_tmux_alive && !snapshot.worker_tmux_alive
}

#[derive(Deserialize)]
struct AhRuntimeEventLine {
    ahd_has_inventory: bool,
    master_tmux_alive: bool,
    worker_tmux_alive: bool,
}

fn lifecycle_snapshot_from_ah_event(line: &str) -> Option<AhLifecycleSnapshot> {
    let event: AhRuntimeEventLine = serde_json::from_str(line).ok()?;
    Some(AhLifecycleSnapshot::new(
        event.ahd_has_inventory,
        event.master_tmux_alive,
        event.worker_tmux_alive,
    ))
}

fn decide_code_assistant_open(
    requested: Option<AhLifecycleSnapshot>,
    others: &[AhLifecycleSnapshot],
) -> CodeAssistantOpenDecision {
    let requested_action = requested
        .map(reconcile_code_assistant_lifecycle)
        .unwrap_or(CodeAssistantLifecycleAction::StartFresh);
    let other_actions = others
        .iter()
        .copied()
        .map(reconcile_code_assistant_lifecycle)
        .collect::<Vec<_>>();
    let has_stale = requested_action == CodeAssistantLifecycleAction::CleanupStale
        || other_actions
            .iter()
            .any(|action| *action == CodeAssistantLifecycleAction::CleanupStale);
    let other_active_count = other_actions
        .iter()
        .filter(|action| **action == CodeAssistantLifecycleAction::AttachExisting)
        .count();

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

    fn combined_output(&self) -> String {
        if self.stderr.is_empty() {
            return self.stdout.clone();
        }
        if self.stdout.is_empty() {
            return self.stderr.clone();
        }
        format!("{}\n{}", self.stdout, self.stderr)
    }
}

/// Prompt the ah-managed interactive master auto-runs on launch, so opening a
/// skill in Claude/Codex greets the user with a self-report (who it is / which
/// workspace + skill / what it can do) instead of an empty prompt. Kept free of
/// single/double quotes so it embeds cleanly in both the TOML `cmd` string and
/// the single-quoted shell argument that carries it.
const MOIRAI_MASTER_REPORT_PROMPT: &str = "用中文简短汇报当前状态(每点一行),然后停下等我:1) 你是谁 2) 当前工作目录 cwd 是什么、根据目录里的文件这是哪个 skill 3) 你能帮我做什么。";

const STUDIO_AH_MANAGED_MARKER_PREFIX: &str = "<!-- studio-ah-managed hash:";
const STUDIO_AH_MANAGED_MARKER_SUFFIX: &str = " -->";
const STUDIO_AH_CONFIG_MARKER_PREFIX: &str = "# studio-ah-managed hash:";
const STUDIO_AH_CONFIG_MARKER_SUFFIX: &str = "";

const DOMAIN_ANALYSIS_SKILL: &str =
    include_str!("../../backend/app/prompts/skills/domain-analysis/SKILL.md");
const GRAPH_DESIGN_SKILL: &str =
    include_str!("../../backend/app/prompts/skills/graph-design/SKILL.md");
const AGENT_PROMPT_DESIGN_SKILL: &str =
    include_str!("../../backend/app/prompts/skills/agent-prompt-design/SKILL.md");
const COMPILE_ERROR_REPAIR_SKILL: &str =
    include_str!("../../backend/app/prompts/skills/compile-error-repair/SKILL.md");

const MOIRAI_MASTER_RULES: &str = r#"# 你是 MoirAI（莫伊莱）

## 身份锚点

- 你是 Moirai 的 Studio 化身：三位命运女神合成的一体，陪一条 skill 从意图、结构、修顺走到终判。
- 背景参考（Wikipedia）：https://en.wikipedia.org/wiki/Moirai
- 只在用户询问名字、神话背景或角色来源时，才按上面的链接和这一句锚点展开；日常协作不讲背景故事。

## 内部操作协议

- 先判断用户请求处在哪一段：需求澄清与设计、编译与修复、整体评估，或需要反问。
- 需要设计时，用 `ah ask clotho "<任务包>" --wait`；需要编译或修复时，用 `ah ask lachesis "<任务包>" --wait`；需要 predict/run、trace 观察和终判时，用 `ah ask atropos "<任务包>" --wait`。
- 给用户只汇总结论、取舍、下一步，不转述内部流水账。
- 不为了让错误消失而补丁式绕过；先定位坏状态为什么可能存在，再决定改哪一层。
"#;

const CLOTHO_RULES: &str = r#"# 你是 Clotho（克洛托）

## 身份锚点

- 你是纺线的手：把散落意图整理成可落地的 graph skill 结构。
- 背景参考（Wikipedia）：https://en.wikipedia.org/wiki/Clotho
- 只在用户询问名字、神话背景或角色来源时，才按上面的链接和这一句锚点展开；日常协作不讲背景故事。

## 内部操作协议

- 先读全材料，再抽结构；不要凭行业常识脑补事实。
- 输出先给结构，再给取舍：实体、流程、规则、术语、未决问题，以及这些内容如何映射到 graph。
- phase 拆分必须能被验证；确定性逻辑优先落 Python/action，只有理解、判断、生成才交给 agent。
- 设计不能停在口号；要落到 `GRAPH.md`、phase 目录、io schema 和后续可编译路径。
- 交付给 Lachesis 前，明确哪些地方需要编译验证、哪些假设需要用户确认。
"#;

const LACHESIS_RULES: &str = r#"# 你是 Lachesis（拉刻西斯）

## 身份锚点

- 你是量线的手：把已经纺出的 skill 量准、修顺，直到契约和实现对齐。
- 背景参考（Wikipedia）：https://en.wikipedia.org/wiki/Lachesis
- 只在用户询问名字、神话背景或角色来源时，才按上面的链接和这一句锚点展开；日常协作不讲背景故事。

## 内部操作协议

- 先拿完整编译/lint 错误，不凭半截报错猜。
- 以挂载的 skill 语法和 compile rules 为准，不靠记忆复述。
- 读涉事文件全文，再改根因；三处命名、DAG、io schema、phase 模式文件、action 签名和 frontmatter 都要按契约量。
- 一次只修一类根因；修完说明改了什么、为什么这是根因、下一轮还剩什么。
- 不做兼容垫片、双格式读取、try/catch 吞坏状态或事后修数据。
"#;

const ATROPOS_RULES: &str = r#"# 你是 Atropos（阿特罗波斯）

## 身份锚点

- 你是剪线的手：用 predict/run、trace、golden 或目标标准给整张图下终判。
- 背景参考（Wikipedia）：https://en.wikipedia.org/wiki/Atropos
- 只在用户询问名字、神话背景或角色来源时，才按上面的链接和这一句锚点展开；日常协作不讲背景故事。

## 内部操作协议

- 先明确验收标准：用户要什么结果、哪些输出字段可比对、哪些失败是阻断。
- 评估要基于真实运行、trace、输出和错误，而不是主观感觉。
- 结论分为通过、需要设计返工、需要编译修复、需要用户补材料；不要把不确定包装成通过。
- 发现结构性问题交回 Clotho；发现契约/编译/实现问题交回 Lachesis。
- 给 MoirAI 的回报要短：证据、判断、下一步。
"#;

const EVAL_JUDGEMENT_SKILL: &str = r#"---
name: eval-judgement
description: 对 graph_skill 的 predict/run 结果做终判：读取输出、trace、错误与目标标准，给出通过/返工判断和下一步归因。
---

# Eval Judgement

目标：把一次 skill 运行结果变成可执行的终判，而不是泛泛评价。

## 流程

1. 明确验收标准：用户目标、golden、io schema、关键输出字段和阻断条件。
2. 读取真实证据：predict/run 输出、trace、错误、日志、生成文件差异。
3. 分类结论：
   - `pass`：满足验收标准，无阻断问题。
   - `design_rework`：phase 拆分、DAG、io 或任务边界错了，交回 Clotho。
   - `repair_needed`：编译、schema、action、prompt 稳定性或实现契约错了，交回 Lachesis。
   - `needs_user_input`：缺材料或验收标准不明确。
4. 输出短结论：证据、判断、归因、下一步。

## 反模式

- 没有运行证据就给通过。
- 把多个根因混成一段散文。
- 只说“效果不好”，不指出该回到设计、修复还是补材料。
"#;

struct StudioAhManagedFile {
    relative_path: &'static str,
    body: &'static str,
}

const STUDIO_AH_MANAGED_FILES: &[StudioAhManagedFile] = &[
    StudioAhManagedFile {
        relative_path: ".ah/rules/master.md",
        body: MOIRAI_MASTER_RULES,
    },
    StudioAhManagedFile {
        relative_path: ".ah/rules/clotho.md",
        body: CLOTHO_RULES,
    },
    StudioAhManagedFile {
        relative_path: ".ah/rules/lachesis.md",
        body: LACHESIS_RULES,
    },
    StudioAhManagedFile {
        relative_path: ".ah/rules/atropos.md",
        body: ATROPOS_RULES,
    },
    StudioAhManagedFile {
        relative_path: ".ah/skills/domain-analysis/SKILL.md",
        body: DOMAIN_ANALYSIS_SKILL,
    },
    StudioAhManagedFile {
        relative_path: ".ah/skills/graph-design/SKILL.md",
        body: GRAPH_DESIGN_SKILL,
    },
    StudioAhManagedFile {
        relative_path: ".ah/skills/agent-prompt-design/SKILL.md",
        body: AGENT_PROMPT_DESIGN_SKILL,
    },
    StudioAhManagedFile {
        relative_path: ".ah/skills/compile-error-repair/SKILL.md",
        body: COMPILE_ERROR_REPAIR_SKILL,
    },
    StudioAhManagedFile {
        relative_path: ".ah/skills/eval-judgement/SKILL.md",
        body: EVAL_JUDGEMENT_SKILL,
    },
];

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
fn claude_master_cmd() -> String {
    let prompt = sh_single_quote_str(MOIRAI_MASTER_REPORT_PROMPT);
    let script = format!(
        "set -e; export SYSTEMD_LOG_LEVEL=err; claude_real=$(command -v claude || true); if [ -n \"$claude_real\" ] && [ ! -x \"$claude_real\" ]; then claude_real=\"\"; fi; if [ -z \"$claude_real\" ] && [ -n \"${{STUDIO_AH_HOST_HOME:-}}\" ] && [ -x \"$STUDIO_AH_HOST_HOME/.local/bin/claude\" ]; then claude_real=\"$STUDIO_AH_HOST_HOME/.local/bin/claude\"; fi; if [ -z \"$claude_real\" ]; then printf '%s\\n' 'claude CLI was not found on PATH.' >&2; exit 127; fi; mkdir -p \"$HOME/.local/bin\"; if [ \"$claude_real\" != \"$HOME/.local/bin/claude\" ]; then ln -sfn \"$claude_real\" \"$HOME/.local/bin/claude\"; fi; if [ -n \"${{STUDIO_AH_HOST_HOME:-}}\" ] && [ -f \"$STUDIO_AH_HOST_HOME/.claude.json\" ]; then ln -sfn \"$STUDIO_AH_HOST_HOME/.claude.json\" \"$HOME/.claude.json\"; fi; export IS_SANDBOX=1; exec \"$claude_real\" --dangerously-skip-permissions {prompt}"
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
fn codex_master_cmd() -> String {
    let prompt = sh_single_quote_str(MOIRAI_MASTER_REPORT_PROMPT);
    let script = format!(
        "set -e; export SYSTEMD_LOG_LEVEL=err; codex_real=$(command -v codex || true); if [ -n \"$codex_real\" ] && [ ! -x \"$codex_real\" ]; then codex_real=\"\"; fi; if [ -z \"$codex_real\" ] && [ -n \"${{STUDIO_AH_HOST_HOME:-}}\" ] && [ -x \"$STUDIO_AH_HOST_HOME/.local/bin/codex\" ]; then codex_real=\"$STUDIO_AH_HOST_HOME/.local/bin/codex\"; fi; if [ -z \"$codex_real\" ]; then printf '%s\\n' 'codex CLI was not found on PATH.' >&2; exit 127; fi; mkdir -p \"$HOME/.local/bin\" \"$HOME/.codex\" \"$HOME/.agents\"; if [ \"$codex_real\" != \"$HOME/.local/bin/codex\" ]; then ln -sfn \"$codex_real\" \"$HOME/.local/bin/codex\"; fi; if [ -n \"${{STUDIO_AH_HOST_HOME:-}}\" ] && [ -f \"$STUDIO_AH_HOST_HOME/.codex/auth.json\" ]; then ln -sfn \"$STUDIO_AH_HOST_HOME/.codex/auth.json\" \"$HOME/.codex/auth.json\"; fi; codex_project_key=$(printf '%s' \"$PWD\" | sed 's/\\\\/\\\\\\\\/g; s/\"/\\\\\"/g'); codex_trust_header=\"[projects.\\\"$codex_project_key\\\"]\"; if ! grep -Fqx \"$codex_trust_header\" \"$HOME/.codex/config.toml\" 2>/dev/null; then {{ if [ -s \"$HOME/.codex/config.toml\" ]; then printf '\\n'; fi; printf '%s\\ntrust_level = \"trusted\"\\n' \"$codex_trust_header\"; }} >> \"$HOME/.codex/config.toml\"; fi; if [ -f \"$PWD/.ah/rules/master.md\" ]; then ln -sfn \"$PWD/.ah/rules/master.md\" \"$HOME/.codex/AGENTS.md\"; fi; if [ -d \"$PWD/.ah/skills\" ]; then rm -rf \"$HOME/.agents/skills\"; ln -sfn \"$PWD/.ah/skills\" \"$HOME/.agents/skills\"; fi; exec \"$codex_real\" --dangerously-bypass-approvals-and-sandbox --dangerously-bypass-hook-trust {prompt}"
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

fn studio_managed_toml_marker(body: &str) -> String {
    format!(
        "{STUDIO_AH_CONFIG_MARKER_PREFIX}{}{STUDIO_AH_CONFIG_MARKER_SUFFIX}",
        sha256_hex(body)
    )
}

fn with_studio_managed_toml_marker(body: &str) -> String {
    format!("{}\n{body}", studio_managed_toml_marker(body))
}

fn extract_studio_managed_toml_hash(content: &str) -> Option<&str> {
    content.lines().find_map(|line| {
        let trimmed = line.trim();
        let hash = trimmed.strip_prefix(STUDIO_AH_CONFIG_MARKER_PREFIX)?;
        hash.strip_suffix(STUDIO_AH_CONFIG_MARKER_SUFFIX)
    })
}

fn strip_studio_managed_toml_marker(content: &str) -> String {
    content
        .split_inclusive('\n')
        .filter(|line| !line.trim().starts_with(STUDIO_AH_CONFIG_MARKER_PREFIX))
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

fn write_studio_managed_toml_file(path: &Path, body: &str) -> Result<(), String> {
    if path.exists() {
        if !path.is_file() {
            return Err(format!(
                "refusing to overwrite non-file ah config: {}",
                path.display()
            ));
        }
        let existing = std::fs::read_to_string(path).map_err(|error| {
            format!(
                "failed to read existing ah config {}: {error}",
                path.display()
            )
        })?;
        let previous_hash = extract_studio_managed_toml_hash(&existing).ok_or_else(|| {
            format!(
                "refusing to overwrite unmanaged ah config: {}",
                path.display()
            )
        })?;
        let existing_body = strip_studio_managed_toml_marker(&existing);
        let actual_hash = sha256_hex(&existing_body);
        if previous_hash != actual_hash {
            return Err(format!(
                "refusing to overwrite modified Studio-managed ah config: {}",
                path.display()
            ));
        }
    }
    let parent = path
        .parent()
        .ok_or_else(|| format!("cannot resolve ah config parent: {}", path.display()))?;
    std::fs::create_dir_all(parent).map_err(|error| {
        format!(
            "failed to create ah config dir {}: {error}",
            parent.display()
        )
    })?;
    std::fs::write(path, with_studio_managed_toml_marker(body))
        .map_err(|error| format!("failed to write ah config {}: {error}", path.display()))
}

fn prepare_studio_ah_workspace(workspace_root: &Path) -> Result<(), String> {
    for file in STUDIO_AH_MANAGED_FILES {
        let path = studio_ah_file_path(workspace_root, file.relative_path);
        write_studio_managed_file(&path, file.body)?;
    }
    Ok(())
}

fn toml_string(value: &str) -> String {
    format!("\"{}\"", value.replace('\\', "\\\\").replace('"', "\\\""))
}

fn master_provider_from_ah_config(config_path: &Path) -> Option<String> {
    let content = std::fs::read_to_string(config_path).ok()?;
    let mut in_master = false;
    for line in content.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with('[') && trimmed.ends_with(']') {
            in_master = trimmed == "[master]";
            continue;
        }
        if !in_master {
            continue;
        }
        let Some(value) = trimmed.strip_prefix("provider") else {
            continue;
        };
        let value = value.trim_start();
        let value = value.strip_prefix('=')?.trim();
        let value = value.strip_prefix('"')?;
        let value = value.strip_suffix('"')?;
        return Some(value.to_string());
    }
    None
}

fn ah_config_matches_assistant(config_path: &Path, assistant: CodeAssistant) -> bool {
    master_provider_from_ah_config(config_path).as_deref() == Some(assistant.provider())
}

fn studio_ah_config_content(assistant: CodeAssistant) -> String {
    let provider = assistant.provider();
    format!(
        "version = \"1\"\n\n[master]\nenabled = true\nprovider = {provider_toml}\ncmd = {cmd}\nreadiness_timeout_s = 180\nwindow_size = \"follow\"\n\n[agents.clotho]\nprovider = {provider_toml}\nskills = [\"domain-analysis\", \"graph-design\", \"agent-prompt-design\"]\n\n[agents.lachesis]\nprovider = {provider_toml}\nskills = [\"compile-error-repair\"]\n\n[agents.atropos]\nprovider = {provider_toml}\nskills = [\"eval-judgement\"]\n",
        provider_toml = toml_string(provider),
        cmd = toml_string(&assistant.master_cmd())
    )
}

fn ah_config_for_workspace(
    workspace_root: &Path,
    assistant: CodeAssistant,
) -> Result<PathBuf, String> {
    let config = studio_ah_config_path(workspace_root);
    if config.is_file() {
        let existing = std::fs::read_to_string(&config)
            .map_err(|error| format!("failed to read ah config {}: {error}", config.display()))?;
        if extract_studio_managed_toml_hash(&existing).is_none() {
            return Ok(config);
        }
    }
    prepare_studio_ah_workspace(workspace_root)?;
    write_studio_managed_toml_file(&config, &studio_ah_config_content(assistant))?;
    Ok(config)
}

fn ah_config_for_status(workspace_root: &Path, assistant: CodeAssistant) -> Option<PathBuf> {
    let config = find_ah_config(workspace_root)?;
    ah_config_matches_assistant(&config, assistant).then_some(config)
}

fn command_result(mut command: Command, label: &str) -> Result<CommandResult, String> {
    command
        .output()
        .map(CommandResult::from_output)
        .map_err(|error| format!("failed to run {label}: {error}"))
}

fn run_ah_config_command_output(
    config_path: &Path,
    ah_args: &[&str],
) -> Result<CommandResult, String> {
    if cfg!(target_os = "windows") {
        let mut command = Command::new("wsl.exe");
        let args = ah_args
            .iter()
            .map(|arg| sh_single_quote_str(arg))
            .collect::<Vec<_>>()
            .join(" ");
        let script = format!(
            "export PATH=\"$HOME/.cargo/bin:$HOME/.local/bin:$PATH\"; export SYSTEMD_LOG_LEVEL=err; ah --config {} {}",
            sh_single_quote_str(&windows_path_to_wsl(config_path)),
            args
        );
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
        let script = format!(
            "export PATH=\"$HOME/.cargo/bin:$HOME/.local/bin:$PATH\"; export SYSTEMD_LOG_LEVEL=err; ah --config {} events --format json",
            sh_single_quote_str(&windows_path_to_wsl(config_path))
        );
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

fn run_tmux_socket_command(
    socket_label: &str,
    tmux_args: &[&str],
) -> Result<CommandResult, String> {
    if !tmux_socket_label_is_safe(socket_label) {
        return Err(format!("unsafe tmux socket label: {socket_label}"));
    }

    if cfg!(target_os = "windows") {
        let mut command = Command::new("wsl.exe");
        let args = tmux_args
            .iter()
            .map(|arg| sh_single_quote_str(arg))
            .collect::<Vec<_>>()
            .join(" ");
        let script = format!(
            "export PATH=\"$HOME/.cargo/bin:$HOME/.local/bin:$PATH\"; export SYSTEMD_LOG_LEVEL=err; tmux -L {} {}",
            sh_single_quote_str(socket_label),
            args
        );
        command.args(["-e", "bash", "-lc", &script]);
        return command_result(command, "tmux");
    }

    let mut command = Command::new("tmux");
    command.env("SYSTEMD_LOG_LEVEL", "err");
    command.arg("-L").arg(socket_label).args(tmux_args);
    command_result(command, "tmux")
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

fn tmux_session_is_master(session: &str) -> bool {
    session.starts_with("master_")
}

fn tmux_session_is_worker(session: &str) -> bool {
    session.starts_with("agent_") || session.starts_with("worker_")
}

fn tmux_session_is_ah_managed(session: &str) -> bool {
    tmux_session_is_master(session) || tmux_session_is_worker(session)
}

fn list_tmux_sessions(socket_label: &str) -> Vec<String> {
    let Ok(result) =
        run_tmux_socket_command(socket_label, &["list-sessions", "-F", "#{session_name}"])
    else {
        return Vec::new();
    };
    if !result.success {
        return Vec::new();
    }
    result
        .stdout
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .map(str::to_string)
        .collect()
}

fn kill_tmux_session(socket_label: &str, session_name: &str) -> Result<bool, String> {
    run_tmux_socket_command(socket_label, &["kill-session", "-t", session_name])
        .map(|result| result.success)
}

fn inspect_ah_runtime(config_path: &Path, tmux_socket_hint: Option<&str>) -> AhRuntimeProbe {
    let Ok(ps_result) = run_ah_config_command_output(config_path, &["ps"]) else {
        return AhRuntimeProbe::empty();
    };
    let ps_output = ps_result.combined_output();
    let tmux_socket_label = extract_tmux_socket_label(&ps_output).or_else(|| {
        tmux_socket_hint
            .filter(|label| tmux_socket_label_is_safe(label))
            .map(str::to_string)
    });
    let tmux_sessions = tmux_socket_label
        .as_deref()
        .map(list_tmux_sessions)
        .unwrap_or_default();
    let has_inventory = ps_result.success && ah_ps_output_has_inventory(&ps_output);
    let session_ids = extract_ah_session_ids(&ps_output);
    let snapshot = AhLifecycleSnapshot::new(
        has_inventory,
        tmux_sessions
            .iter()
            .any(|session| tmux_session_is_master(session)),
        tmux_sessions
            .iter()
            .any(|session| tmux_session_is_worker(session)),
    );
    AhRuntimeProbe {
        snapshot,
        tmux_socket_label,
        tmux_sessions,
        session_ids,
    }
}

fn force_cleanup_ah_runtime(config_path: &Path, probe: &AhRuntimeProbe) {
    for session_id in &probe.session_ids {
        match run_ah_config_command(config_path, &["kill", "--session", session_id, "--force"]) {
            Ok(true) => log::info!(
                "phase=code-assistant-cleanup action=ah-kill-session-ok config={} session_id={session_id}",
                config_path.display()
            ),
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

    if let Some(socket_label) = probe.tmux_socket_label.as_deref() {
        for session in probe
            .tmux_sessions
            .iter()
            .filter(|session| tmux_session_is_ah_managed(session))
        {
            match kill_tmux_session(socket_label, session) {
                Ok(true) => log::info!(
                    "phase=code-assistant-cleanup action=tmux-kill-session-ok socket={socket_label} session={session}"
                ),
                Ok(false) => log::info!(
                    "phase=code-assistant-cleanup action=tmux-kill-session-skip socket={socket_label} session={session}"
                ),
                Err(error) => log::warn!(
                    "phase=code-assistant-cleanup action=tmux-kill-session-failed socket={socket_label} session={session} error={error}"
                ),
            }
        }
    }
}

fn wait_for_code_assistant_shutdown(
    config_path: &Path,
    tmux_socket_hint: Option<&str>,
) -> AhRuntimeProbe {
    let mut last_probe = inspect_ah_runtime(config_path, tmux_socket_hint);
    if code_assistant_shutdown_is_complete(last_probe.snapshot) {
        return last_probe;
    }

    for _ in 0..AH_SHUTDOWN_POLL_ATTEMPTS {
        std::thread::sleep(AH_SHUTDOWN_POLL_INTERVAL);
        let hint = last_probe.tmux_socket_label.as_deref().or(tmux_socket_hint);
        last_probe = inspect_ah_runtime(config_path, hint);
        if code_assistant_shutdown_is_complete(last_probe.snapshot) {
            break;
        }
    }
    last_probe
}

fn cleanup_code_assistant_config(config_path: &Path) -> Result<bool, String> {
    let before = inspect_ah_runtime(config_path, None);
    if code_assistant_shutdown_is_complete(before.snapshot) {
        return Ok(false);
    }

    let stop_succeeded = stop_ah_config(config_path)?;
    let after_stop =
        wait_for_code_assistant_shutdown(config_path, before.tmux_socket_label.as_deref());
    if code_assistant_shutdown_is_complete(after_stop.snapshot) {
        return Ok(stop_succeeded || before.snapshot != after_stop.snapshot);
    }

    force_cleanup_ah_runtime(config_path, &after_stop);
    let fallback_hint = after_stop
        .tmux_socket_label
        .as_deref()
        .or(before.tmux_socket_label.as_deref());
    let after_force = wait_for_code_assistant_shutdown(config_path, fallback_hint);
    if code_assistant_shutdown_is_complete(after_force.snapshot) {
        return Ok(true);
    }

    Err(format!(
        "failed to close ah completely: ahd={}, master_tmux={}, worker_tmux={}",
        after_force.snapshot.ahd_has_inventory,
        after_force.snapshot.master_tmux_alive,
        after_force.snapshot.worker_tmux_alive
    ))
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
}

fn cleanup_workspace_code_assistants(
    workspace_root: &Path,
) -> Result<CodeAssistantCleanupResult, String> {
    let configs = workspace_code_assistant_configs(workspace_root);
    let mut closed_any = false;
    for config in &configs {
        closed_any |= cleanup_code_assistant_config(config)?;
    }
    Ok(CodeAssistantCleanupResult {
        configs,
        closed_any,
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
) -> BTreeMap<PathBuf, AhLifecycleSnapshot> {
    let snapshots = state
        .status_snapshots
        .lock()
        .expect("code assistant status snapshots poisoned");
    specs
        .keys()
        .filter_map(|config| {
            snapshots
                .get(config)
                .map(|snapshot| (config.clone(), *snapshot))
        })
        .collect()
}

fn code_assistant_status_from_snapshots(
    specs: &BTreeMap<PathBuf, CodeAssistantStatusSpec>,
    snapshots: &BTreeMap<PathBuf, AhLifecycleSnapshot>,
) -> CodeAssistantStatus {
    let mut status = CodeAssistantStatus {
        claude: false,
        codex: false,
    };
    for (config, spec) in specs {
        let active = snapshots
            .get(config)
            .copied()
            .map(code_assistant_lifecycle_is_active)
            .unwrap_or(false);
        if !active {
            continue;
        }
        match spec.assistant {
            CodeAssistant::Claude => status.claude = true,
            CodeAssistant::Codex => status.codex = true,
        }
    }
    if status.claude {
        status.codex = false;
    }
    status
}

fn workspace_status_requires_cleanup(
    specs: &BTreeMap<PathBuf, CodeAssistantStatusSpec>,
    snapshots: &BTreeMap<PathBuf, AhLifecycleSnapshot>,
) -> bool {
    let has_stale = snapshots.values().any(|snapshot| {
        reconcile_code_assistant_lifecycle(*snapshot) == CodeAssistantLifecycleAction::CleanupStale
    });
    let active_count = specs
        .keys()
        .filter(|config| {
            snapshots
                .get(*config)
                .copied()
                .map(code_assistant_lifecycle_is_active)
                .unwrap_or(false)
        })
        .count();
    has_stale || active_count > 1
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

fn clear_status_snapshots_for_workspace(state: &CodeAssistantRuntimeState, workspace_root: &Path) {
    let configs = status_specs_for_workspace(state, workspace_root)
        .keys()
        .cloned()
        .collect::<BTreeSet<_>>();
    state
        .status_snapshots
        .lock()
        .expect("code assistant status snapshots poisoned")
        .retain(|config, _| !configs.contains(config));
}

fn handle_code_assistant_status_snapshot(
    app: &tauri::AppHandle,
    config_path: &Path,
    snapshot: AhLifecycleSnapshot,
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

    let specs = status_specs_for_workspace(&state, &workspace_root);
    let snapshots = snapshots_for_configs(&state, &specs);
    if workspace_status_requires_cleanup(&specs, &snapshots) {
        match cleanup_workspace_code_assistants(&workspace_root) {
            Ok(cleanup) => {
                state
                    .configs
                    .lock()
                    .expect("code assistant state poisoned")
                    .retain(|registered_config| !cleanup.configs.contains(registered_config));
                clear_status_snapshots_for_workspace(&state, &workspace_root);
            }
            Err(error) => {
                log::warn!(
                    "phase=code-assistant-status action=cleanup-failed workspace={} error={error}",
                    workspace_root.display()
                );
            }
        }
    }

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

fn start_code_assistant_status_stream(
    app: tauri::AppHandle,
    config_path: PathBuf,
) -> Result<CodeAssistantStatusStream, String> {
    let mut child = spawn_ah_events_command(&config_path)?;
    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "ah events did not expose stdout".to_string())?;
    let stop = Arc::new(AtomicBool::new(false));
    let child_slot = Arc::new(Mutex::new(Some(child)));
    let thread_stop = Arc::clone(&stop);
    let thread_child = Arc::clone(&child_slot);
    std::thread::spawn(move || {
        let reader = BufReader::new(stdout);
        for line in reader.lines() {
            if thread_stop.load(Ordering::SeqCst) {
                break;
            }
            match line {
                Ok(line) => {
                    if let Some(snapshot) = lifecycle_snapshot_from_ah_event(&line) {
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
        if !thread_stop.load(Ordering::SeqCst) {
            if let Some(state) = app.try_state::<CodeAssistantRuntimeState>() {
                let workspace_root = {
                    let specs = state
                        .status_specs
                        .lock()
                        .expect("code assistant status specs poisoned");
                    specs
                        .get(&config_path)
                        .map(|spec| spec.workspace_root.clone())
                };
                state
                    .status_streams
                    .lock()
                    .expect("code assistant status streams poisoned")
                    .remove(&config_path);
                state
                    .status_snapshots
                    .lock()
                    .expect("code assistant status snapshots poisoned")
                    .remove(&config_path);
                if let Some(workspace_root) = workspace_root {
                    emit_code_assistant_status_for_workspace(&app, &state, &workspace_root);
                }
            }
            log::warn!(
                "phase=code-assistant-status action=events-exited config={}",
                config_path.display()
            );
        }
    });
    Ok(CodeAssistantStatusStream {
        stop,
        child: child_slot,
    })
}

fn ensure_code_assistant_status_streams_for_workspace(
    app: &tauri::AppHandle,
    state: &CodeAssistantRuntimeState,
    workspace_root: &Path,
) -> Result<(), String> {
    let next_specs = next_status_specs_for_workspace(state, workspace_root);
    let next_configs = next_specs.keys().cloned().collect::<BTreeSet<_>>();
    let stale_streams = {
        let specs = status_specs_for_workspace(state, workspace_root);
        specs
            .keys()
            .filter(|config| !next_configs.contains(*config))
            .cloned()
            .collect::<Vec<_>>()
    };
    for config in stale_streams {
        if let Some(stream) = state
            .status_streams
            .lock()
            .expect("code assistant status streams poisoned")
            .remove(&config)
        {
            stop_code_assistant_status_stream(stream);
        }
        state
            .status_specs
            .lock()
            .expect("code assistant status specs poisoned")
            .remove(&config);
        state
            .status_snapshots
            .lock()
            .expect("code assistant status snapshots poisoned")
            .remove(&config);
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

    for config in next_configs {
        let should_start = {
            let streams = state
                .status_streams
                .lock()
                .expect("code assistant status streams poisoned");
            !streams.contains_key(&config)
        };
        if should_start {
            let stream = start_code_assistant_status_stream(app.clone(), config.clone())?;
            let mut streams = state
                .status_streams
                .lock()
                .expect("code assistant status streams poisoned");
            if streams.contains_key(&config) {
                stop_code_assistant_status_stream(stream);
            } else {
                streams.insert(config, stream);
            }
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

fn unwatch_code_assistant_status_streams_for_workspace(
    state: &CodeAssistantRuntimeState,
    workspace_root: &Path,
) {
    let configs = status_specs_for_workspace(state, workspace_root)
        .keys()
        .cloned()
        .collect::<Vec<_>>();
    for config in configs {
        if let Some(stream) = state
            .status_streams
            .lock()
            .expect("code assistant status streams poisoned")
            .remove(&config)
        {
            stop_code_assistant_status_stream(stream);
        }
        state
            .status_specs
            .lock()
            .expect("code assistant status specs poisoned")
            .remove(&config);
        state
            .status_snapshots
            .lock()
            .expect("code assistant status snapshots poisoned")
            .remove(&config);
    }
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
        match cleanup_code_assistant_config(&config) {
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

fn powershell_single_quote_str(value: &str) -> String {
    format!("'{}'", value.replace('\'', "''"))
}

fn sh_single_quote_str(value: &str) -> String {
    format!("'{}'", value.replace('\'', "'\\''"))
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

/// The bash payload ah + claude run inside WSL. It pre-accepts the onboarding
/// gates (see `CLAUDE_ONBOARDING_PRESEED_PY`) so the interactive master reaches
/// its prompt instead of blocking, then `ah start`s and attaches the master —
/// all in ONE wsl session so the interactive attach holds the distro alive and
/// the master persists.
fn wsl_payload_script(
    wsl_workspace: &str,
    wsl_config: &str,
    assistant: CodeAssistant,
    windows_codex_home: Option<&str>,
) -> String {
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
WIN_USER_HOME="${{WIN_CODEX_HOME%/.codex}}"
codex_real=""
codex_path_candidate="$(command -v codex || true)"
if [ -n "$codex_path_candidate" ] && [ -x "$codex_path_candidate" ]; then
  codex_real="$codex_path_candidate"
fi
if [ -z "$codex_real" ] && [ -n "$WIN_USER_HOME" ]; then
  for codex_candidate in "$WIN_USER_HOME"/AppData/Local/OpenAI/Codex/bin/*/codex.exe; do
    if [ -x "$codex_candidate" ]; then
      codex_real="$codex_candidate"
      break
    fi
  done
fi
if [ -z "$codex_real" ]; then
  printf '%s\n' "Codex executable was not found in WSL."
  printf '%s\n' "Run Codex login on Windows first, then reopen Studio's Codex menu item."
  exec bash -i
fi
mkdir -p "$HOME/.local/bin"
ln -sfn "$codex_real" "$HOME/.local/bin/codex"
"#,
            windows_home = windows_home
        )
    } else {
        String::new()
    };
    format!(
        r#"#!/usr/bin/env bash
export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
WS={workspace}
CFG={config}
export SYSTEMD_LOG_LEVEL=err
export STUDIO_AH_HOST_HOME="$HOME"
{codex_auth_sync}
if ! command -v ah >/dev/null 2>&1; then
  printf '%s\n' "ah CLI was not found in WSL."
  printf '%s\n' "Install it from https://github.com/SevenX77/ah then reopen Studio."
  exec bash -i
fi
ah_version="$(ah --version 2>/dev/null | awk '{{print $2}}')"
ah_major="${{ah_version%%.*}}"
ah_rest="${{ah_version#*.}}"
ah_minor="${{ah_rest%%.*}}"
ah_patch="${{ah_rest#*.}}"
[ "$ah_patch" = "$ah_rest" ] && ah_patch=0
ah_ok=0
if [ "$ah_major" -gt 1 ] 2>/dev/null; then
  ah_ok=1
elif [ "$ah_major" -eq 1 ] 2>/dev/null && [ "$ah_minor" -gt 3 ] 2>/dev/null; then
  ah_ok=1
elif [ "$ah_major" -eq 1 ] 2>/dev/null && [ "$ah_minor" -eq 3 ] 2>/dev/null && [ "$ah_patch" -ge 1 ] 2>/dev/null; then
  ah_ok=1
fi
if [ "$ah_ok" -ne 1 ]; then
  printf 'ah %s is installed; Studio requires ah >= 1.3.1 for runtime events.\n' "${{ah_version:-unknown}}"
  printf '%s\n' "Run scripts/install-claude-code-wsl.ps1, then reopen Studio."
  exec bash -i
fi
if command -v python3 >/dev/null 2>&1; then
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
printf '%s\n' "Attaching - {assistant_name} will auto-report its status (detach: Ctrl-b then d)."
ah --config "$CFG" attach master
printf '[attach ended; exit=%s]\n' "$?"
exec bash -i
"#,
        workspace = sh_single_quote_str(wsl_workspace),
        config = sh_single_quote_str(wsl_config),
        assistant_name = assistant.display_name(),
        codex_auth_sync = codex_auth_sync,
        preseed = CLAUDE_ONBOARDING_PRESEED_PY,
    )
}

/// On Windows, ah + claude live inside WSL2, so the .ps1 just runs the bash
/// payload through `wsl.exe` in this console window (keeping the attach
/// interactive).
fn windows_code_assistant_launcher_script(
    wsl_payload_path: &str,
    assistant: CodeAssistant,
    window_title: &str,
) -> String {
    format!(
        r#"$ErrorActionPreference = "Stop"
$studioWindowTitle = {window_title}
$Host.UI.RawUI.WindowTitle = $studioWindowTitle
[Console]::Title = $studioWindowTitle
Write-Host "Opening {assistant_name} through ah (WSL)..."
wsl.exe -e bash {payload}
if ($LASTEXITCODE -ne 0) {{
  Read-Host "Could not start WSL (exit $LASTEXITCODE). Is WSL2 installed? Press Enter to close"
}}
"#,
        assistant_name = assistant.display_name(),
        payload = powershell_single_quote_str(wsl_payload_path),
        window_title = powershell_single_quote_str(window_title),
    )
}

fn wsl_attach_payload_script(wsl_config: &str, assistant: CodeAssistant) -> String {
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
ah_version="$(ah --version 2>/dev/null | awk '{{print $2}}')"
ah_major="${{ah_version%%.*}}"
ah_rest="${{ah_version#*.}}"
ah_minor="${{ah_rest%%.*}}"
ah_patch="${{ah_rest#*.}}"
[ "$ah_patch" = "$ah_rest" ] && ah_patch=0
ah_ok=0
if [ "$ah_major" -gt 1 ] 2>/dev/null; then
  ah_ok=1
elif [ "$ah_major" -eq 1 ] 2>/dev/null && [ "$ah_minor" -gt 3 ] 2>/dev/null; then
  ah_ok=1
elif [ "$ah_major" -eq 1 ] 2>/dev/null && [ "$ah_minor" -eq 3 ] 2>/dev/null && [ "$ah_patch" -ge 1 ] 2>/dev/null; then
  ah_ok=1
fi
if [ "$ah_ok" -ne 1 ]; then
  printf 'ah %s is installed; Studio requires ah >= 1.3.1 for runtime events.\n' "${{ah_version:-unknown}}"
  printf '%s\n' "Run scripts/install-claude-code-wsl.ps1, then reopen Studio."
  exec bash -i
fi
printf '%s\n' "Attaching {assistant_name} master pane (detach: Ctrl-b then d)."
ah --config "$CFG" attach master
printf '[attach ended; exit=%s]\n' "$?"
exec bash -i
"#,
        config = sh_single_quote_str(wsl_config),
        assistant_name = assistant.display_name(),
    )
}

fn windows_code_assistant_attach_launcher_script(
    wsl_payload_path: &str,
    assistant: CodeAssistant,
    window_title: &str,
) -> String {
    format!(
        r#"$ErrorActionPreference = "Stop"
$studioWindowTitle = {window_title}
$Host.UI.RawUI.WindowTitle = $studioWindowTitle
[Console]::Title = $studioWindowTitle
Write-Host "Attaching {assistant_name} through ah (WSL)..."
wsl.exe -e bash {payload}
if ($LASTEXITCODE -ne 0) {{
  Read-Host "Could not start WSL (exit $LASTEXITCODE). Is WSL2 installed? Press Enter to close"
}}
"#,
        assistant_name = assistant.display_name(),
        payload = powershell_single_quote_str(wsl_payload_path),
        window_title = powershell_single_quote_str(window_title),
    )
}

/// On native Linux ah runs directly. macOS is not yet supported by ah.
fn unix_code_assistant_launcher_script(
    workspace_root: &Path,
    config_path: &Path,
    assistant: CodeAssistant,
) -> String {
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
ah_version="$(ah --version 2>/dev/null | awk '{{print $2}}')"
ah_major="${{ah_version%%.*}}"
ah_rest="${{ah_version#*.}}"
ah_minor="${{ah_rest%%.*}}"
ah_patch="${{ah_rest#*.}}"
[ "$ah_patch" = "$ah_rest" ] && ah_patch=0
ah_ok=0
if [ "$ah_major" -gt 1 ] 2>/dev/null; then
  ah_ok=1
elif [ "$ah_major" -eq 1 ] 2>/dev/null && [ "$ah_minor" -gt 3 ] 2>/dev/null; then
  ah_ok=1
elif [ "$ah_major" -eq 1 ] 2>/dev/null && [ "$ah_minor" -eq 3 ] 2>/dev/null && [ "$ah_patch" -ge 1 ] 2>/dev/null; then
  ah_ok=1
fi
if [ "$ah_ok" -ne 1 ]; then
  printf 'ah %s is installed; Studio requires ah >= 1.3.1 for runtime events.\n' "${{ah_version:-unknown}}"
  printf '%s\n' "Install ah from https://github.com/SevenX77/ah, then reopen Studio."
  exec "${{SHELL:-/bin/sh}}"
fi
if command -v python3 >/dev/null 2>&1; then
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
ah --config {config} attach master
printf '[attach ended]\n'
exec "${{SHELL:-/bin/sh}}"
"#,
        workspace = sh_single_quote(workspace_root),
        config = sh_single_quote(config_path),
        assistant_name = assistant.display_name(),
        preseed = CLAUDE_ONBOARDING_PRESEED_PY,
    )
}

fn unix_code_assistant_attach_launcher_script(
    config_path: &Path,
    assistant: CodeAssistant,
) -> String {
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
ah_version="$(ah --version 2>/dev/null | awk '{{print $2}}')"
ah_major="${{ah_version%%.*}}"
ah_rest="${{ah_version#*.}}"
ah_minor="${{ah_rest%%.*}}"
ah_patch="${{ah_rest#*.}}"
[ "$ah_patch" = "$ah_rest" ] && ah_patch=0
ah_ok=0
if [ "$ah_major" -gt 1 ] 2>/dev/null; then
  ah_ok=1
elif [ "$ah_major" -eq 1 ] 2>/dev/null && [ "$ah_minor" -gt 3 ] 2>/dev/null; then
  ah_ok=1
elif [ "$ah_major" -eq 1 ] 2>/dev/null && [ "$ah_minor" -eq 3 ] 2>/dev/null && [ "$ah_patch" -ge 1 ] 2>/dev/null; then
  ah_ok=1
fi
if [ "$ah_ok" -ne 1 ]; then
  printf 'ah %s is installed; Studio requires ah >= 1.3.1 for runtime events.\n' "${{ah_version:-unknown}}"
  printf '%s\n' "Install ah from https://github.com/SevenX77/ah, then reopen Studio."
  exec "${{SHELL:-/bin/sh}}"
fi
printf '%s\n' "Attaching {assistant_name} master pane (detach: Ctrl-b then d)."
ah --config {config} attach master
printf '[attach ended]\n'
exec "${{SHELL:-/bin/sh}}"
"#,
        config = sh_single_quote(config_path),
        assistant_name = assistant.display_name(),
    )
}

fn launcher_script_path(workspace_root: &Path, assistant: CodeAssistant) -> PathBuf {
    let extension = if cfg!(target_os = "windows") {
        "ps1"
    } else if cfg!(target_os = "macos") {
        "command"
    } else {
        "sh"
    };
    std::env::temp_dir()
        .join("skill-studio-ah")
        .join(workspace_hash(workspace_root))
        .join(assistant.slug())
        .join(format!("{}.{extension}", assistant.launcher_stem()))
}

fn attach_launcher_script_path(workspace_root: &Path, assistant: CodeAssistant) -> PathBuf {
    let extension = if cfg!(target_os = "windows") {
        "ps1"
    } else if cfg!(target_os = "macos") {
        "command"
    } else {
        "sh"
    };
    std::env::temp_dir()
        .join("skill-studio-ah")
        .join(workspace_hash(workspace_root))
        .join(assistant.slug())
        .join(format!("{}.{extension}", assistant.attach_launcher_stem()))
}

fn code_assistant_window_title(workspace_root: &Path, assistant: CodeAssistant) -> String {
    let workspace_name = workspace_root
        .file_name()
        .and_then(|name| name.to_str())
        .filter(|name| !name.is_empty())
        .unwrap_or("workspace");
    format!(
        "Studio {} master - {} - {}",
        assistant.display_name(),
        workspace_name,
        workspace_hash(workspace_root)
    )
}

fn windows_codex_home_wsl() -> Option<String> {
    let user_profile = std::env::var_os("USERPROFILE")?;
    Some(windows_path_to_wsl(
        &PathBuf::from(user_profile).join(".codex"),
    ))
}

fn write_code_assistant_launcher_script(
    workspace_root: &Path,
    config_path: &Path,
    assistant: CodeAssistant,
) -> Result<PathBuf, String> {
    let script_path = launcher_script_path(workspace_root, assistant);
    let parent = script_path
        .parent()
        .ok_or_else(|| format!("cannot resolve launcher parent: {}", script_path.display()))?;
    std::fs::create_dir_all(parent)
        .map_err(|error| format!("failed to create launcher script dir: {error}"))?;
    let content = if cfg!(target_os = "windows") {
        // ah + claude live inside WSL2 on Windows: write the bash payload, then a
        // .ps1 that runs it through wsl.exe. Both paths are translated to the
        // /mnt/... form the distro sees.
        let payload_path = parent.join(format!("{}.wsl.sh", assistant.launcher_stem()));
        std::fs::write(
            &payload_path,
            wsl_payload_script(
                &windows_path_to_wsl(workspace_root),
                &windows_path_to_wsl(config_path),
                assistant,
                windows_codex_home_wsl().as_deref(),
            ),
        )
        .map_err(|error| format!("failed to write WSL payload: {error}"))?;
        let window_title = code_assistant_window_title(workspace_root, assistant);
        windows_code_assistant_launcher_script(
            &windows_path_to_wsl(&payload_path),
            assistant,
            &window_title,
        )
    } else {
        unix_code_assistant_launcher_script(workspace_root, config_path, assistant)
    };
    std::fs::write(&script_path, content).map_err(|error| {
        format!(
            "failed to write {} launcher: {error}",
            assistant.display_name()
        )
    })?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut permissions = std::fs::metadata(&script_path)
            .map_err(|error| {
                format!(
                    "failed to stat {} launcher: {error}",
                    assistant.display_name()
                )
            })?
            .permissions();
        permissions.set_mode(0o700);
        std::fs::set_permissions(&script_path, permissions).map_err(|error| {
            format!(
                "failed to chmod {} launcher: {error}",
                assistant.display_name()
            )
        })?;
    }
    Ok(script_path)
}

fn write_code_assistant_attach_launcher_script(
    workspace_root: &Path,
    config_path: &Path,
    assistant: CodeAssistant,
) -> Result<PathBuf, String> {
    let script_path = attach_launcher_script_path(workspace_root, assistant);
    let parent = script_path.parent().ok_or_else(|| {
        format!(
            "cannot resolve attach launcher parent: {}",
            script_path.display()
        )
    })?;
    std::fs::create_dir_all(parent)
        .map_err(|error| format!("failed to create attach launcher script dir: {error}"))?;
    let content = if cfg!(target_os = "windows") {
        let payload_path = parent.join(format!("{}.wsl.sh", assistant.attach_launcher_stem()));
        std::fs::write(
            &payload_path,
            wsl_attach_payload_script(&windows_path_to_wsl(config_path), assistant),
        )
        .map_err(|error| format!("failed to write WSL attach payload: {error}"))?;
        let window_title = code_assistant_window_title(workspace_root, assistant);
        windows_code_assistant_attach_launcher_script(
            &windows_path_to_wsl(&payload_path),
            assistant,
            &window_title,
        )
    } else {
        unix_code_assistant_attach_launcher_script(config_path, assistant)
    };
    std::fs::write(&script_path, content).map_err(|error| {
        format!(
            "failed to write {} attach launcher: {error}",
            assistant.display_name()
        )
    })?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut permissions = std::fs::metadata(&script_path)
            .map_err(|error| {
                format!(
                    "failed to stat {} attach launcher: {error}",
                    assistant.display_name()
                )
            })?
            .permissions();
        permissions.set_mode(0o700);
        std::fs::set_permissions(&script_path, permissions).map_err(|error| {
            format!(
                "failed to chmod {} attach launcher: {error}",
                assistant.display_name()
            )
        })?;
    }
    Ok(script_path)
}

fn spawn_linux_terminal(script_path: &Path) -> Result<(), String> {
    let script = script_path.display().to_string();
    let candidates: [(&str, Vec<&str>); 7] = [
        ("x-terminal-emulator", vec!["-e", script.as_str()]),
        ("gnome-terminal", vec!["--", script.as_str()]),
        ("konsole", vec!["-e", script.as_str()]),
        ("xfce4-terminal", vec!["-e", script.as_str()]),
        ("kitty", vec![script.as_str()]),
        ("alacritty", vec!["-e", script.as_str()]),
        ("xterm", vec!["-e", script.as_str()]),
    ];
    let mut errors = Vec::new();
    for (program, args) in candidates {
        match Command::new(program).args(args).spawn() {
            Ok(_) => return Ok(()),
            Err(error) => errors.push(format!("{program}: {error}")),
        }
    }
    Err(format!(
        "failed to open a terminal; tried x-terminal-emulator, gnome-terminal, konsole, xfce4-terminal, kitty, alacritty, xterm ({})",
        errors.join("; ")
    ))
}

fn windows_cmd_start_powershell_args(
    script_path: &Path,
    window_title: &str,
) -> Vec<std::ffi::OsString> {
    vec![
        std::ffi::OsString::from("/C"),
        std::ffi::OsString::from("start"),
        // cmd.exe's `start` treats the first quoted token as the window title.
        // Keeping it explicit prevents assistant names such as "Codex" from
        // being interpreted as the command/program.
        std::ffi::OsString::from(window_title),
        std::ffi::OsString::from("powershell.exe"),
        std::ffi::OsString::from("-NoExit"),
        std::ffi::OsString::from("-ExecutionPolicy"),
        std::ffi::OsString::from("Bypass"),
        std::ffi::OsString::from("-File"),
        script_path.as_os_str().to_os_string(),
    ]
}

fn windows_focus_existing_terminal_command(window_title: &str) -> String {
    format!(
        r#"$ErrorActionPreference = "Stop"
$needle = {window_title}
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;

public static class StudioWindowFocus {{
  public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}}
"@
$target = [IntPtr]::Zero
$callback = [StudioWindowFocus+EnumWindowsProc]{{
  param([IntPtr] $hWnd, [IntPtr] $lParam)
  if (-not [StudioWindowFocus]::IsWindowVisible($hWnd)) {{ return $true }}
  $title = New-Object System.Text.StringBuilder 512
  [void][StudioWindowFocus]::GetWindowText($hWnd, $title, $title.Capacity)
  if ($title.ToString().Contains($needle)) {{
    $script:target = $hWnd
    return $false
  }}
  return $true
}}
[void][StudioWindowFocus]::EnumWindows($callback, [IntPtr]::Zero)
if ($target -eq [IntPtr]::Zero) {{ exit 1 }}
[void][StudioWindowFocus]::ShowWindow($target, 9)
[void][StudioWindowFocus]::SetForegroundWindow($target)
exit 0
"#,
        window_title = powershell_single_quote_str(window_title),
    )
}

fn focus_existing_windows_terminal(window_title: &str) -> bool {
    let command = windows_focus_existing_terminal_command(window_title);
    Command::new("powershell.exe")
        .args([
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            &command,
        ])
        .status()
        .map(|status| status.success())
        .unwrap_or(false)
}

fn spawn_terminal_with_launcher(
    script_path: &Path,
    assistant: CodeAssistant,
    window_title: &str,
    reuse_existing_window: bool,
) -> Result<(), String> {
    if cfg!(target_os = "windows") {
        if reuse_existing_window && focus_existing_windows_terminal(window_title) {
            return Ok(());
        }
        return Command::new("cmd")
            .args(windows_cmd_start_powershell_args(script_path, window_title))
            .spawn()
            .map(|_| ())
            .map_err(|error| format!("failed to open PowerShell: {error}"));
    }

    if cfg!(target_os = "macos") {
        return Command::new("open")
            .args(["-a", "Terminal"])
            .arg(script_path)
            .spawn()
            .map(|_| ())
            .map_err(|error| format!("failed to open Terminal.app: {error}"));
    }

    if cfg!(target_os = "linux") {
        return spawn_linux_terminal(script_path);
    }

    Err(format!(
        "opening {} is not supported on this platform",
        assistant.display_name()
    ))
}

enum CodeAssistantOpenAction {
    StartFresh,
    AttachExisting(PathBuf),
}

fn prepare_code_assistant_open(
    workspace_root: &Path,
    requested: CodeAssistant,
) -> Result<CodeAssistantOpenAction, String> {
    let requested_runtime = ah_config_for_status(workspace_root, requested).map(|config| {
        let probe = inspect_ah_runtime(&config, None);
        (config, probe.snapshot)
    });
    let requested_config = requested_runtime
        .as_ref()
        .map(|(config, _)| config.to_path_buf());
    let other_runtimes = CodeAssistant::ALL
        .iter()
        .copied()
        .filter(|assistant| assistant.slug() != requested.slug())
        .filter_map(|assistant| {
            ah_config_for_status(workspace_root, assistant).map(|config| {
                let probe = inspect_ah_runtime(&config, None);
                (assistant, config, probe.snapshot)
            })
        })
        .filter(|(_, config, _)| requested_config.as_ref() != Some(config))
        .collect::<Vec<_>>();
    let other_snapshots = other_runtimes
        .iter()
        .map(|(_, _, snapshot)| *snapshot)
        .collect::<Vec<_>>();

    match decide_code_assistant_open(
        requested_runtime.as_ref().map(|(_, snapshot)| *snapshot),
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
                    code_assistant_lifecycle_is_active(*snapshot).then_some(*assistant)
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
    }
}

fn open_code_assistant(workspace_root: &Path, assistant: CodeAssistant) -> Result<PathBuf, String> {
    match prepare_code_assistant_open(workspace_root, assistant)? {
        CodeAssistantOpenAction::AttachExisting(config_path) => {
            let launcher = write_code_assistant_attach_launcher_script(
                workspace_root,
                &config_path,
                assistant,
            )?;
            let window_title = code_assistant_window_title(workspace_root, assistant);
            spawn_terminal_with_launcher(&launcher, assistant, &window_title, true)?;
            Ok(config_path)
        }
        CodeAssistantOpenAction::StartFresh => {
            let config_path = ah_config_for_workspace(workspace_root, assistant)?;
            let launcher =
                write_code_assistant_launcher_script(workspace_root, &config_path, assistant)?;
            let window_title = code_assistant_window_title(workspace_root, assistant);
            spawn_terminal_with_launcher(&launcher, assistant, &window_title, false)?;
            Ok(config_path)
        }
    }
}

fn attach_code_assistant_terminal(
    workspace_root: String,
    assistant: CodeAssistant,
) -> Result<(), String> {
    let workspace_root = existing_directory(&workspace_root)?;
    let Some(config_path) = ah_config_for_status(&workspace_root, assistant) else {
        return Err(format!("{} is not running", assistant.display_name()));
    };
    let probe = inspect_ah_runtime(&config_path, None);
    match reconcile_code_assistant_lifecycle(probe.snapshot) {
        CodeAssistantLifecycleAction::AttachExisting => {}
        CodeAssistantLifecycleAction::CleanupStale => {
            cleanup_workspace_code_assistants(&workspace_root)?;
            return Err(format!(
                "{} was stale and has been closed; reopen it from Open in CLI.",
                assistant.display_name()
            ));
        }
        CodeAssistantLifecycleAction::StartFresh => {
            return Err(format!("{} is not running", assistant.display_name()));
        }
    }
    let launcher =
        write_code_assistant_attach_launcher_script(&workspace_root, &config_path, assistant)?;
    let window_title = code_assistant_window_title(&workspace_root, assistant);
    spawn_terminal_with_launcher(&launcher, assistant, &window_title, true)
}

#[tauri::command]
fn open_claude_code(
    app: tauri::AppHandle,
    workspace_root: String,
    state: tauri::State<'_, CodeAssistantRuntimeState>,
) -> Result<(), String> {
    let workspace_root = existing_directory(&workspace_root)?;
    let config = open_code_assistant(&workspace_root, CodeAssistant::Claude)?;
    state
        .configs
        .lock()
        .expect("code assistant state poisoned")
        .insert(config.clone());
    register_opened_code_assistant_status_spec(
        &state,
        &workspace_root,
        CodeAssistant::Claude,
        &config,
    );
    ensure_code_assistant_status_streams_for_workspace(&app, &state, &workspace_root)?;
    emit_code_assistant_status_for_workspace(&app, &state, &workspace_root);
    Ok(())
}

#[tauri::command]
fn open_codex_cli(
    app: tauri::AppHandle,
    workspace_root: String,
    state: tauri::State<'_, CodeAssistantRuntimeState>,
) -> Result<(), String> {
    let workspace_root = existing_directory(&workspace_root)?;
    let config = open_code_assistant(&workspace_root, CodeAssistant::Codex)?;
    state
        .configs
        .lock()
        .expect("code assistant state poisoned")
        .insert(config.clone());
    register_opened_code_assistant_status_spec(
        &state,
        &workspace_root,
        CodeAssistant::Codex,
        &config,
    );
    ensure_code_assistant_status_streams_for_workspace(&app, &state, &workspace_root)?;
    emit_code_assistant_status_for_workspace(&app, &state, &workspace_root);
    Ok(())
}

#[tauri::command]
fn attach_code_assistant(workspace_root: String, assistant: String) -> Result<(), String> {
    let assistant = CodeAssistant::from_slug(assistant.trim())?;
    attach_code_assistant_terminal(workspace_root, assistant)
}

#[tauri::command]
fn watch_code_assistant_status(
    app: tauri::AppHandle,
    workspace_root: String,
    state: tauri::State<'_, CodeAssistantRuntimeState>,
) -> Result<(), String> {
    let workspace_root = existing_directory(&workspace_root)?;
    ensure_code_assistant_status_streams_for_workspace(&app, &state, &workspace_root)?;
    emit_code_assistant_status_for_workspace(&app, &state, &workspace_root);
    Ok(())
}

#[tauri::command]
fn unwatch_code_assistant_status(
    workspace_root: String,
    state: tauri::State<'_, CodeAssistantRuntimeState>,
) -> Result<(), String> {
    let workspace_root = PathBuf::from(workspace_root.trim());
    if workspace_root.as_os_str().is_empty() {
        return Ok(());
    }
    unwatch_code_assistant_status_streams_for_workspace(&state, &workspace_root);
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
        clear_status_snapshots_for_workspace(&state, &workspace_root);
        emit_code_assistant_status_for_workspace(&app, &state, &workspace_root);
        return Ok(false);
    }
    let cleanup = cleanup_workspace_code_assistants(&workspace_root)?;
    state
        .configs
        .lock()
        .expect("code assistant state poisoned")
        .retain(|registered_config| !cleanup.configs.contains(registered_config));
    clear_status_snapshots_for_workspace(&state, &workspace_root);
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
            .arg(target)
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
            watch_code_assistant_status,
            unwatch_code_assistant_status,
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
            source.contains("unwatch_code_assistant_status,"),
            "unwatch_code_assistant_status must be registered in the Tauri invoke handler"
        );
        assert!(
            source.contains("close_code_assistant,"),
            "close_code_assistant must be registered in the Tauri invoke handler"
        );
    }

    #[test]
    fn studio_ah_config_starts_moirai_team() {
        let config = studio_ah_config_content(CodeAssistant::Claude);

        assert!(config.contains("version = \"1\""));
        assert!(config.contains("[master]"));
        assert!(
            config.contains("window_size = \"follow\""),
            "ah 1.3.0 defaults master tmux sizing to fixed; Studio must opt into follow"
        );
        // IS_SANDBOX (root escape hatch) + skip-permissions + the auto-report
        // prompt; NOT --continue (aborts on a fresh workspace) or /remote-control.
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
        assert!(config.contains("--dangerously-skip-permissions"));
        assert!(config.contains(MOIRAI_MASTER_REPORT_PROMPT));
        assert!(!config.contains("--continue"));
        assert!(!config.contains("/remote-control"));
        assert!(!config.contains("[agents.studio]"));
        assert!(config.contains("[agents.clotho]"));
        assert!(config
            .contains("skills = [\"domain-analysis\", \"graph-design\", \"agent-prompt-design\"]"));
        assert!(config.contains("[agents.lachesis]"));
        assert!(config.contains("skills = [\"compile-error-repair\"]"));
        assert!(config.contains("[agents.atropos]"));
        assert!(config.contains("skills = [\"eval-judgement\"]"));
        assert_eq!(config.matches("provider = \"claude\"").count(), 4);
        assert!(!config.contains("[sandbox]"));
        assert!(
            !config.contains("additional_ro_binds"),
            "ah 1.3.0 still maps additional_ro_binds to systemd-run --user --scope BindReadOnlyPaths, which WSL rejects"
        );
    }

    #[test]
    fn studio_ah_config_starts_codex_moirai_team() {
        let config = studio_ah_config_content(CodeAssistant::Codex);

        assert!(config.contains("version = \"1\""));
        assert!(config.contains("[master]"));
        assert!(config.contains("window_size = \"follow\""));
        assert!(config.contains("cmd = \"bash -c "));
        assert!(config.contains("STUDIO_AH_HOST_HOME"));
        assert!(config.contains("[ ! -x \\\"$codex_real\\\" ]"));
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
        assert!(config.contains(MOIRAI_MASTER_REPORT_PROMPT));
        assert!(config.contains("[agents.clotho]"));
        assert!(config
            .contains("skills = [\"domain-analysis\", \"graph-design\", \"agent-prompt-design\"]"));
        assert!(config.contains("[agents.lachesis]"));
        assert!(config.contains("skills = [\"compile-error-repair\"]"));
        assert!(config.contains("[agents.atropos]"));
        assert!(config.contains("skills = [\"eval-judgement\"]"));
        assert_eq!(config.matches("provider = \"codex\"").count(), 4);
        assert!(!config.contains("--dangerously-skip-permissions"));
    }

    fn assert_progressive_wikipedia_background(rules: &str, wikipedia_url: &str) {
        assert!(
            rules.contains(wikipedia_url),
            "rules should link the role background instead of embedding long mythology"
        );
        assert!(
            rules.contains("只在用户询问"),
            "background should be disclosed progressively, not always expanded"
        );
        assert!(
            rules.contains("Wikipedia"),
            "the source link should be named explicitly"
        );
        for leaked_term in ["master", "worker", "派单"] {
            assert!(
                !rules.contains(leaked_term),
                "Studio-managed persona rules must not leak ah scaffold term `{leaked_term}`"
            );
        }
    }

    #[test]
    fn managed_moirai_rules_use_progressive_wikipedia_backgrounds() {
        assert_progressive_wikipedia_background(
            MOIRAI_MASTER_RULES,
            "https://en.wikipedia.org/wiki/Moirai",
        );
        assert_progressive_wikipedia_background(
            CLOTHO_RULES,
            "https://en.wikipedia.org/wiki/Clotho",
        );
        assert_progressive_wikipedia_background(
            LACHESIS_RULES,
            "https://en.wikipedia.org/wiki/Lachesis",
        );
        assert_progressive_wikipedia_background(
            ATROPOS_RULES,
            "https://en.wikipedia.org/wiki/Atropos",
        );
    }

    #[test]
    fn studio_ah_config_omits_systemd_scope_ro_binds() {
        let config = studio_ah_config_content(CodeAssistant::Claude);

        assert!(!config.contains("additional_ro_binds"));
        assert!(!config.contains("BindReadOnlyPaths"));
    }

    #[test]
    fn launchers_reject_ah_before_runtime_events_support() {
        let windows_payload = wsl_payload_script(
            "/mnt/d/skill",
            "/mnt/c/tmp/ah.toml",
            CodeAssistant::Claude,
            None,
        );
        assert!(windows_payload.contains("ah_version="));
        assert!(windows_payload.contains("requires ah >= 1.3.1"));

        let unix_payload = unix_code_assistant_launcher_script(
            Path::new("/tmp/skill"),
            Path::new("/tmp/ah.toml"),
            CodeAssistant::Claude,
        );
        assert!(unix_payload.contains("ah_version="));
        assert!(unix_payload.contains("requires ah >= 1.3.1"));
    }

    #[test]
    fn generated_ah_config_prepares_moirai_workspace_files() {
        let root = temp_path("moirai-workspace");
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();

        let config = ah_config_for_workspace(&root, CodeAssistant::Claude)
            .expect("generated workspace ah config");

        assert_eq!(config, root.join("ah.toml"));
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

        assert!(master_rules.is_file());
        assert!(clotho_rules.is_file());
        assert!(domain_skill.is_file());
        assert!(eval_skill.is_file());
        let master = std::fs::read_to_string(master_rules).unwrap();
        assert!(master.contains("studio-ah-managed hash:"));
        assert!(master.contains("MoirAI"));
        let domain = std::fs::read_to_string(domain_skill).unwrap();
        assert!(domain.starts_with("---\n"));
        assert!(domain.contains("name: domain-analysis"));
        assert!(domain.contains("studio-ah-managed hash:"));
        let eval = std::fs::read_to_string(eval_skill).unwrap();
        assert!(eval.contains("name: eval-judgement"));
        let config_content = std::fs::read_to_string(config).unwrap();
        assert!(config_content.contains("# studio-ah-managed hash:"));
        assert_eq!(
            master_provider_from_ah_config(&root.join("ah.toml")).as_deref(),
            Some("claude")
        );

        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn existing_ah_config_is_respected_without_generating_studio_files() {
        let root = temp_path("user-ah-config");
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();
        std::fs::write(root.join("ah.toml"), "version = \"1\"\n").unwrap();

        let config =
            ah_config_for_workspace(&root, CodeAssistant::Claude).expect("existing ah config");

        assert_eq!(config, root.join("ah.toml"));
        assert!(!root.join(".ah").exists());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn managed_workspace_ah_config_rewrites_for_requested_assistant() {
        let root = temp_path("managed-ah-config-rewrite");
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();

        let claude_config =
            ah_config_for_workspace(&root, CodeAssistant::Claude).expect("claude config");
        assert_eq!(claude_config, root.join("ah.toml"));
        assert_eq!(
            master_provider_from_ah_config(&claude_config).as_deref(),
            Some("claude")
        );

        let codex_config =
            ah_config_for_workspace(&root, CodeAssistant::Codex).expect("codex config");
        assert_eq!(codex_config, root.join("ah.toml"));
        assert_eq!(
            master_provider_from_ah_config(&codex_config).as_deref(),
            Some("codex")
        );
        assert_eq!(
            ah_config_for_status(&root, CodeAssistant::Codex).as_deref(),
            Some(codex_config.as_path())
        );
        assert!(ah_config_for_status(&root, CodeAssistant::Claude).is_none());

        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn status_config_lookup_does_not_generate_workspace_files() {
        let root = temp_path("status-ah-config");
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();
        let config = root.join("ah.toml");

        assert!(ah_config_for_status(&root, CodeAssistant::Codex).is_none());
        assert!(!root.join(".ah").exists());

        write_studio_managed_toml_file(&config, &studio_ah_config_content(CodeAssistant::Codex))
            .unwrap();

        assert_eq!(
            ah_config_for_status(&root, CodeAssistant::Codex).as_deref(),
            Some(config.as_path())
        );
        assert!(ah_config_for_status(&root, CodeAssistant::Claude).is_none());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn code_assistant_status_requires_ahd_and_master_tmux() {
        assert!(code_assistant_lifecycle_is_active(
            AhLifecycleSnapshot::new(true, true, true)
        ));
        assert!(!code_assistant_lifecycle_is_active(
            AhLifecycleSnapshot::new(true, false, true)
        ));
        assert!(!code_assistant_lifecycle_is_active(
            AhLifecycleSnapshot::new(false, true, true)
        ));
        assert!(code_assistant_lifecycle_is_active(
            AhLifecycleSnapshot::new(true, true, false)
        ));
    }

    #[test]
    fn stale_ahd_without_master_requires_cleanup_before_reopen() {
        assert_eq!(
            reconcile_code_assistant_lifecycle(AhLifecycleSnapshot::new(true, false, true)),
            CodeAssistantLifecycleAction::CleanupStale
        );
        assert_eq!(
            reconcile_code_assistant_lifecycle(AhLifecycleSnapshot::new(false, true, false)),
            CodeAssistantLifecycleAction::CleanupStale
        );
        assert_eq!(
            reconcile_code_assistant_lifecycle(AhLifecycleSnapshot::new(true, true, true)),
            CodeAssistantLifecycleAction::AttachExisting
        );
        assert_eq!(
            reconcile_code_assistant_lifecycle(AhLifecycleSnapshot::new(false, false, false)),
            CodeAssistantLifecycleAction::StartFresh
        );
    }

    #[test]
    fn open_decision_enforces_single_ahd_per_workspace() {
        let active = AhLifecycleSnapshot::new(true, true, true);
        let stopped = AhLifecycleSnapshot::new(false, false, false);
        let stale = AhLifecycleSnapshot::new(true, false, false);

        assert_eq!(
            decide_code_assistant_open(Some(active), &[stopped]),
            CodeAssistantOpenDecision::AttachRequested
        );
        assert_eq!(
            decide_code_assistant_open(Some(stopped), &[active]),
            CodeAssistantOpenDecision::RejectOtherActive
        );
        assert_eq!(
            decide_code_assistant_open(Some(active), &[active]),
            CodeAssistantOpenDecision::CleanupStale
        );
        assert_eq!(
            decide_code_assistant_open(Some(stale), &[stopped]),
            CodeAssistantOpenDecision::CleanupStale
        );
        assert_eq!(
            decide_code_assistant_open(None, &[stopped]),
            CodeAssistantOpenDecision::StartFresh
        );
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
    fn ah_events_snapshot_maps_open_state_from_inventory_and_master_not_worker() {
        let line = r#"{"schema_version":1,"event":"snapshot","reason":"tmux_changed","runtime_state":"degraded","ahd_has_inventory":true,"master_tmux_alive":true,"worker_tmux_alive":false}"#;
        let snapshot = lifecycle_snapshot_from_ah_event(line).expect("snapshot parses");

        assert_eq!(snapshot, AhLifecycleSnapshot::new(true, true, false));
        assert!(code_assistant_lifecycle_is_active(snapshot));
    }

    #[test]
    fn ah_events_status_aggregation_cleans_stale_or_multiple_active_configs() {
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

        let snapshots = BTreeMap::from([(
            claude_config.clone(),
            AhLifecycleSnapshot::new(true, true, false),
        )]);
        assert_eq!(
            code_assistant_status_from_snapshots(&specs, &snapshots),
            CodeAssistantStatus {
                claude: true,
                codex: false,
            }
        );
        assert!(!workspace_status_requires_cleanup(&specs, &snapshots));

        let multiple_active = BTreeMap::from([
            (claude_config, AhLifecycleSnapshot::new(true, true, true)),
            (
                codex_config.clone(),
                AhLifecycleSnapshot::new(true, true, true),
            ),
        ]);
        assert!(workspace_status_requires_cleanup(&specs, &multiple_active));

        let stale_codex =
            BTreeMap::from([(codex_config, AhLifecycleSnapshot::new(true, false, true))]);
        assert!(workspace_status_requires_cleanup(&specs, &stale_codex));
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
    fn find_ah_config_does_not_walk_above_workspace() {
        let root = temp_path("ah-config-root");
        let child = root.join("child").join("nested");
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&child).unwrap();
        std::fs::write(
            root.join("ah.toml"),
            studio_ah_config_content(CodeAssistant::Claude),
        )
        .unwrap();

        let found = find_ah_config(&child);

        assert_eq!(found, None);
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
        );

        assert!(script.contains("WIN_CODEX_HOME='/mnt/c/Users/Test User/.codex'"));
        assert!(script.contains("cp \"$WIN_CODEX_HOME/auth.json\" \"$HOME/.codex/auth.json\""));
        assert!(script.contains("chmod 600 \"$HOME/.codex/auth.json\""));
        assert!(script.contains("WIN_USER_HOME=\"${WIN_CODEX_HOME%/.codex}\""));
        assert!(script.contains("command -v codex || true"));
        assert!(script.contains("[ -x \"$codex_path_candidate\" ]"));
        assert!(script.contains("AppData/Local/OpenAI/Codex/bin/*/codex.exe"));
        assert!(script.contains("ln -sfn \"$codex_real\" \"$HOME/.local/bin/codex\""));
        assert!(script.contains("Run Codex login on Windows first"));
        assert!(script.contains("Starting Codex through ah"));
    }

    #[test]
    fn windows_launcher_runs_wsl_bash_payload() {
        let script = windows_code_assistant_launcher_script(
            "/mnt/c/tmp/skill-studio-ah/open-claude-code.wsl.sh",
            CodeAssistant::Claude,
            "Studio Claude Code master - skill - abc123",
        );

        assert!(
            script.contains("$studioWindowTitle = 'Studio Claude Code master - skill - abc123'")
        );
        assert!(script.contains("$Host.UI.RawUI.WindowTitle = $studioWindowTitle"));
        assert!(script.contains("[Console]::Title = $studioWindowTitle"));
        assert!(
            script.contains("wsl.exe -e bash '/mnt/c/tmp/skill-studio-ah/open-claude-code.wsl.sh'")
        );
    }

    #[test]
    fn code_assistant_window_title_is_stable_per_workspace_and_assistant() {
        let root =
            Path::new(r"D:\coding\skills\story-deconstruction-v3\subgraph\text-segmentation");
        let title = code_assistant_window_title(root, CodeAssistant::Codex);

        assert!(title.starts_with("Studio Codex master - text-segmentation - "));
        assert_eq!(
            title,
            code_assistant_window_title(root, CodeAssistant::Codex)
        );
        assert_ne!(
            title,
            code_assistant_window_title(root, CodeAssistant::Claude)
        );
    }

    #[test]
    fn wsl_attach_payload_only_attaches_master() {
        let script = wsl_attach_payload_script(
            "/mnt/c/Users/Test User/AppData/Local/Temp/ah.toml",
            CodeAssistant::Codex,
        );

        assert!(script.contains("Attaching Codex master pane"));
        assert!(script.contains("ah --config \"$CFG\" attach master"));
        assert!(!script.contains("start --wait"));
        assert!(!script.contains("Starting Codex through ah"));
    }

    #[test]
    fn windows_attach_launcher_runs_wsl_attach_payload() {
        let script = windows_code_assistant_attach_launcher_script(
            "/mnt/c/tmp/skill-studio-ah/attach-codex-cli.wsl.sh",
            CodeAssistant::Codex,
            "Studio Codex master - skill - def456",
        );

        assert!(script.contains("$studioWindowTitle = 'Studio Codex master - skill - def456'"));
        assert!(script.contains("$Host.UI.RawUI.WindowTitle = $studioWindowTitle"));
        assert!(script.contains("Attaching Codex through ah (WSL)"));
        assert!(
            script.contains("wsl.exe -e bash '/mnt/c/tmp/skill-studio-ah/attach-codex-cli.wsl.sh'")
        );
    }

    #[test]
    fn windows_terminal_launcher_uses_stable_start_title() {
        let script_path = Path::new(r"C:\Users\Test User\AppData\Local\Temp\open-codex-cli.ps1");
        let args = windows_cmd_start_powershell_args(
            script_path,
            "Studio Codex master - text-segmentation - abc123",
        );
        let as_text: Vec<String> = args
            .iter()
            .map(|arg| arg.to_string_lossy().to_string())
            .collect();

        assert_eq!(as_text[0], "/C");
        assert_eq!(as_text[1], "start");
        assert_eq!(
            as_text[2], "Studio Codex master - text-segmentation - abc123",
            "cmd start needs an explicit title before the program name"
        );
        assert_eq!(as_text[3], "powershell.exe");
        assert!(as_text.contains(&"-NoExit".to_string()));
        assert_eq!(
            as_text.last().unwrap(),
            r"C:\Users\Test User\AppData\Local\Temp\open-codex-cli.ps1"
        );
        assert_ne!(
            as_text[3], "Codex",
            "Codex must never be passed as the start command/program"
        );
    }

    #[test]
    fn windows_focus_command_targets_existing_studio_terminal_title() {
        let command = windows_focus_existing_terminal_command(
            "Studio Codex master - text-segmentation - abc123",
        );

        assert!(command.contains("$needle = 'Studio Codex master - text-segmentation - abc123'"));
        assert!(command.contains("EnumWindows"));
        assert!(command.contains("IsWindowVisible"));
        assert!(command.contains("GetWindowText"));
        assert!(command.contains(".Contains($needle)"));
        assert!(command.contains("ShowWindow($target, 9)"));
        assert!(command.contains("SetForegroundWindow($target)"));
        assert!(command.contains("exit 1"));
    }

    #[test]
    fn attach_reuses_existing_terminal_but_open_always_runs_launcher() {
        let source = include_str!("lib.rs");

        assert!(
            source.contains("spawn_terminal_with_launcher(&launcher, assistant, &window_title, false)?"),
            "initial open must always run the launcher so stale terminal shells cannot block ah start"
        );
        assert!(
            source.contains(
                "spawn_terminal_with_launcher(&launcher, assistant, &window_title, true)"
            ),
            "attach should focus an existing target window before opening a duplicate"
        );
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
