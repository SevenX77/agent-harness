mod native_fs;
mod sidecar;

use sha2::{Digest, Sha256};
use std::path::Path;
use std::path::PathBuf;
use std::process::Command;
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

fn transient_ah_config_path(workspace_root: &Path) -> PathBuf {
    std::env::temp_dir()
        .join("skill-studio-ah")
        .join(workspace_hash(workspace_root))
        .join("ah.toml")
}

/// Prompt the ah-managed Claude master auto-runs on launch, so opening a skill
/// in Claude Code greets the user with a self-report (who it is / which
/// workspace + skill / what it can do) instead of an empty prompt. Kept free of
/// single/double quotes so it embeds cleanly in both the TOML `cmd` string and
/// the single-quoted shell argument that carries it.
const CLAUDE_MASTER_REPORT_PROMPT: &str = "用中文简短汇报当前状态(每点一行),然后停下等我:1) 你是谁 2) 当前工作目录 cwd 是什么、根据目录里的文件这是哪个 skill 3) 你能帮我做什么。";

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
    format!("IS_SANDBOX=1 claude --dangerously-skip-permissions '{CLAUDE_MASTER_REPORT_PROMPT}'")
}

fn transient_ah_config_content() -> String {
    // ah v1 requires at least one agent; Studio only attaches the Claude master pane here.
    format!(
        "version = \"1\"\n\n[master]\nenabled = true\ncmd = \"{cmd}\"\nreadiness_timeout_s = 180\n\n[agents.studio]\nprovider = \"bash\"\n",
        cmd = claude_master_cmd()
    )
}

fn ah_config_for_workspace(workspace_root: &Path) -> Result<PathBuf, String> {
    if let Some(config) = find_ah_config(workspace_root) {
        return Ok(config);
    }
    let config = transient_ah_config_path(workspace_root);
    let parent = config
        .parent()
        .ok_or_else(|| format!("cannot resolve ah config parent: {}", config.display()))?;
    std::fs::create_dir_all(parent)
        .map_err(|error| format!("failed to create transient ah config dir: {error}"))?;
    std::fs::write(&config, transient_ah_config_content())
        .map_err(|error| format!("failed to write transient ah config: {error}"))?;
    Ok(config)
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
    let slashed = path.display().to_string().replace('\\', "/");
    let bytes = slashed.as_bytes();
    if slashed.len() >= 2 && bytes[1] == b':' && bytes[0].is_ascii_alphabetic() {
        let drive = (bytes[0] as char).to_ascii_lowercase();
        return format!("/mnt/{}{}", drive, &slashed[2..]);
    }
    slashed
}

/// The bash payload ah + claude run inside WSL. It pre-accepts the per-workspace
/// onboarding gates (theme picker + folder-trust dialog) so the interactive
/// master reaches its prompt instead of blocking, then `ah start`s and attaches
/// the master — all in ONE wsl session so the interactive attach holds the
/// distro alive and the master persists.
fn wsl_payload_script(wsl_workspace: &str, wsl_config: &str) -> String {
    format!(
        r#"#!/usr/bin/env bash
export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
WS={workspace}
CFG={config}
if ! command -v ah >/dev/null 2>&1; then
  printf '%s\n' "ah CLI was not found in WSL."
  printf '%s\n' "Install it from https://github.com/SevenX77/ah then reopen Studio."
  exec bash -i
fi
if command -v python3 >/dev/null 2>&1; then
python3 - "$WS" <<'PY'
import json, os, sys
p = os.path.expanduser('~/.claude.json')
try:
    d = json.load(open(p))
except Exception:
    d = {{}}
d.setdefault('theme', 'dark')
proj = d.setdefault('projects', {{}})
e = proj.setdefault(sys.argv[1], {{}})
e['hasTrustDialogAccepted'] = True
e.setdefault('hasCompletedProjectOnboarding', True)
e.setdefault('projectOnboardingSeenCount', 3)
json.dump(d, open(p, 'w'), indent=2)
PY
fi
cd "$WS" 2>/dev/null || cd "$HOME"
printf '%s\n' "Starting Claude Code through ah (first launch ~15s cold start)..."
ah --config "$CFG" start --wait
printf '%s\n' "Attaching - Claude Code will auto-report its status (detach: Ctrl-b then d)."
ah --config "$CFG" attach master
printf '[attach ended; exit=%s]\n' "$?"
exec bash -i
"#,
        workspace = sh_single_quote_str(wsl_workspace),
        config = sh_single_quote_str(wsl_config),
    )
}

