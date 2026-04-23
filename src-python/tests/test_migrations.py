"""Tests for the migration runner."""

from sqlalchemy import inspect, text

from migrations.runner import run_migrations


def test_first_run_creates_all_tables(test_engine):
    inspector = inspect(test_engine)
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


def test_first_run_records_all_scripts(test_engine):
    with test_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT script_name FROM schema_version ORDER BY version_id")
        ).fetchall()

    script_names = [r[0] for r in rows]
    assert "001_initial_schema.sql" in script_names
    assert "002_seed_config.sql" in script_names
    assert "003_add_logo.sql" in script_names
    assert "004_pdf_tracking.sql" in script_names


def test_idempotent_rerun_does_not_duplicate(test_engine):
    run_migrations(test_engine)
    run_migrations(test_engine)  # second run

    with test_engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM schema_version")).scalar()

    # 11 migration scripts: 001–011
    assert count == 11, f"Expected 11 rows in schema_version, got {count}"


def test_seed_config_inserts_single_row(test_engine):
    with test_engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM app_config")).scalar()

    assert count == 1


def test_seed_config_idempotent(test_engine):
    run_migrations(test_engine)
    run_migrations(test_engine)

    with test_engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM app_config")).scalar()

    assert count == 1
