"""Tests for scripts/import_assets_csv.py (Story 8.3)."""

from __future__ import annotations

import pathlib
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event, select, text

from app.models.tables import audit_logs, fixed_assets
from app.utils.audit_logger import AuditLogger
from migrations.runner import run_migrations
from scripts.import_assets_csv import (
    _decimal_or_none_to_db,
    _map_engine_method,
    _normalize_row,
    build_insert_payload,
    get_category_defaults,
    main,
    parse_decimal_or_none,
    parse_int_or_default,
    parse_iso_date,
    parse_required_decimal,
    run_import,
)

CSV_HEADERS = [
    "CODCONTABLE",
    "CODIGO",
    "DESCRIPCION",
    "TIPO",
    "CARACTERISTICAS",
    "UBICACIÓN",
    "CENTRO COSTO",
    "CANTIDAD",
    "VALOR",
    "IVA",
    "ADICI_MEJORAS",
    "AIPI",
    "DEPRECIACION",
    "AIPI DEP",
    "VALOR FISCAL",
    "REVALORIZACION",
    "F.ADQ",
    "PROVEEDOR",
    "FACTURA",
]


def _write_csv(
    path: pathlib.Path,
    rows: list[dict[str, str]],
    *,
    headers: list[str] = CSV_HEADERS,
    delimiter: str = ";",
    encoding: str = "cp1252",
) -> pathlib.Path:
    """Create a semicolon-delimited CSV at ``path`` using ``headers``."""
    lines = [delimiter.join(headers)]
    for row in rows:
        lines.append(delimiter.join(row.get(h, "") for h in headers))
    path.write_text("\n".join(lines) + "\n", encoding=encoding)
    return path


def _init_db(db_path: pathlib.Path) -> None:
    """Create an empty SQLite DB at ``db_path`` with all migrations applied."""
    engine = create_engine(f"sqlite:///{db_path}")

    @event.listens_for(engine, "connect")
    def _pragma(dbapi_conn, _record):  # pragma: no cover — wiring only
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    run_migrations(engine)
    engine.dispose()


def _base_row(**overrides: str) -> dict[str, str]:
    """Return a fully valid row with overridable fields."""
    row = {
        "CODCONTABLE": "15200501",
        "CODIGO": "TEST-001",
        "DESCRIPCION": "  Test asset  ",  # includes padding to exercise trim
        "TIPO": "MAQUINARIA Y EQUIPOS",
        "CARACTERISTICAS": "specs",
        "UBICACIÓN": "BODEGA",
        "CENTRO COSTO": "ADM",
        "CANTIDAD": "1",
        "VALOR": "1200000",
        "IVA": "228000",
        "ADICI_MEJORAS": "0",
        "AIPI": "9999",  # ignored
        "DEPRECIACION": "500000",
        "AIPI DEP": "9999",  # ignored
        "VALOR FISCAL": "700000",
        "REVALORIZACION": "",
        "F.ADQ": "2015.06.20",
        "PROVEEDOR": "Test supplier",
        "FACTURA": "INV-0001",
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# Unit tests: helpers
# ---------------------------------------------------------------------------


class TestParseDecimalOrNone:
    def test_empty_returns_none(self):
        assert parse_decimal_or_none("") is None
        assert parse_decimal_or_none(None) is None
        assert parse_decimal_or_none("   ") is None

    def test_comma_as_decimal_separator(self):
        # AC2
        assert parse_decimal_or_none("11896318,06") == Decimal("11896318.06")
        assert parse_decimal_or_none("3495760,9") == Decimal("3495760.9")

    def test_dot_decimal_still_works(self):
        assert parse_decimal_or_none("1234.56") == Decimal("1234.56")

    def test_dotted_thousands_with_comma_decimal(self):
        assert parse_decimal_or_none("1.234,56") == Decimal("1234.56")

    def test_invalid_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_decimal_or_none("not-a-number")

    def test_negative_accepted(self):
        assert parse_decimal_or_none("-8398068") == Decimal("-8398068")


class TestParseRequiredDecimal:
    def test_empty_raises(self):
        with pytest.raises(ValueError, match="required"):
            parse_required_decimal("", "VALOR")

    def test_valid_returns_decimal(self):
        assert parse_required_decimal("1200.00", "VALOR") == Decimal("1200.00")


class TestParseIsoDate:
    def test_full_date_converts(self):
        # AC7
        assert parse_iso_date("2011.09.08") == "2011-09-08"

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="required"):
            parse_iso_date("")
        with pytest.raises(ValueError, match="required"):
            parse_iso_date(None)

    def test_year_only_rejected(self):
        with pytest.raises(ValueError):
            parse_iso_date("2015")

    def test_malformed_rejected(self):
        with pytest.raises(ValueError):
            parse_iso_date("08/09/2011")


