/// Tauri invoke() commands — OS-level operations only.
/// Business logic goes through fetch() to Flask, not through these commands.
use tauri::{AppHandle, Manager};

/// Returns the application data directory path for SGAF.
/// Frontend uses this to display the DB location, never to access it directly.
#[tauri::command]
pub fn get_app_data_path(app: AppHandle) -> Result<String, String> {
    app.path()
        .app_data_dir()
        .map(|p| p.to_string_lossy().to_string())
        .map_err(|e| format!("Failed to get app data path: {}", e))
}
