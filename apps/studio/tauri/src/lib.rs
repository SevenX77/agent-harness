mod sidecar;

use std::process::Command;
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc, Mutex,
};
use tauri::Manager;

struct SidecarAppState {
    manager: Mutex<Option<sidecar::SidecarManager>>,
    startup_error: Mutex<Option<String>>,
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

fn spawn_tool(bin: &str, path: &str) -> Result<(), String> {
    Command::new(bin)
        .arg(path)
        .spawn()
        .map(|_| ())
        .map_err(|error| format!("failed to spawn {bin}: {error}"))
}

#[tauri::command]
fn open_in_cursor(path: String) -> Result<(), String> {
    spawn_tool("cursor", &path)
}

#[tauri::command]
fn open_in_codex(path: String) -> Result<(), String> {
    spawn_tool("codex", &path)
}

#[tauri::command]
fn reveal_in_file_manager(path: String) -> Result<(), String> {
    if cfg!(target_os = "macos") {
        return Command::new("open")
            .args(["-R", &path])
            .spawn()
            .map(|_| ())
            .map_err(|error| format!("failed to reveal in Finder: {error}"));
    }

    if cfg!(target_os = "linux") {
        return Command::new("xdg-open")
            .arg(&path)
            .spawn()
            .map(|_| ())
            .map_err(|error| format!("failed to open file manager: {error}"));
    }

    if cfg!(target_os = "windows") {
        return Command::new("explorer")
            .arg(format!("/select,{}", path))
            .spawn()
            .map(|_| ())
            .map_err(|error| format!("failed to open Explorer: {error}"));
    }

    Err("revealing in file manager is not supported on this platform".to_string())
}

#[tauri::command]
fn open_in_terminal(path: String) -> Result<(), String> {
    if cfg!(target_os = "macos") {
        return Command::new("open")
            .args(["-a", "Terminal", &path])
            .spawn()
            .map(|_| ())
            .map_err(|error| format!("failed to open Terminal: {error}"));
    }

    if cfg!(target_os = "linux") {
        return Command::new("gnome-terminal")
            .args(["--working-directory", &path])
            .spawn()
            .or_else(|_| {
                Command::new("xterm")
                    .args([
                        "-e",
                        "sh",
                        "-lc",
                        "cd \"$1\" && exec \"${SHELL:-sh}\"",
                        "sh",
                        &path,
                    ])
                    .spawn()
            })
            .map(|_| ())
            .map_err(|error| format!("failed to open terminal: {error}"));
    }

    if cfg!(target_os = "windows") {
        return Command::new("wt.exe")
            .args(["-d", &path])
            .spawn()
            .or_else(|_| {
                Command::new("cmd")
                    .args(["/c", "start", "cmd", "/k", "cd", "/d", &path])
                    .spawn()
            })
            .map(|_| ())
            .map_err(|error| format!("failed to open terminal: {error}"));
    }

    Err("opening a terminal is not supported on this platform".to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            get_sidecar_config,
            get_sidecar_stderr,
            open_in_cursor,
            open_in_codex,
            open_in_terminal,
            reveal_in_file_manager
        ])
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }
            if std::env::var("STUDIO_TAURI_DISABLE_SIDECAR").as_deref() != Ok("1") {
                let resolved_resource_root = app
                    .path()
                    .resource_dir()
                    .unwrap_or_else(|_| sidecar::default_tauri_dir());
                let resource_root = if resolved_resource_root.join("vendor").exists() {
                    resolved_resource_root
                } else {
                    sidecar::default_tauri_dir()
                };
                let config = sidecar::SidecarLaunchConfig::from_resource_root(resource_root);
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
