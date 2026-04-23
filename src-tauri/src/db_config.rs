//! Reads PostgreSQL connection parameters from {AppData}/sgaf/db.conf.
//!
//! File format — one `KEY=VALUE` per line; `#` lines and blank lines are ignored:
//!   PG_HOST=myserver.example.com
//!   PG_PORT=5432
//!   PG_USER=sgaf_user
//!   PG_PASS=secret
//!   PG_DB=sgaf_production

use std::collections::HashMap;
use std::fs;
use tauri::Manager;

pub struct DbConfig {
    pub host: String,
    pub port: String,
    pub user: String,
    pub pass: String,
    pub db: String,
}

/// Returns the path to `db.conf` without reading it.
pub fn config_path(app: &tauri::AppHandle) -> Result<std::path::PathBuf, String> {
    app.path()
        .app_data_dir()
        .map(|p| p.join("sgaf").join("db.conf"))
        .map_err(|e| format!("Cannot resolve app data directory: {e}"))
}

pub fn load(app: &tauri::AppHandle) -> Result<DbConfig, String> {
    let app_data = app
        .path()
        .app_data_dir()
        .map_err(|e| format!("Cannot resolve app data directory: {e}"))?;

    let config_path = app_data.join("sgaf").join("db.conf");

    let content = fs::read_to_string(&config_path).map_err(|e| {
        format!(
            "Cannot read db.conf at '{}': {e}. \
             Create this file with PG_HOST, PG_PORT, PG_USER, PG_PASS, PG_DB entries.",
            config_path.display()
        )
    })?;

    let mut map: HashMap<String, String> = HashMap::new();
    for line in content.lines() {
        let line = line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        if let Some((key, val)) = line.split_once('=') {
            // Strip inline comments (e.g. `PG_PORT=5432 # default`)
            let val = val.split('#').next().unwrap_or("").trim();
            map.insert(key.trim().to_string(), val.to_string());
        }
    }

    let get = |key: &str| -> Result<String, String> {
        map.get(key)
            .cloned()
            .filter(|v| !v.is_empty())
            .ok_or_else(|| format!("Missing or empty key '{key}' in db.conf"))
    };

    Ok(DbConfig {
        host: get("PG_HOST")?,
        port: get("PG_PORT").unwrap_or_else(|_| "5432".to_string()),
        user: get("PG_USER")?,
        pass: get("PG_PASS")?,
        db: get("PG_DB")?,
    })
}
