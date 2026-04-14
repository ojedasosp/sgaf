"""CLI importer for legacy fixed-asset CSVs (Epic 8, Story 8.3).

Reads a semicolon-delimited Windows-1252 CSV exported from the client's legacy
Excel workbook and loads each row into ``fixed_assets``. Category defaults come
from ``scripts/category_defaults.json`` (Story 8.2). One ``audit_logs`` CREATE
entry is written per inserted asset — via :class:`AuditLogger` on the same
connection, so the batch is atomic.

Usage::

    python -m scripts.import_assets_csv --csv "datos activos.csv" --db sgaf.db --dry-run
    python scripts/import_assets_csv.py --csv "datos activos.csv" --db sgaf.db

Run ``--dry-run`` first. No rows are written when that flag is set.

This is an ops tool, not an HTTP endpoint. It talks to SQLite directly and
bypasses the Flask validator — ``useful_life_months = 0`` is legal here (needed
for TERRENOS) even though the HTTP ``POST /api/v1/assets/`` validator rejects
it.

D3 compliance: every monetary value routed through ``to_db_string`` so the
stored TEXT always has 4+ decimal places.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

# When invoked as ``python scripts/import_assets_csv.py ...`` from src-python/,
# the parent directory is not automatically on sys.path. Add it so ``app.*``
# imports resolve whether run directly or via ``python -m scripts.import_assets_csv``.
_SRC_PYTHON = pathlib.Path(__file__).resolve().parent.parent
if str(_SRC_PYTHON) not in sys.path:
    sys.path.insert(0, str(_SRC_PYTHON))

import csv  # noqa: E402

from sqlalchemy import create_engine, insert, select  # noqa: E402

from app.models.tables import fixed_assets  # noqa: E402
from app.utils.audit_logger import AuditLogger  # noqa: E402
from app.utils.decimal_utils import to_db_string  # noqa: E402

DEFAULTS_FILE = pathlib.Path(__file__).parent / "category_defaults.json"

# CSV header → DB column. Headers are stripped/normalized before lookup.
HEADER_MAP: dict[str, str] = {
    "CODCONTABLE": "accounting_code",
    "CODIGO": "code",
    "DESCRIPCION": "description",
    "TIPO": "category",
    "CARACTERISTICAS": "characteristics",
    "UBICACIÓN": "location",
    "CENTRO COSTO": "cost_center",
    "CANTIDAD": "quantity",
    "VALOR": "historical_cost",
    "IVA": "vat_amount",
    "ADICI_MEJORAS": "additions_improvements",
    "DEPRECIACION": "imported_accumulated_depreciation",
    "VALOR FISCAL": "fiscal_value",
    "REVALORIZACION": "revaluation",
    "F.ADQ": "acquisition_date",
    "PROVEEDOR": "supplier",
    "FACTURA": "invoice_number",
}

# Intentionally ignored per epic 8.3 (legacy COLGAAP — not applicable in NIIF).
IGNORED_CSV_COLUMNS = frozenset({"AIPI", "AIPI DEP"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_category_defaults(tipo: str, defaults: dict) -> dict:
    """Look up category defaults, raising ValueError on unknown TIPO.

    Canonical home for this helper (moved from tests/test_category_defaults.py
    as part of Story 8.3).
    """
    if tipo not in defaults:
        raise ValueError(
            f"Unknown asset type '{tipo}'. Not found in category_defaults.json. "
            "Add it or correct the CSV value."
        )
    return defaults[tipo]


def parse_decimal_or_none(raw: str | None) -> Decimal | None:
    """Parse a decimal string that may use ``,`` as the decimal separator.

    Returns ``None`` when the input is empty or whitespace-only. Handles the
    quirks of Excel-exported Colombian CSVs: plain ``1234,56``, ``1.234,56``
    thousands grouping, and ``1234.56`` ASCII form. Raises ValueError on
    truly malformed input.
    """
    if raw is None:
        return None
    trimmed = raw.strip()
    if trimmed == "":
        return None

    # Normalize: if comma is used as decimal separator, strip dot thousands
    # separators first, then swap comma → dot. If only dot is present, leave
    # as-is (already ASCII decimal form).
    if "," in trimmed:
        cleaned = trimmed.replace(".", "").replace(",", ".")
    else:
        cleaned = trimmed

    try:
        result = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Cannot parse decimal from {raw!r}: {exc}") from exc
    if result.is_nan() or result.is_infinite():
        raise ValueError(f"Cannot parse decimal from {raw!r}: NaN/Inf not allowed")
    return result


def parse_required_decimal(raw: str | None, field_name: str) -> Decimal:
    """Same as parse_decimal_or_none but empty/None raises ValueError."""
    result = parse_decimal_or_none(raw)
    if result is None:
        raise ValueError(f"{field_name} is required but empty")
    return result


def parse_iso_date(raw: str | None) -> str:
    """Convert ``YYYY.MM.DD`` from the legacy CSV into ISO 8601 ``YYYY-MM-DD``.

    Rejects blank, year-only (e.g. ``2015``), and unparseable inputs with a
    clear ValueError — no silent defaults.
    """
    if raw is None or raw.strip() == "":
        raise ValueError("acquisition_date is required but empty")
    trimmed = raw.strip()
    try:
        parsed = datetime.strptime(trimmed, "%Y.%m.%d").date()
    except ValueError as exc:
        raise ValueError(
            f"Invalid date {raw!r}: expected YYYY.MM.DD (got year-only or malformed value)"
        ) from exc
    return parsed.isoformat()


def parse_int_or_default(raw: str | None, default: int) -> int:
    """Parse a non-negative integer; empty/unparseable returns ``default``."""
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


def _map_engine_method(method: str) -> str:
    """Translate category_defaults vocabulary → depreciation_engine vocabulary.

    ``"lineal"`` (Spanish, NIIF-native, stored in category_defaults.json) maps
    to ``"straight_line"`` which is the value the engine and HTTP validator
    already accept. ``"none"`` is passed through (engine support lands in
    Story 8.4). Anything else raises — no silent fallbacks.
    """
    if method == "lineal":
        return "straight_line"
    if method == "none":
        return "none"
    raise ValueError(
        f"Unsupported depreciation_method '{method}' from category_defaults.json"
    )


def _decimal_or_none_to_db(raw: str | None) -> str | None:
    """Full pipeline: raw string → Decimal (or None) → D3-compliant TEXT (or None)."""
    d = parse_decimal_or_none(raw)
    return to_db_string(d) if d is not None else None


# ---------------------------------------------------------------------------
# Row → payload
# ---------------------------------------------------------------------------


def _normalize_row(raw_row: dict) -> dict:
    """Return a dict keyed by DB column names (not CSV headers).

    Strips trailing/leading whitespace from every header key. Keys not in
    HEADER_MAP are dropped (including IGNORED_CSV_COLUMNS — AIPI, AIPI DEP).
    Values remain as-is (the payload builder handles their transformation).
    """
    normalized: dict[str, str] = {}
    for raw_key, value in raw_row.items():
        if raw_key is None:
            continue
        key = raw_key.strip()
        if key in IGNORED_CSV_COLUMNS:
            continue
        db_col = HEADER_MAP.get(key)
        if db_col is None:
            continue
        normalized[db_col] = value if value is not None else ""
    return normalized


def build_insert_payload(
    raw_row: dict,
    defaults_json: dict,
    now_iso: str,
) -> dict[str, Any]:
    """Transform a raw CSV DictReader row into kwargs for ``insert(fixed_assets)``.

    Raises ValueError on any validation failure (unknown TIPO, bad decimal,
    bad date, missing required field). The caller is expected to catch and
    funnel the error into the report.
    """
    row = _normalize_row(raw_row)

    tipo = (row.get("category") or "").strip()
    if not tipo:
        raise ValueError("TIPO (category) is required but empty")
    cat_defaults = get_category_defaults(tipo, defaults_json)

    code = (row.get("code") or "").strip()
    if not code:
        raise ValueError("CODIGO (code) is required but empty")

    description = (row.get("description") or "").strip()
    if not description:
        raise ValueError("DESCRIPCION (description) is required but empty")

    historical_cost = parse_required_decimal(row.get("historical_cost"), "VALOR")
    acquisition_date = parse_iso_date(row.get("acquisition_date"))

    def _opt_text(key: str) -> str | None:
        v = (row.get(key) or "").strip()
        return v if v else None

    payload: dict[str, Any] = {
        "code": code,
        "description": description,
        "category": tipo,
        "historical_cost": to_db_string(historical_cost),
        "acquisition_date": acquisition_date,
        "accounting_code": _opt_text("accounting_code"),
        "characteristics": _opt_text("characteristics"),
        "location": _opt_text("location"),
        "cost_center": _opt_text("cost_center"),
        "quantity": parse_int_or_default(row.get("quantity"), 1),
        "vat_amount": _decimal_or_none_to_db(row.get("vat_amount")),
        "additions_improvements": _decimal_or_none_to_db(row.get("additions_improvements")),
        "imported_accumulated_depreciation": _decimal_or_none_to_db(
            row.get("imported_accumulated_depreciation")
        ),
        "fiscal_value": _decimal_or_none_to_db(row.get("fiscal_value")),
        "revaluation": _decimal_or_none_to_db(row.get("revaluation")),
        "supplier": _opt_text("supplier"),
        "invoice_number": _opt_text("invoice_number"),
        # Category defaults (Story 8.2) — translated / D3-normalized
        "salvage_value": to_db_string(Decimal(cat_defaults["salvage_value"])),
        "useful_life_months": int(cat_defaults["useful_life_months"]),
        "depreciation_method": _map_engine_method(cat_defaults["depreciation_method"]),
        # Hardcoded
        "status": "active",
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    return payload


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


@dataclass
class ImportReport:
    csv_path: str
    db_path: str
    dry_run: bool
    started_at: str
    total_read: int = 0
    successful: int = 0
    warnings: list[tuple[int, str, str]] = field(default_factory=list)
    errors: list[tuple[int, str, str]] = field(default_factory=list)

    def format(self) -> str:
        lines: list[str] = []
        lines.append("==============================")
        lines.append("IMPORT ASSETS CSV — REPORT")
        lines.append("==============================")
        lines.append(f"CSV:           {self.csv_path}")
        lines.append(f"DB:            {self.db_path}")
        lines.append(f"Mode:          {'DRY-RUN' if self.dry_run else 'LIVE'}")
        lines.append(f"Started:       {self.started_at}")
        lines.append("")
        lines.append(f"Total rows read:      {self.total_read}")
        lines.append(f"Successful imports:   {self.successful}")
        lines.append(f"Warnings:             {len(self.warnings)}")
        lines.append(f"Errors (skipped):     {len(self.errors)}")
        lines.append("")
        lines.append("--- WARNINGS ---")
        if self.warnings:
            for row_num, code, reason in self.warnings:
                lines.append(f"Row {row_num}: CODIGO={code} — {reason}")
        else:
            lines.append("(none)")
        lines.append("")
        lines.append("--- ERRORS ---")
        if self.errors:
            for row_num, code, reason in self.errors:
                lines.append(f"Row {row_num}: CODIGO={code} — {reason}")
        else:
            lines.append("(none)")
        lines.append("")
        if self.dry_run:
            lines.append("DRY RUN — no data written")
        else:
            lines.append(f"COMMITTED — {self.successful} rows inserted")
        lines.append("==============================")
        return "\n".join(lines)


def _load_defaults() -> dict:
    with open(DEFAULTS_FILE, encoding="utf-8") as f:
        return json.load(f)


def _read_csv_rows(
    csv_path: pathlib.Path, encoding: str, delimiter: str
) -> list[dict]:
    with open(csv_path, encoding=encoding, newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        return [dict(row) for row in reader]


def run_import(
    csv_path: pathlib.Path,
    db_path: pathlib.Path,
    *,
    dry_run: bool,
    encoding: str = "cp1252",
    delimiter: str = ";",
    audit_logger: AuditLogger | None = None,
) -> ImportReport:
    """Entry point used by both the CLI and by tests.

    Returns the :class:`ImportReport`; does not print (the CLI prints).
    """
    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = ImportReport(
        csv_path=str(csv_path),
        db_path=str(db_path),
        dry_run=dry_run,
        started_at=started_at,
    )

    defaults = _load_defaults()
    raw_rows = _read_csv_rows(csv_path, encoding=encoding, delimiter=delimiter)
    report.total_read = len(raw_rows)

    # Phase 1 — parse each row into a payload or collect an error.
    parsed: list[tuple[int, dict[str, Any]]] = []
    for idx, raw in enumerate(raw_rows, start=1):
        try:
            payload = build_insert_payload(raw, defaults, now_iso=started_at)
        except ValueError as exc:
            code = (raw.get("CODIGO") or "").strip() or "?"
            report.errors.append((idx, code, str(exc)))
            continue
        parsed.append((idx, payload))

    # Phase 2 — duplicate detection (CSV-internal + against DB).
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        existing_codes = {
            row[0]
            for row in conn.execute(select(fixed_assets.c.code)).fetchall()
        }

    seen_in_csv: set[str] = set()
    deduped: list[tuple[int, dict[str, Any]]] = []
    for idx, payload in parsed:
        code = payload["code"]
        if code in existing_codes:
            report.errors.append(
                (idx, code, "duplicate code — already exists in fixed_assets")
            )
            continue
        if code in seen_in_csv:
            report.errors.append(
                (idx, code, "duplicate code within CSV — first occurrence wins")
            )
            continue
        seen_in_csv.add(code)
        deduped.append((idx, payload))

    # Phase 3 — commit (skipped on dry-run).
    if dry_run:
        return report

    logger = audit_logger or AuditLogger()
    current_idx = 0
    current_code = "?"
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            for idx, payload in deduped:
                current_idx = idx
                current_code = payload["code"]
                result = conn.execute(insert(fixed_assets).values(**payload))
                new_id = result.lastrowid
                logger.log_change(
                    entity_type="asset",
                    entity_id=new_id,
                    action="CREATE",
                    actor="system",
                    new_value=json.dumps(
                        {"code": payload["code"], "category": payload["category"]},
                        ensure_ascii=False,
                    ),
                    conn=conn,
                )
                report.successful += 1
            trans.commit()
        except Exception as exc:  # noqa: BLE001 — atomic batch on any failure
            trans.rollback()
            report.errors.append(
                (current_idx, current_code, f"DB error — batch rolled back: {exc}")
            )
            report.successful = 0  # nothing persisted

    return report


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import legacy fixed-asset CSV into SGAF SQLite database.",
    )
    parser.add_argument("--csv", required=True, help="Path to input CSV file")
    parser.add_argument("--db", required=True, help="Path to target SQLite database")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and report but never commit (recommended first pass)",
    )
    parser.add_argument(
        "--encoding",
        default="cp1252",
        help="Source file encoding (default cp1252 — Excel CSV from Colombia)",
    )
    parser.add_argument(
        "--delimiter",
        default=";",
        help="CSV field delimiter (default ;)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    csv_path = pathlib.Path(args.csv)
    db_path = pathlib.Path(args.db)

    if not csv_path.is_file():
        print(f"ERROR: CSV file not found: {csv_path}", file=sys.stderr)
        return 1
    if not db_path.is_file():
        print(f"ERROR: DB file not found: {db_path}", file=sys.stderr)
        return 1

    print(
        f"Import script — CSV: {csv_path}, DB: {db_path}, DRY-RUN: {args.dry_run}"
    )

    try:
        report = run_import(
            csv_path=csv_path,
            db_path=db_path,
            dry_run=args.dry_run,
            encoding=args.encoding,
            delimiter=args.delimiter,
        )
    except Exception:  # noqa: BLE001 — top-level CLI safety net
        traceback.print_exc()
        return 3

    print(report.format())

    if report.errors:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
