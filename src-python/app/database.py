from contextlib import contextmanager

from sqlalchemy import create_engine as _create_engine
from sqlalchemy import event, text
from sqlalchemy.engine import Engine

from app.config import Config

_engine: Engine | None = None


def get_engine() -> Engine:
    """Return the singleton SQLAlchemy engine, creating it on first call.

    Raises RuntimeError if SGAF_DB_PATH is not set or the DB is unreachable.
    """
    global _engine
    if _engine is None:
        if not Config.DB_PATH:
            raise RuntimeError(
                "SGAF_DB_PATH environment variable is not set. "
                "Ensure the Tauri sidecar passes the DB path on startup."
            )
        _engine = _create_engine(
            f"sqlite:///{Config.DB_PATH}",
            connect_args={"check_same_thread": False},
        )

        # Enforce foreign key constraints on every connection
        @event.listens_for(_engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        # Verify the connection is valid — catches missing dir / permission errors
        try:
            with _engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as exc:
            _engine = None
            raise RuntimeError(
                f"Cannot open SQLite database at '{Config.DB_PATH}': {exc}. "
                "Check that the directory exists and SGAF has write permissions."
            ) from exc
    return _engine


@contextmanager
def get_db():
    """Context manager yielding a SQLAlchemy Connection."""
    engine = get_engine()
    with engine.connect() as conn:
        yield conn
