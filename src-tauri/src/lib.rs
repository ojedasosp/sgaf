pub mod commands;
pub mod sidecar;

use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
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
        .invoke_handler(tauri::generate_handler![commands::get_app_data_path])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
