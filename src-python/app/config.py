import os


class Config:
    # Flask port — can be overridden by FLASK_PORT env var set by Tauri sidecar
    PORT: int = int(os.environ.get("FLASK_PORT", 5000))

    # PostgreSQL connection parameters — set by Tauri via db.conf env vars
    PG_HOST: str = os.environ.get("PG_HOST", "")
    PG_PORT: int = int(os.environ.get("PG_PORT", "5432"))
    PG_USER: str = os.environ.get("PG_USER", "")
    PG_PASS: str = os.environ.get("PG_PASS", "")
    PG_DB:   str = os.environ.get("PG_DB", "")

    # JWT secret — stored in SQLite config table after Story 1.2; placeholder here
    JWT_SECRET: str = os.environ.get("SGAF_JWT_SECRET", "")

    # Logging
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