class TestParseIntOrDefault:
    def test_empty_returns_default(self):
        assert parse_int_or_default("", 1) == 1
        assert parse_int_or_default(None, 1) == 1

    def test_valid_parses(self):
        assert parse_int_or_default("2", 1) == 2

    def test_malformed_returns_default(self):
        assert parse_int_or_default("abc", 1) == 1


class TestMapEngineMethod:
    def test_lineal_maps_to_straight_line(self):
        assert _map_engine_method("lineal") == "straight_line"

    def test_none_passes_through(self):
        assert _map_engine_method("none") == "none"

    def test_unknown_raises(self):
        with pytest.raises(ValueError):
            _map_engine_method("geometric")


class TestGetCategoryDefaults:
    def test_unknown_raises(self):
        # AC8
        with pytest.raises(ValueError, match="MOBILIARIO"):
            get_category_defaults("MOBILIARIO", {"TERRENOS": {}})

    def test_known_returns_entry(self):
        defaults = {"TERRENOS": {"useful_life_months": 0}}
        assert get_category_defaults("TERRENOS", defaults) == {"useful_life_months": 0}


class TestNormalizeRow:
    def test_drops_ignored_columns(self):
        # AC9
        raw = {"AIPI": "999", "AIPI DEP": "999", "CODIGO": "X"}
        normalized = _normalize_row(raw)
        assert "AIPI" not in normalized
        assert "AIPI DEP" not in normalized
        assert normalized["code"] == "X"

    def test_strips_trailing_whitespace_in_headers(self):
        raw = {"DESCRIPCION ": "padded", "VALOR ": "1"}
        normalized = _normalize_row(raw)
        assert normalized["description"] == "padded"
        assert normalized["historical_cost"] == "1"


# ---------------------------------------------------------------------------
# Integration tests: run_import
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path):
    db_path = tmp_path / "sgaf_test.db"
    db_path.touch()
    _init_db(db_path)
    return db_path


def _row_count(db_path: pathlib.Path, table) -> int:
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.connect() as conn:
            return conn.execute(text(f"SELECT count(*) FROM {table.name}")).scalar_one()
    finally:
        engine.dispose()


def _fetch_all(db_path: pathlib.Path, table):
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.connect() as conn:
            return conn.execute(select(table)).fetchall()
    finally:
        engine.dispose()


class TestDryRun:
    def test_ac1_dry_run_writes_nothing(self, tmp_path, tmp_db):
        # AC1
        csv_path = _write_csv(
            tmp_path / "in.csv",
            [
                _base_row(CODIGO="A"),
                _base_row(CODIGO="B"),
                _base_row(CODIGO="C"),
            ],
        )
        report = run_import(csv_path, tmp_db, dry_run=True)
        assert report.total_read == 3
        assert len(report.errors) == 0
        assert _row_count(tmp_db, fixed_assets) == 0
        assert _row_count(tmp_db, audit_logs) == 0


