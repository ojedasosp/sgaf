pub mod commands;
pub mod db_config;
pub mod sidecar;

use std::sync::Mutex;
use tauri::Manager;

use crate::sidecar::{BackendState, BackendStatus, SidecarChild};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(SidecarChild(Mutex::new(None)))
        .manage(BackendStatus(Mutex::new(BackendState::Loading)))
        .setup(|app| {
            // Hide the main window until Flask sidecar is ready (NFR15)
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.hide();
            }

            // Spawn Flask sidecar in background — will emit backend-ready or backend-error
            let app_handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                sidecar::start_backend(app_handle).await;
            });

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                // Kill the sidecar process when the main window closes
                if let Some(state) = window.try_state::<SidecarChild>() {
                    if let Some(child) = state.0.lock().unwrap().take() {
                        let _ = child.kill();
                    }
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            commands::get_app_data_path,
            commands::get_backend_status,
            commands::write_binary_file,
            commands::save_db_config,
            commands::reset_db_config,
            commands::retry_backend,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
