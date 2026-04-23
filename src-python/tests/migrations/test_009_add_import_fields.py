"""Tests for migration 009: Add import fields to fixed_assets.

Covers:
- AC1: Migration applies without data loss; all 12 new columns created; schema_version updated.
- AC2: NULL additions_improvements is safe — treated as Decimal('0').
- AC3: NULL imported_accumulated_depreciation is safe — treated as Decimal('0').
"""

from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import inspect, text

from app.utils.decimal_utils import from_db_string
from migrations.runner import run_migrations

MIGRATION_SCRIPT = "009_add_import_fields.sql"

NEW_COLUMNS = [
    "accounting_code",
    "characteristics",
    "location",
    "cost_center",
    "quantity",
    "vat_amount",
    "additions_improvements",
    "fiscal_value",
    "revaluation",
    "supplier",
    "invoice_number",
    "imported_accumulated_depreciation",
]

# NULL-safe Decimal conversion idiom as documented in Dev Notes — Story 8.4
# MUST implement this exact pattern (truthy check + from_db_string) so that
# both NULL and empty-string values are coerced to Decimal("0") without raising.
def _nullable_decimal(raw_value):
    return from_db_string(raw_value) if raw_value else Decimal("0")


# Path to the real migrations directory — used for the data-preservation test
# which must apply migrations 001–008 before inserting pre-existing rows and
# then apply 009 on top to verify the AC1 scenario.
MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"


@pytest.fixture(autouse=True)
def _cleanup_test_rows(test_engine):
    """Delete rows inserted by this module's tests after each test to prevent UniqueViolation on re-run."""
    yield
    with test_engine.begin() as conn:
        conn.execute(text("DELETE FROM fixed_assets WHERE code LIKE 'TEST-%'"))


def _apply_sql_file(engine, sql_file: Path) -> None:
    """Execute all statements in an SQL file within a single transaction."""
    sql_content = sql_file.read_text(encoding="utf-8")
    with engine.begin() as conn:
        for statement in sql_content.split(";"):
            stmt = statement.strip()
            if stmt:
                conn.execute(text(stmt))


def _ensure_schema_version_table(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                    version_id SERIAL PRIMARY KEY,
                    script_name TEXT NOT NULL UNIQUE,
                    applied_at TEXT NOT NULL
                )
                """
            )
        )


# ---------------------------------------------------------------------------
# Task 3.1 — AC1: Migration creates all 12 new columns and preserves data
# ---------------------------------------------------------------------------


def test_migration_009_creates_all_new_columns(test_engine):
    """All 12 import columns are present in fixed_assets after running migrations."""
    inspector = inspect(test_engine)
    col_names = {c["name"] for c in inspector.get_columns("fixed_assets")}

    missing = [col for col in NEW_COLUMNS if col not in col_names]
    assert not missing, f"Missing columns after migration 009: {missing}"


def test_migration_009_preserves_existing_data_through_upgrade(test_engine_pre_009):
    """AC1: Pre-existing assets survive the 009 migration with all columns intact.

    This test reflects the real AC1 scenario: a DB populated at the 008 schema,
    then upgraded to 009. Data must remain and new columns must appear as NULL
    (or default 1 for quantity).
    """
    engine = test_engine_pre_009

    # Insert a row at the pre-009 schema level
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO fixed_assets
                    (code, description, historical_cost, salvage_value,
                     useful_life_months, acquisition_date, category,
                     depreciation_method, status, created_at, updated_at)
                VALUES
                    ('TEST-001', 'Laptop Test', '5000.0000', '500.0000',
                     60, '2020-01-15', 'Equipos de Cómputo',
                     'straight_line', 'active', '2020-01-15T00:00:00Z', '2020-01-15T00:00:00Z')
                """
            )
        )

    # Now apply migration 009 on top of the existing data
    _apply_sql_file(engine, MIGRATIONS_DIR / MIGRATION_SCRIPT)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO schema_version (script_name, applied_at) "
                "VALUES (:name, :ts)"
            ),
            {"name": MIGRATION_SCRIPT, "ts": "2026-04-12T00:00:00Z"},
        )

    with engine.connect() as conn:
        row = (
            conn.execute(text("SELECT * FROM fixed_assets WHERE code = 'TEST-001'"))
            .mappings()
            .fetchone()
        )

    # Original columns retain their values
    assert row["code"] == "TEST-001"
    assert row["description"] == "Laptop Test"
    assert row["historical_cost"] == "5000.0000"
    assert row["salvage_value"] == "500.0000"
    assert row["useful_life_months"] == 60
    assert row["acquisition_date"] == "2020-01-15"
    assert row["category"] == "Equipos de Cómputo"
    assert row["depreciation_method"] == "straight_line"
    assert row["status"] == "active"

    # New columns appear after upgrade: TEXT columns NULL, quantity defaults to 1
    for col in NEW_COLUMNS:
        if col == "quantity":
            assert row["quantity"] == 1, f"quantity should default to 1, got {row['quantity']}"
        else:
            assert row[col] is None, f"Column '{col}' should be NULL after upgrade, got {row[col]!r}"