class TestLiveImport:
    def test_valid_row_is_inserted(self, tmp_path, tmp_db):
        csv_path = _write_csv(tmp_path / "in.csv", [_base_row(CODIGO="LIVE-001")])
        report = run_import(csv_path, tmp_db, dry_run=False)
        assert report.successful == 1
        assert len(report.errors) == 0
        rows = _fetch_all(tmp_db, fixed_assets)
        assert len(rows) == 1
        asset = dict(rows[0]._mapping)
        assert asset["code"] == "LIVE-001"
        assert asset["status"] == "active"

    def test_ac10_audit_log_per_insert(self, tmp_path, tmp_db):
        # AC10
        csv_path = _write_csv(
            tmp_path / "in.csv",
            [_base_row(CODIGO="AUD-1"), _base_row(CODIGO="AUD-2"), _base_row(CODIGO="AUD-3")],
        )
        report = run_import(csv_path, tmp_db, dry_run=False)
        assert report.successful == 3

        engine = create_engine(f"sqlite:///{tmp_db}")
        with engine.connect() as conn:
            logs = conn.execute(
                select(audit_logs).where(audit_logs.c.entity_type == "asset")
            ).fetchall()
        engine.dispose()
        assert len(logs) == 3
        for log in logs:
            entry = dict(log._mapping)
            assert entry["action"] == "CREATE"
            assert entry["actor"] == "system"
            assert entry["new_value"] is not None

    def test_ac3_duplicate_codigo_skipped(self, tmp_path, tmp_db):
        # AC3 — pre-seed DB and run CSV that duplicates the code
        # Pre-seed via the script itself for simplicity.
        pre_csv = _write_csv(tmp_path / "seed.csv", [_base_row(CODIGO="DUP-001")])
        run_import(pre_csv, tmp_db, dry_run=False)
        assert _row_count(tmp_db, fixed_assets) == 1

        main_csv = _write_csv(
            tmp_path / "main.csv",
            [
                _base_row(CODIGO="DUP-001"),  # duplicate
                _base_row(CODIGO="NEW-001"),  # unique
            ],
        )
        report = run_import(main_csv, tmp_db, dry_run=False)
        assert report.successful == 1
        assert len(report.errors) == 1
        assert "duplicate" in report.errors[0][2]
        assert _row_count(tmp_db, fixed_assets) == 2  # seed + new

    def test_duplicate_within_csv_rejected(self, tmp_path, tmp_db):
        csv_path = _write_csv(
            tmp_path / "in.csv",
            [_base_row(CODIGO="X"), _base_row(CODIGO="X")],
        )
        report = run_import(csv_path, tmp_db, dry_run=False)
        assert report.successful == 1
        assert len(report.errors) == 1
        assert "duplicate" in report.errors[0][2]


class TestAC4Rollback:
    def test_ac4_db_error_rolls_back_whole_batch(self, tmp_path, tmp_db):
        # AC4 — M3 fix: replaced fragile SQLAlchemy-monkeypatch with an
        # injectable AuditLogger subclass that raises on the 3rd audit call.
        # The exception bubbles through run_import's except → trans.rollback(),
        # undoing ALL fixed_assets inserts and prior audit_logs entries.
        csv_path = _write_csv(
            tmp_path / "in.csv",
            [_base_row(CODIGO=f"ROLL-{i}") for i in range(5)],
        )

        class _FailOnThirdAudit(AuditLogger):
            _calls = 0

            def log_change(self, **kwargs):  # type: ignore[override]
                self.__class__._calls += 1
                if self.__class__._calls == 3:
                    raise RuntimeError("simulated audit failure on 3rd call")
                super().log_change(**kwargs)

        _FailOnThirdAudit._calls = 0  # reset between test runs
        report = run_import(csv_path, tmp_db, dry_run=False, audit_logger=_FailOnThirdAudit())
        assert report.successful == 0
        assert _row_count(tmp_db, fixed_assets) == 0
        assert _row_count(tmp_db, audit_logs) == 0
        assert any("rolled back" in e[2] for e in report.errors)


class TestReport:
    def test_ac5_report_contains_all_sections(self, tmp_path, tmp_db):
        # AC5
        csv_path = _write_csv(
            tmp_path / "in.csv",
            [_base_row(CODIGO="R-1"), _base_row(CODIGO="R-2", TIPO="UNKNOWN_TYPE")],
        )
        report = run_import(csv_path, tmp_db, dry_run=True)
        text_out = report.format()
        assert "Total rows read" in text_out
        assert "Successful imports" in text_out
        assert "Warnings" in text_out
        assert "Errors" in text_out
        assert "--- WARNINGS ---" in text_out
        assert "--- ERRORS ---" in text_out
        assert "DRY RUN" in text_out

    def test_live_report_committed_footer(self, tmp_path, tmp_db):
        csv_path = _write_csv(tmp_path / "in.csv", [_base_row(CODIGO="RPT-1")])
        report = run_import(csv_path, tmp_db, dry_run=False)
        assert "COMMITTED — 1 rows inserted" in report.format()


