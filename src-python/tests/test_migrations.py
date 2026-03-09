"""Tests for the migration runner."""

from sqlalchemy import create_engine, inspect, text

from migrations.runner import run_migrations


def make_engine():
    return create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})


def test_first_run_creates_all_tables():
    engine = make_engine()
    run_migrations(engine)

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    expected = {
        "schema_version",
        "app_config",
        "fixed_assets",
        "depreciation_results",
        "maintenance_events",
        "audit_logs",
    }
    assert expected.issubset(table_names), f"Missing tables: {expected - table_names}"


def test_first_run_records_all_scripts():
    engine = make_engine()
    run_migrations(engine)

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT script_name FROM schema_version ORDER BY version_id")
        ).fetchall()

    script_names = [r[0] for r in rows]
    assert "001_initial_schema.sql" in script_names
    assert "002_seed_config.sql" in script_names
    assert "003_add_logo.sql" in script_names


def test_idempotent_rerun_does_not_duplicate():
    engine = make_engine()
    run_migrations(engine)
    run_migrations(engine)  # second run

    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM schema_version")).scalar()

    # 3 migration scripts: 001, 002, 003
    assert count == 3, f"Expected 3 rows in schema_version, got {count}"


def test_seed_config_inserts_single_row():
    engine = make_engine()
    run_migrations(engine)

    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM app_config")).scalar()

    assert count == 1


def test_seed_config_idempotent():
    engine = make_engine()
    run_migrations(engine)
    run_migrations(engine)

    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM app_config")).scalar()

    assert count == 1


def test_wal_pragma_in_migration_script():
    """001_initial_schema.sql contains the WAL mode pragma.

    Note: in-memory SQLite always reports 'memory' journal mode regardless of
    PRAGMA journal_mode=WAL, so we verify the pragma is present in the script
    rather than querying the runtime value.
    """
    from pathlib import Path

    script = (Path(__file__).parent.parent / "migrations" / "001_initial_schema.sql").read_text()
    assert "journal_mode=WAL" in script
