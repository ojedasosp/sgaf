/// Flask sidecar lifecycle management.
/// Spawns the PyInstaller binary, polls the health endpoint,
/// and emits backend-ready or backend-error events to the frontend.
use std::net::TcpListener;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_shell::ShellExt;

const HEALTH_POLL_INTERVAL_MS: u64 = 500;
const HEALTH_TIMEOUT_SECS: u64 = 30;
const DEFAULT_PORT: u16 = 5000;

/// Finds the first available TCP port starting from `start`.
pub fn find_available_port(start: u16) -> u16 {
    let mut port = start;
    loop {
        if TcpListener::bind(("127.0.0.1", port)).is_ok() {
            return port;
        }
        port = port.checked_add(1).expect("No available port found in range");
    }
}

/// Spawns the Flask sidecar, polls the health endpoint, and emits
/// `backend-ready` (with port payload) or `backend-error` (with message payload).
///
/// Must be called from an async context — use `tauri::async_runtime::spawn`.
pub async fn start_backend(app: AppHandle) {
    let port = find_available_port(DEFAULT_PORT);
    let health_url = format!("http://127.0.0.1:{}/api/v1/health", port);

    // Spawn sidecar binary with FLASK_PORT env var so Flask listens on the right port
    let sidecar_result = app
        .shell()
        .sidecar("sgaf-backend")
        .map(|cmd| cmd.env("FLASK_PORT", port.to_string()))
        .and_then(|cmd| cmd.spawn());

    match sidecar_result {
        Err(e) => {
            let msg = format!("Failed to spawn backend: {}", e);
            app.emit("backend-error", &msg).ok();
            return;
        }
        Ok((_rx, _child)) => {
            // child is held alive; _rx receives stdout/stderr lines
        }
    }

    // Poll health endpoint until backend responds or timeout
    let deadline = Instant::now() + Duration::from_secs(HEALTH_TIMEOUT_SECS);
    let client = Arc::new(reqwest::Client::new());

    loop {
        if Instant::now() > deadline {
            app.emit(
                "backend-error",
                format!("Backend failed to start within {} seconds", HEALTH_TIMEOUT_SECS),
            )
            .ok();
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
                app.emit("backend-ready", port).ok();
                return;
            }
        }

        tokio::time::sleep(Duration::from_millis(HEALTH_POLL_INTERVAL_MS)).await;
    }
}
