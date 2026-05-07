mod sidecar;

use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc,
};
use tauri::Manager;

#[tauri::command]
fn get_sidecar_config(
    manager: tauri::State<'_, sidecar::SidecarManager>,
) -> sidecar::SidecarRuntimeConfig {
    manager.runtime_config()
}

#[tauri::command]
fn get_sidecar_stderr(manager: tauri::State<'_, sidecar::SidecarManager>) -> Vec<String> {
    manager.recent_stderr()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            get_sidecar_config,
            get_sidecar_stderr
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
                let manager = sidecar::SidecarManager::start(config)
                    .map_err(|err| format!("failed to start Python sidecar: {err}"))?;
                app.manage(manager);
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
                if let Some(manager) = app_handle.try_state::<sidecar::SidecarManager>() {
                    manager.shutdown_blocking();
                }
                app_handle.exit(0);
            });
        }
    });
}
