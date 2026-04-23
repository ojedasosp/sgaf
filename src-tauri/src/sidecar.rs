/// Flask sidecar lifecycle management.
/// Spawns the PyInstaller binary, polls the health endpoint,
/// and emits backend-ready or backend-error events to the frontend.
use std::fs;
use std::net::TcpListener;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

/// Holds the sidecar child process so it can be killed on app exit.
pub struct SidecarChild(pub Mutex<Option<CommandChild>>);

/// Holds the backend status so the frontend can poll it if it missed the event.
#[derive(Clone, serde::Serialize)]
pub enum BackendState {
    Loading,
    Ready(u16),
    Error(String),
    SetupRequired,
}

pub struct BackendStatus(pub Mutex<BackendState>);

const HEALTH_POLL_INTERVAL_MS: u64 = 500;
const HEALTH_TIMEOUT_SECS: u64 = 30;
const DEFAULT_PORT: u16 = 5000;

/// Finds the first available TCP port starting from `start`.
/// Returns error if no available port found within 1000 attempts.
pub fn find_available_port(start: u16) -> Result<u16, String> {
    let mut port = start;
    let mut attempts = 0;
    const MAX_ATTEMPTS: u32 = 1000;

    loop {
        if TcpListener::bind(("127.0.0.1", port)).is_ok() {
            return Ok(port);
        }

        attempts += 1;
        if attempts > MAX_ATTEMPTS {
            return Err("No available port found after 1000 attempts".to_string());
        }

        port = match port.checked_add(1) {
            Some(p) => p,
            None => return Err("Port number overflow — all ports exhausted".to_string()),
        };
    }
}

/// Spawns the Flask sidecar, polls the health endpoint, and emits
/// `backend-ready` (with port payload) or `backend-error` (with message payload).
///
/// Must be called from an async context — use `tauri::async_runtime::spawn`.
pub async fn start_backend(app: AppHandle) {
    let port = match find_available_port(DEFAULT_PORT) {
        Ok(p) => p,
        Err(e) => {
            let msg = format!("Port management error: {}", e);
            if let Some(state) = app.try_state::<BackendStatus>() {
                *state.0.lock().unwrap() = BackendState::Error(msg.clone());
            }
            app.emit("backend-error", &msg).ok();
            return;
        }
    };
    let health_url = format!("http://127.0.0.1:{}/api/v1/health", port);

    // Ensure {AppData}/sgaf/ exists (home for db.conf)
    match app.path().app_data_dir() {
        Ok(app_data) => {
            if let Err(e) = fs::create_dir_all(app_data.join("sgaf")) {
                let msg = format!("Cannot create app data directory: {e}");
                if let Some(state) = app.try_state::<BackendStatus>() {
                    *state.0.lock().unwrap() = BackendState::Error(msg.clone());
                }
                app.emit("backend-error", &msg).ok();
                return;
            }
        }
        Err(e) => {
            let msg = format!("Cannot resolve app data directory: {e}");
            if let Some(state) = app.try_state::<BackendStatus>() {
                *state.0.lock().unwrap() = BackendState::Error(msg.clone());
            }
            app.emit("backend-error", &msg).ok();
            return;
        }
    }

    // If db.conf doesn't exist, prompt user to configure the connection
    match crate::db_config::config_path(&app) {
        Ok(path) if !path.exists() => {
            if let Some(state) = app.try_state::<BackendStatus>() {
                *state.0.lock().unwrap() = BackendState::SetupRequired;
            }
            app.emit("db-setup-required", ()).ok();
            return;
        }
        Err(e) => {
            let msg = format!("Cannot resolve db.conf path: {e}");
            if let Some(state) = app.try_state::<BackendStatus>() {
                *state.0.lock().unwrap() = BackendState::Error(msg.clone());
            }
            app.emit("backend-error", &msg).ok();
            return;
        }
        _ => {} // File exists — proceed to load
    }

    // Load PostgreSQL credentials from {AppData}/sgaf/db.conf
    let db_cfg = match crate::db_config::load(&app) {
        Ok(cfg) => cfg,
        Err(msg) => {
            if let Some(state) = app.try_state::<BackendStatus>() {
                *state.0.lock().unwrap() = BackendState::Error(msg.clone());
            }
            app.emit("backend-error", &msg).ok();
            return;
        }
    };

    // Spawn sidecar binary with FLASK_PORT and PostgreSQL env vars
    let sidecar_result = app
        .shell()
        .sidecar("sgaf-backend")
        .map(|cmd| {
            cmd.env("FLASK_PORT", port.to_string())
                .env("PG_HOST", &db_cfg.host)
                .env("PG_PORT", &db_cfg.port)
                .env("PG_USER", &db_cfg.user)
                .env("PG_PASS", &db_cfg.pass)
                .env("PG_DB",   &db_cfg.db)
        })
        .and_then(|cmd| cmd.spawn());

    let _rx = match sidecar_result {
        Err(e) => {
            let msg = format!("Failed to spawn backend: {}", e);
            if let Some(state) = app.try_state::<BackendStatus>() {
                *state.0.lock().unwrap() = BackendState::Error(msg.clone());
            }
            app.emit("backend-error", &msg).ok();
            return;
        }
        Ok((rx, child)) => {
            // Store child in app state so it can be killed on exit
            if let Some(state) = app.try_state::<SidecarChild>() {
                *state.0.lock().unwrap() = Some(child);
            }
            rx
        }
    };

    // Poll health endpoint until backend responds or timeout
    let deadline = Instant::now() + Duration::from_secs(HEALTH_TIMEOUT_SECS);
    let client = Arc::new(reqwest::Client::new());

    loop {
        if Instant::now() > deadline {
            let msg = format!("Backend failed to start within {} seconds", HEALTH_TIMEOUT_SECS);
            if let Some(state) = app.try_state::<BackendStatus>() {
                *state.0.lock().unwrap() = BackendState::Error(msg.clone());
            }
            app.emit("backend-error", &msg).ok();
            return;
        }

        let resp = client
            .get(&health_url)
            .timeout(Duration::from_millis(HEALTH_POLL_INTERVAL_MS))
            .send()
            .await;

        if let Ok(response) = resp {
            if response.status().is_success() {
                // Show the window now that backend is ready
                if let Some(window) = app.get_webview_window("main") {
                    window.show().ok();
                    window.set_focus().ok();
                }
                if let Some(state) = app.try_state::<BackendStatus>() {
                    *state.0.lock().unwrap() = BackendState::Ready(port);
                }
                app.emit("backend-ready", port).ok();
                return;
            }
        }

        tokio::time::sleep(Duration::from_millis(HEALTH_POLL_INTERVAL_MS)).await;
    }
}
