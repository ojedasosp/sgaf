/// Tauri invoke() commands — OS-level operations only.
/// Business logic goes through fetch() to Flask, not through these commands.
use tauri::{AppHandle, Manager};

use crate::sidecar::{BackendState, BackendStatus};

/// Returns the application data directory path for SGAF.
/// Frontend uses this to display the DB location, never to access it directly.
#[tauri::command]
pub fn get_app_data_path(app: AppHandle) -> Result<String, String> {
    app.path()
        .app_data_dir()
        .map(|p| p.to_string_lossy().to_string())
        .map_err(|e| format!("Failed to get app data path: {}", e))
}

/// Returns the current backend status so the frontend can poll if it missed the event.
#[tauri::command]
pub fn get_backend_status(app: AppHandle) -> Result<BackendState, String> {
    app.try_state::<BackendStatus>()
        .map(|state| state.0.lock().unwrap().clone())
        .ok_or_else(|| "Backend status not available".to_string())
}
