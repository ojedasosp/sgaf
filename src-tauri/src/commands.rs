/// Tauri invoke() commands — OS-level operations only.
/// Business logic goes through fetch() to Flask, not through these commands.
use tauri::{AppHandle, Manager};

use crate::sidecar::{BackendState, BackendStatus, SidecarChild};

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

/// Writes binary content to a file path. Used for PDF/CSV export.
/// Returns error string if write fails.
#[tauri::command]
pub fn write_binary_file(path: String, content: Vec<u8>) -> Result<(), String> {
    std::fs::write(&path, &content).map_err(|e| format!("Failed to write file: {}", e))
}

/// Persists PostgreSQL connection parameters to {AppData}/sgaf/db.conf.
/// Called by the DB setup wizard before triggering backend startup.
#[tauri::command]
pub fn save_db_config(
    app: AppHandle,
    host: String,
    port: String,
    user: String,
    pass: String,
    db: String,
) -> Result<(), String> {
    // Prevent newlines from breaking the KEY=VALUE file format
    for val in &[&host, &user, &pass, &db, &port] {
        if val.contains('\n') || val.contains('\r') {
            return Err("Invalid character in connection parameter".to_string());
        }
    }
    let app_data = app
        .path()
        .app_data_dir()
        .map_err(|e| format!("Cannot resolve app data directory: {e}"))?;
    let config_path = app_data.join("sgaf").join("db.conf");
    let content = format!(
        "PG_HOST={}\nPG_PORT={}\nPG_USER={}\nPG_PASS={}\nPG_DB={}\n",
        host, port, user, pass, db
    );
    std::fs::write(&config_path, content).map_err(|e| format!("Failed to write db.conf: {e}"))
}

/// Removes db.conf so the next backend start triggers the setup wizard again.
/// Used by the "Reconfigurar" button on the error screen.
#[tauri::command]
pub fn reset_db_config(app: AppHandle) -> Result<(), String> {
    let app_data = app
        .path()
        .app_data_dir()
        .map_err(|e| format!("Cannot resolve app data directory: {e}"))?;
    let path = app_data.join("sgaf").join("db.conf");
    if path.exists() {
        std::fs::remove_file(&path).map_err(|e| format!("Cannot delete db.conf: {e}"))?;
    }
    Ok(())
}

/// Kills any running sidecar and restarts the backend.
/// Used after saving db.conf to attempt a new connection.
#[tauri::command]
pub fn retry_backend(app: AppHandle) {
    // Kill any existing sidecar before spawning a new one
    if let Some(child_state) = app.try_state::<SidecarChild>() {
        if let Some(child) = child_state.0.lock().unwrap().take() {
            let _ = child.kill();
        }
    }
    if let Some(state) = app.try_state::<BackendStatus>() {
        *state.0.lock().unwrap() = BackendState::Loading;
    }
    tauri::async_runtime::spawn(async move {
        crate::sidecar::start_backend(app).await;
    });
}
