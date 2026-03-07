import os


class Config:
    # Flask port — can be overridden by FLASK_PORT env var set by Tauri sidecar
    PORT: int = int(os.environ.get("FLASK_PORT", 5000))

    # Database path — set by Tauri via SGAF_DB_PATH env var; Story 1.2 uses this
    DB_PATH: str = os.environ.get("SGAF_DB_PATH", "")

    # JWT secret — stored in SQLite config table after Story 1.2; placeholder here
    JWT_SECRET: str = os.environ.get("SGAF_JWT_SECRET", "")

    # Logging
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