def test_migration_009_recorded_in_schema_version(test_engine):
    """schema_version table records 009_add_import_fields.sql as applied."""
    with test_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT script_name FROM schema_version ORDER BY version_id")
        ).fetchall()

    script_names = [r[0] for r in rows]
    assert MIGRATION_SCRIPT in script_names, (
        f"'{MIGRATION_SCRIPT}' not found in schema_version. Found: {script_names}"
    )


def test_migration_009_idempotent(test_engine):
    """Running migrations again does not duplicate the 009 entry in schema_version."""
    run_migrations(test_engine)  # second run on the already-migrated fixture

    with test_engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM schema_version WHERE script_name = :name"),
            {"name": MIGRATION_SCRIPT},
        ).scalar()

    assert count == 1, f"Expected 1 entry for {MIGRATION_SCRIPT}, got {count}"


def test_migration_009_total_schema_version_count(test_engine):
    """After all migrations, schema_version has exactly 11 applied scripts (001–011)."""
    with test_engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM schema_version")).scalar()

    assert count == 11, f"Expected 11 rows in schema_version after all migrations, got {count}"


# ---------------------------------------------------------------------------
# Task 3.3 — AC2 & AC3: NULL-safe Decimal conversion contract
# ---------------------------------------------------------------------------


def test_ac2_null_additions_improvements_is_safe(test_engine):
    """AC2: NULL additions_improvements → Decimal('0') using Story 8.4 idiom."""
    with test_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO fixed_assets
                    (code, description, historical_cost, salvage_value,
                     useful_life_months, acquisition_date, category,
                     depreciation_method, status, created_at, updated_at,
                     additions_improvements)
                VALUES
                    ('TEST-AC2', 'Asset AC2', '10000.0000', '1000.0000',
                     48, '2021-06-01', 'Maquinaria y Equipo',
                     'straight_line', 'active', '2021-06-01T00:00:00Z', '2021-06-01T00:00:00Z',
                     NULL)
                """
            )
        )

    with test_engine.connect() as conn:
        row = (
            conn.execute(
                text("SELECT additions_improvements FROM fixed_assets WHERE code = 'TEST-AC2'")
            )
            .mappings()
            .fetchone()
        )

    raw_value = row["additions_improvements"]
    assert raw_value is None, f"Expected NULL, got {raw_value!r}"

    # Story 8.4 contract: truthy check + from_db_string — NO exception raised.
    result = _nullable_decimal(raw_value)
    assert result == Decimal("0"), f"Expected Decimal('0'), got {result}"


def test_ac3_null_imported_accumulated_depreciation_is_safe(test_engine):
    """AC3: NULL imported_accumulated_depreciation → Decimal('0') — no error."""
    with test_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO fixed_assets
                    (code, description, historical_cost, salvage_value,
                     useful_life_months, acquisition_date, category,
                     depreciation_method, status, created_at, updated_at,
                     imported_accumulated_depreciation)
                VALUES
                    ('TEST-AC3', 'Asset AC3', '8000.0000', '800.0000',
                     36, '2022-03-15', 'Vehículos',
                     'declining_balance', 'active', '2022-03-15T00:00:00Z', '2022-03-15T00:00:00Z',
                     NULL)
                """
            )
        )

    with test_engine.connect() as conn:
        row = (
            conn.execute(
                text(
                    "SELECT imported_accumulated_depreciation "
                    "FROM fixed_assets WHERE code = 'TEST-AC3'"
                )
            )
            .mappings()
            .fetchone()
        )

    raw_value = row["imported_accumulated_depreciation"]
    assert raw_value is None, f"Expected NULL, got {raw_value!r}"

    result = _nullable_decimal(raw_value)
    assert result == Decimal("0"), f"Expected Decimal('0'), got {result}"


def test_ac2_ac3_empty_string_is_safe():
    """The Story 8.4 idiom treats empty string like NULL — no ValueError.

    This matters because `from_db_string("")` raises ValueError; the truthy
    check protects against that. Pin the contract so Story 8.4 does not
    accidentally use `is not None` instead of a truthy check.
    """
    assert _nullable_decimal(None) == Decimal("0")
    assert _nullable_decimal("") == Decimal("0")


def test_ac2_non_null_additions_improvements_converts_correctly(test_engine):
    """AC2 positive case: a stored TEXT value converts to correct Decimal via from_db_string."""
    with test_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO fixed_assets
                    (code, description, historical_cost, salvage_value,
                     useful_life_months, acquisition_date, category,
                     depreciation_method, status, created_at, updated_at,
                     additions_improvements)
                VALUES
                    ('TEST-AC2B', 'Asset with improvements', '20000.0000', '2000.0000',
                     60, '2023-01-01', 'Equipos de Cómputo',
                     'sum_of_digits', 'active', '2023-01-01T00:00:00Z', '2023-01-01T00:00:00Z',
                     '3500.5000')
                """
            )
        )

    with test_engine.connect() as conn:
        row = (
            conn.execute(
                text("SELECT additions_improvements FROM fixed_assets WHERE code = 'TEST-AC2B'")
            )
            .mappings()
            .fetchone()
        )

    result = _nullable_decimal(row["additions_improvements"])
    assert result == Decimal("3500.5000")
    assert isinstance(result, Decimal), "Must be Decimal, not float"
