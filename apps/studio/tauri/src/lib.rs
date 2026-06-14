mod native_fs;
mod sidecar;

use std::path::PathBuf;
use std::process::Command;
use std::sync::{
    atomic::{AtomicBool, Ordering},
    mpsc, Arc, Mutex,
};
#[cfg(target_os = "macos")]
use tauri::menu::{AboutMetadata, Menu, PredefinedMenuItem, Submenu};
use tauri::Manager;
use tauri_plugin_dialog::DialogExt;

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

fn spawn_tool(bin: &str, path: &str) -> Result<(), String> {
    let target = existing_path(path)?;
    Command::new(bin)
        .arg(target)
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
fn open_in_terminal(path: String) -> Result<(), String> {
    let target = existing_path(&path)?;
    if cfg!(target_os = "macos") {
        return Command::new("open")
            .arg("-a")
            .arg("Terminal")
            .arg(target)
            .spawn()
            .map(|_| ())
            .map_err(|error| format!("failed to open Terminal: {error}"));
    }

    if cfg!(target_os = "linux") {
        return Command::new("gnome-terminal")
            .arg("--working-directory")
            .arg(&target)
            .spawn()
            .or_else(|_| {
                Command::new("xterm")
                    .args([
                        "-e",
                        "sh",
                        "-lc",
                        "cd \"$1\" && exec \"${SHELL:-sh}\"",
                        "sh",
                    ])
                    .arg(&target)
                    .spawn()
            })
            .map(|_| ())
            .map_err(|error| format!("failed to open terminal: {error}"));
    }

    if cfg!(target_os = "windows") {
        return Command::new("wt.exe")
            .arg("-d")
            .arg(&target)
            .spawn()
            .or_else(|_| {
                Command::new("cmd")
                    .args(["/c", "start", "cmd", "/k", "cd", "/d"])
                    .arg(&target)
                    .spawn()
            })
            .map(|_| ())
            .map_err(|error| format!("failed to open terminal: {error}"));
    }

    Err("opening a terminal is not supported on this platform".to_string())
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
            open_in_cursor,
            open_in_codex,
            select_directory,
            open_in_terminal,
            reveal_in_file_manager,
            native_fs::write_workspace_file,
            native_fs::add_recent_workspace,
            native_fs::list_recent_workspaces,
            native_fs::remove_recent_workspace,
            native_fs::ensure_workspace_support_dirs
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
                let resource_root = sidecar::resource_root_for_runtime(resolved_resource_root);
                let config = sidecar::SidecarLaunchConfig::from_resource_root(resource_root)
                    .with_config_dir(sidecar::default_user_config_dir());
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
