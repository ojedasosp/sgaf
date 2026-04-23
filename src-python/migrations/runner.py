"""Versioned SQL migration runner for SGAF.

Reads schema_version table, applies any pending .sql scripts in numeric order.
Each script runs in its own transaction — idempotent and safe to re-run.

CLI usage:
    python -m migrations.runner
    PG_HOST=... PG_PORT=5432 PG_USER=... PG_PASS=... PG_DB=... python -m migrations.runner
"""

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

import sys

# PyInstaller extracts data files to sys._MEIPASS; in dev, use the file's directory
_BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).parent.parent))
MIGRATIONS_DIR = _BASE / "migrations"


def run_migrations(engine: Engine) -> None:
    """Apply pending SQL migration scripts in order. Idempotent."""
    with engine.begin() as conn:
        conn.execute(text("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version_id SERIAL PRIMARY KEY,
                    script_name TEXT NOT NULL UNIQUE,
                    applied_at TEXT NOT NULL
                )
            """))

    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))

    for sql_file in sql_files:
        script_name = sql_file.name

        with engine.connect() as conn:
            already_applied = conn.execute(
                text("SELECT 1 FROM schema_version WHERE script_name = :name"),
                {"name": script_name},
            ).fetchone()

        if already_applied is not None:
            continue

        sql_content = sql_file.read_text(encoding="utf-8")
        applied_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        with engine.begin() as conn:
            for statement in sql_content.split(";"):
                stmt = statement.strip()
                # Skip empty statements and comment-only blocks (e.g. from semicolons inside -- comments)
                non_comment_lines = [l for l in stmt.splitlines() if l.strip() and not l.strip().startswith("--")]
                if stmt and non_comment_lines:
                    conn.execute(text(stmt))
            conn.execute(
                text("INSERT INTO schema_version (script_name, applied_at) " "VALUES (:name, :ts)"),
                {"name": script_name, "ts": applied_at},
            )
        print(f"  [OK] {script_name}")


if __name__ == "__main__":
    import os
    from sqlalchemy.engine import URL

    host = os.environ.get("PG_HOST", "")
    port = int(os.environ.get("PG_PORT", "5432"))
    user = os.environ.get("PG_USER", "")
    password = os.environ.get("PG_PASS", "")
    database = os.environ.get("PG_DB", "")

    missing = [k for k, v in {"PG_HOST": host, "PG_USER": user, "PG_PASS": password, "PG_DB": database}.items() if not v]
    if missing:
        print(f"Error: faltan variables de entorno: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    from sqlalchemy import create_engine

    url = URL.create("postgresql+psycopg2", username=user, password=password, host=host, port=port, database=database)
    engine = create_engine(url, pool_pre_ping=True)

    print(f"Conectando a {host}:{port}/{database}...")
    run_migrations(engine)
    print("Migraciones completadas.")