class TestAC6Terrenos:
    def test_ac6_terrenos_defaults_applied(self, tmp_path, tmp_db):
        # AC6
        csv_path = _write_csv(
            tmp_path / "in.csv",
            [
                _base_row(
                    CODIGO="LOT-001",
                    TIPO="TERRENOS",
                    DESCRIPCION="Lote principal",
                    VALOR="500000000",
                )
            ],
        )
        report = run_import(csv_path, tmp_db, dry_run=False)
        assert report.successful == 1
        rows = _fetch_all(tmp_db, fixed_assets)
        asset = dict(rows[0]._mapping)
        assert asset["useful_life_months"] == 0
        assert asset["depreciation_method"] == "none"
        assert asset["salvage_value"] == "0.0000"


class TestAC7DateEdgeCases:
    def test_year_only_rejected(self, tmp_path, tmp_db):
        csv_path = _write_csv(
            tmp_path / "in.csv",
            [_base_row(CODIGO="DT-1", **{"F.ADQ": "2015"})],
        )
        report = run_import(csv_path, tmp_db, dry_run=True)
        assert len(report.errors) == 1
        assert "Invalid date" in report.errors[0][2]

    def test_empty_date_rejected(self, tmp_path, tmp_db):
        csv_path = _write_csv(
            tmp_path / "in.csv",
            [_base_row(CODIGO="DT-2", **{"F.ADQ": ""})],
        )
        report = run_import(csv_path, tmp_db, dry_run=True)
        assert len(report.errors) == 1


class TestAC8UnknownTipo:
    def test_unknown_tipo_reported_and_skipped(self, tmp_path, tmp_db):
        # AC8
        csv_path = _write_csv(
            tmp_path / "in.csv",
            [
                _base_row(CODIGO="OK-1"),
                _base_row(CODIGO="BAD-1", TIPO="MOBILIARIO XYZ"),
            ],
        )
        report = run_import(csv_path, tmp_db, dry_run=False)
        assert report.successful == 1
        assert len(report.errors) == 1
        assert "MOBILIARIO XYZ" in report.errors[0][2]


class TestAC9IgnoredColumns:
    def test_aipi_not_in_payload(self):
        # AC9 — build_insert_payload must never include AIPI / AIPI DEP keys.
        defaults = {"MAQUINARIA Y EQUIPOS": {
            "useful_life_months": 120,
            "salvage_value": "0",
            "depreciation_method": "lineal",
            "is_depreciable": True,
        }}
        raw = {
            "CODIGO": "TEST",
            "DESCRIPCION": "desc",
            "TIPO": "MAQUINARIA Y EQUIPOS",
            "VALOR": "1000",
            "F.ADQ": "2020.01.01",
            "CANTIDAD": "1",
            "AIPI": "9999",
            "AIPI DEP": "9999",
        }
        payload = build_insert_payload(raw, defaults, now_iso="2026-04-13T00:00:00Z")
        assert "AIPI" not in payload
        assert "AIPI DEP" not in payload
        assert "aipi" not in payload


class TestAC11ColumnMappingFidelity:
    def test_full_row_mapping(self, tmp_path, tmp_db):
        # AC11 — one fully-populated row; assert every DB column matches expectation.
        csv_path = _write_csv(
            tmp_path / "in.csv",
            [
                _base_row(
                    CODCONTABLE="15165501",
                    CODIGO="MAP-001",
                    DESCRIPCION="APTO 4B",
                    TIPO="EDIFICACIONES",
                    CARACTERISTICAS="3 bedrooms",
                    **{
                        "UBICACIÓN": "CARTAGENA",
                        "CENTRO COSTO": "ADM",
                        "VALOR FISCAL": "27482223,47",
                        "F.ADQ": "2005.02.28",
                    },
                    CANTIDAD="2",
                    VALOR="137000000",
                    IVA="0",
                    ADICI_MEJORAS="18739845",
                    DEPRECIACION="11896318,06",
                    REVALORIZACION="331919289,3",
                    PROVEEDOR="LUCAS GONZALEZ",
                    FACTURA="ESC. 299",
                )
            ],
        )
        report = run_import(csv_path, tmp_db, dry_run=False)
        assert report.successful == 1
        asset = dict(_fetch_all(tmp_db, fixed_assets)[0]._mapping)

        assert asset["accounting_code"] == "15165501"
        assert asset["code"] == "MAP-001"
        assert asset["description"] == "APTO 4B"
        assert asset["category"] == "EDIFICACIONES"
        assert asset["characteristics"] == "3 bedrooms"
        assert asset["location"] == "CARTAGENA"
        assert asset["cost_center"] == "ADM"
        assert asset["quantity"] == 2
        assert asset["historical_cost"] == "137000000.0000"
        assert asset["vat_amount"] == "0.0000"
        assert asset["additions_improvements"] == "18739845.0000"
        assert asset["imported_accumulated_depreciation"] == "11896318.0600"
        assert asset["fiscal_value"] == "27482223.4700"
        assert asset["revaluation"] == "331919289.3000"
        assert asset["acquisition_date"] == "2005-02-28"
        assert asset["supplier"] == "LUCAS GONZALEZ"
        assert asset["invoice_number"] == "ESC. 299"
        # Category defaults (EDIFICACIONES)
        assert asset["salvage_value"] == "0.0000"
        assert asset["useful_life_months"] == 240
        assert asset["depreciation_method"] == "straight_line"
        # Hardcoded
        assert asset["status"] == "active"