/// On Windows, ah + claude live inside WSL2, so the .ps1 just runs the bash
/// payload through `wsl.exe` in this console window (keeping the attach
/// interactive).
fn windows_claude_code_launcher_script(wsl_payload_path: &str) -> String {
    format!(
        r#"$ErrorActionPreference = "Stop"
Write-Host "Opening Claude Code through ah (WSL)..."
wsl.exe -e bash {payload}
if ($LASTEXITCODE -ne 0) {{
  Read-Host "Could not start WSL (exit $LASTEXITCODE). Is WSL2 installed? Press Enter to close"
}}
"#,
        payload = powershell_single_quote_str(wsl_payload_path),
    )
}

/// On native Linux ah runs directly. macOS is not yet supported by ah.
fn unix_claude_code_launcher_script(workspace_root: &Path, config_path: &Path) -> String {
    format!(
        r#"#!/bin/sh
set -u
if ! command -v ah >/dev/null 2>&1; then
  printf '%s\n' "ah CLI was not found on PATH."
  printf '%s\n' "Install it from https://github.com/SevenX77/ah then reopen Studio."
  exec "${{SHELL:-/bin/sh}}"
fi
if command -v python3 >/dev/null 2>&1; then
python3 - {workspace} <<'PY'
import json, os, sys
p = os.path.expanduser('~/.claude.json')
try:
    d = json.load(open(p))
except Exception:
    d = {{}}
d.setdefault('theme', 'dark')
proj = d.setdefault('projects', {{}})
e = proj.setdefault(sys.argv[1], {{}})
e['hasTrustDialogAccepted'] = True
e.setdefault('hasCompletedProjectOnboarding', True)
e.setdefault('projectOnboardingSeenCount', 3)
json.dump(d, open(p, 'w'), indent=2)
PY
fi
cd {workspace}
printf '%s\n' "Starting Claude Code through ah (first launch ~15s cold start)..."
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
    )
}

fn launcher_script_path(workspace_root: &Path) -> PathBuf {
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
        .join(format!("open-claude-code.{extension}"))
}

