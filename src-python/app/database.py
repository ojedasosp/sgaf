from contextlib import contextmanager

from sqlalchemy import create_engine as _create_engine, text
from sqlalchemy.engine import Engine, URL

from app.config import Config

_engine: Engine | None = None


def get_engine() -> Engine:
    """Return the singleton SQLAlchemy engine, creating it on first call."""
    global _engine
    if _engine is None:
        missing = [v for v in ("PG_HOST", "PG_USER", "PG_PASS", "PG_DB") if not getattr(Config, v)]
        if missing:
            raise RuntimeError(
                f"Missing required environment variables: {', '.join(missing)}. "
                "Ensure db.conf is present with PG_HOST, PG_PORT, PG_USER, PG_PASS, PG_DB."
            )
        url = URL.create(
            drivername="postgresql+psycopg2",
            username=Config.PG_USER,
            password=Config.PG_PASS,
            host=Config.PG_HOST,
            port=Config.PG_PORT,
            database=Config.PG_DB,
        )
        _engine = _create_engine(url, pool_pre_ping=True)

        try:
            with _engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as exc:
            _engine = None
            # Mask password in the exception string to avoid leaking credentials in logs/events
            safe_exc = str(exc).replace(Config.PG_PASS, "***") if Config.PG_PASS else str(exc)
            raise RuntimeError(
                f"Cannot connect to PostgreSQL at "
                f"'{Config.PG_HOST}:{Config.PG_PORT}/{Config.PG_DB}': {safe_exc}. "
                "Check db.conf credentials and network connectivity."
            ) from exc
    return _engine


@contextmanager
def get_db():
    """Context manager yielding a SQLAlchemy Connection."""
    engine = get_engine()
    with engine.connect() as conn:
        yield conn