class TestOptionalFieldsToNull:
    def test_empty_optional_fields_become_null(self, tmp_path, tmp_db):
        row = _base_row(
            CODIGO="NUL-1",
            CARACTERISTICAS="",
            REVALORIZACION="",
            IVA="",
            ADICI_MEJORAS="",
            DEPRECIACION="",
            PROVEEDOR="",
            FACTURA="",
        )
        csv_path = _write_csv(tmp_path / "in.csv", [row])
        report = run_import(csv_path, tmp_db, dry_run=False)
        assert report.successful == 1
        asset = dict(_fetch_all(tmp_db, fixed_assets)[0]._mapping)
        assert asset["characteristics"] is None
        assert asset["revaluation"] is None
        assert asset["vat_amount"] is None
        assert asset["additions_improvements"] is None
        assert asset["imported_accumulated_depreciation"] is None
        assert asset["supplier"] is None
        assert asset["invoice_number"] is None


class TestGoldenRealWorld:
    def test_real_world_sample_succeeds(self, tmp_path, tmp_db):
        # Sample rows modeled on `datos activos.csv` — decimal commas, negatives,
        # EDIFICACIONES + MAQUINARIA + TERRENOS mix.
        rows = [
            _base_row(
                CODIGO="RW-TERRENO",
                TIPO="TERRENOS",
                DESCRIPCION="Lote oficina",
                VALOR="597140000",
                **{"F.ADQ": "2011.09.08"},
            ),
            _base_row(
                CODIGO="RW-EDIF",
                TIPO="EDIFICACIONES",
                DESCRIPCION="APTO 4B",
                VALOR="137000000",
                ADICI_MEJORAS="18739845",
                DEPRECIACION="11896318,06",
                **{"F.ADQ": "2005.02.28"},
            ),
            _base_row(
                CODIGO="RW-MAQ-NEG",
                TIPO="MAQUINARIA Y EQUIPOS",
                DESCRIPCION="EMPACADORA (negative depr)",
                VALOR="8468580",
                DEPRECIACION="-8398068",
                **{"F.ADQ": "2011.05.26"},
            ),
            _base_row(
                CODIGO="RW-COMP",
                TIPO="Equipos de Cómputo",
                DESCRIPCION="Laptop",
                VALOR="3500000",
                **{"F.ADQ": "2022.06.15"},
            ),
            _base_row(
                CODIGO="RW-VEH",
                TIPO="Vehículos",
                DESCRIPCION="Camioneta",
                VALOR="85000000",
                **{"F.ADQ": "2019.12.01"},
            ),
        ]
        csv_path = _write_csv(tmp_path / "real.csv", rows)
        report = run_import(csv_path, tmp_db, dry_run=False)
        assert report.successful == 5, report.format()
        assert len(report.errors) == 0
        assert _row_count(tmp_db, fixed_assets) == 5


class TestDecimalHelpers:
    def test_decimal_or_none_to_db_round_trip(self):
        assert _decimal_or_none_to_db("") is None
        assert _decimal_or_none_to_db("11896318,06") == "11896318.0600"
        assert _decimal_or_none_to_db("0") == "0.0000"