fn write_claude_code_launcher_script(
    workspace_root: &Path,
    config_path: &Path,
) -> Result<PathBuf, String> {
    let script_path = launcher_script_path(workspace_root);
    let parent = script_path
        .parent()
        .ok_or_else(|| format!("cannot resolve launcher parent: {}", script_path.display()))?;
    std::fs::create_dir_all(parent)
        .map_err(|error| format!("failed to create launcher script dir: {error}"))?;
    let content = if cfg!(target_os = "windows") {
        // ah + claude live inside WSL2 on Windows: write the bash payload, then a
        // .ps1 that runs it through wsl.exe. Both paths are translated to the
        // /mnt/... form the distro sees.
        let payload_path = parent.join("open-claude-code.wsl.sh");
        std::fs::write(
            &payload_path,
            wsl_payload_script(
                &windows_path_to_wsl(workspace_root),
                &windows_path_to_wsl(config_path),
            ),
        )
        .map_err(|error| format!("failed to write WSL payload: {error}"))?;
        windows_claude_code_launcher_script(&windows_path_to_wsl(&payload_path))
    } else {
        unix_claude_code_launcher_script(workspace_root, config_path)
    };
    std::fs::write(&script_path, content)
        .map_err(|error| format!("failed to write Claude Code launcher: {error}"))?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut permissions = std::fs::metadata(&script_path)
            .map_err(|error| format!("failed to stat Claude Code launcher: {error}"))?
            .permissions();
        permissions.set_mode(0o700);
        std::fs::set_permissions(&script_path, permissions)
            .map_err(|error| format!("failed to chmod Claude Code launcher: {error}"))?;
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

fn spawn_terminal_with_launcher(script_path: &Path) -> Result<(), String> {
    if cfg!(target_os = "windows") {
        return Command::new("cmd")
            .args([
                "/C",
                "start",
                "Claude Code",
                "powershell.exe",
                "-NoExit",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
            ])
            .arg(script_path)
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

    Err("opening Claude Code is not supported on this platform".to_string())
}

#[tauri::command]
fn open_claude_code(workspace_root: String) -> Result<(), String> {
    let workspace_root = existing_directory(&workspace_root)?;
    let config_path = ah_config_for_workspace(&workspace_root)?;
    let launcher = write_claude_code_launcher_script(&workspace_root, &config_path)?;
    spawn_terminal_with_launcher(&launcher)
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
    fn transient_ah_config_starts_claude_master() {
        let config = transient_ah_config_content();

        assert!(config.contains("version = \"1\""));
        assert!(config.contains("[master]"));
        // IS_SANDBOX (root escape hatch) + skip-permissions + the auto-report
        // prompt; NOT --continue (aborts on a fresh workspace) or /remote-control.
        assert!(config.contains("cmd = \"IS_SANDBOX=1 claude --dangerously-skip-permissions '"));
        assert!(config.contains(CLAUDE_MASTER_REPORT_PROMPT));
        assert!(!config.contains("--continue"));
        assert!(!config.contains("/remote-control"));
        assert!(config.contains("[agents.studio]"));
        assert!(config.contains("provider = \"bash\""));
    }

    #[test]
    fn find_ah_config_walks_up_from_workspace() {
        let root = temp_path("ah-config-root");
        let child = root.join("child").join("nested");
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&child).unwrap();
        std::fs::write(root.join("ah.toml"), transient_ah_config_content()).unwrap();

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
    }

    #[test]
    fn wsl_payload_starts_ah_then_attaches_master() {
        let script = wsl_payload_script(
            "/mnt/c/Users/Test User/skill",
            "/mnt/c/Users/Test User/AppData/Local/Temp/ah.toml",
        );

        assert!(script.contains("WS='/mnt/c/Users/Test User/skill'"));
        assert!(
            script.contains("CFG='/mnt/c/Users/Test User/AppData/Local/Temp/ah.toml'")
        );
        // pre-accepts the per-workspace folder-trust gate so the master doesn't block
        assert!(script.contains("hasTrustDialogAccepted"));
        assert!(script.contains("cd \"$WS\""));
        assert!(script.contains("ah --config \"$CFG\" start --wait"));
        assert!(script.contains("ah --config \"$CFG\" attach master"));
    }

    #[test]
    fn windows_launcher_runs_wsl_bash_payload() {
        let script =
            windows_claude_code_launcher_script("/mnt/c/tmp/skill-studio-ah/open-claude-code.wsl.sh");

        assert!(script
            .contains("wsl.exe -e bash '/mnt/c/tmp/skill-studio-ah/open-claude-code.wsl.sh'"));
    }

    #[test]
    fn unix_launcher_runs_ah_start_then_attach_master() {
        let script = unix_claude_code_launcher_script(
            Path::new("/tmp/skill root"),
            Path::new("/tmp/studio ah/ah.toml"),
        );

        assert!(script.starts_with("#!/bin/sh"));
        assert!(script.contains("cd '/tmp/skill root'"));
        assert!(script.contains("command -v ah"));
        assert!(script.contains("ah --config '/tmp/studio ah/ah.toml' start --wait"));
        assert!(script.contains("ah --config '/tmp/studio ah/ah.toml' attach master"));
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