class TestMainExitCodes:
    """M2 fix: verify Task 1.4 exit codes via the CLI main() entry point."""

    def test_exit_0_on_clean_live_import(self, tmp_path, tmp_db):
        # Exit 0 — no errors, live mode, all rows succeed.
        csv_path = _write_csv(tmp_path / "in.csv", [_base_row(CODIGO="EX0-1")])
        code = main(["--csv", str(csv_path), "--db", str(tmp_db)])
        assert code == 0

    def test_exit_0_on_clean_dry_run(self, tmp_path, tmp_db):
        # Exit 0 — no errors, dry-run mode.
        csv_path = _write_csv(tmp_path / "in.csv", [_base_row(CODIGO="EX0-DR")])
        code = main(["--csv", str(csv_path), "--db", str(tmp_db), "--dry-run"])
        assert code == 0

    def test_exit_1_csv_not_found(self, tmp_path, tmp_db):
        # Exit 1 — CSV file does not exist.
        code = main(["--csv", str(tmp_path / "missing.csv"), "--db", str(tmp_db)])
        assert code == 1

    def test_exit_1_db_not_found(self, tmp_path):
        # Exit 1 — DB file does not exist.
        csv_path = _write_csv(tmp_path / "in.csv", [_base_row()])
        code = main(["--csv", str(csv_path), "--db", str(tmp_path / "missing.db")])
        assert code == 1

    def test_exit_2_on_row_errors(self, tmp_path, tmp_db):
        # Exit 2 — some rows had errors (unknown TIPO), script still finished.
        csv_path = _write_csv(
            tmp_path / "in.csv",
            [
                _base_row(CODIGO="OK-1"),
                _base_row(CODIGO="BAD-1", TIPO="UNKNOWN_TYPE_XYZ"),
            ],
        )
        code = main(["--csv", str(csv_path), "--db", str(tmp_db)])
        assert code == 2


class TestM1AuditTimestampConsistency:
    """M1 fix: audit_logs.timestamp must match fixed_assets.created_at (batch co-timestamping)."""

    def test_audit_timestamp_matches_asset_created_at(self, tmp_path, tmp_db):
        csv_path = _write_csv(
            tmp_path / "in.csv",
            [_base_row(CODIGO="TS-1"), _base_row(CODIGO="TS-2")],
        )
        run_import(csv_path, tmp_db, dry_run=False)

        engine = create_engine(f"sqlite:///{tmp_db}")
        with engine.connect() as conn:
            assets = conn.execute(select(fixed_assets)).fetchall()
            logs = conn.execute(
                select(audit_logs).where(audit_logs.c.entity_type == "asset")
            ).fetchall()
        engine.dispose()

        asset_created_ats = {dict(a._mapping)["created_at"] for a in assets}
        log_timestamps = {dict(log._mapping)["timestamp"] for log in logs}

        # All assets share the same created_at (batch start time).
        assert len(asset_created_ats) == 1
        # All audit entries share the same timestamp.
        assert len(log_timestamps) == 1
        # Both are the same value.
        assert asset_created_ats == log_timestamps


class TestH2NormalizedCodigoInErrors:
    """H2 fix: CODIGO error reporting handles trailing-space headers."""

    def test_error_shows_code_with_trailing_space_header(self, tmp_path, tmp_db):
        # Simulate a CSV where the CODIGO header has a trailing space, as seen
        # in Excel exports like "DESCRIPCION " and "VALOR ".
        # The _write_csv helper uses `row.get(h, "")` so the row dict must also
        # use the spaced key to produce a non-empty cell value.
        headers_with_space = [h if h != "CODIGO" else "CODIGO " for h in CSV_HEADERS]
        row = _base_row(TIPO="UNKNOWN_XYZ")
        row.pop("CODIGO")
        row["CODIGO "] = "SPACE-001"  # matches the spaced header for csv cell value
        csv_path = _write_csv(
            tmp_path / "in.csv",
            [row],
            headers=headers_with_space,
        )
        report = run_import(csv_path, tmp_db, dry_run=True)
        assert len(report.errors) == 1
        # Code must be resolved to "SPACE-001", not "?"
        assert report.errors[0][1] == "SPACE-001"
