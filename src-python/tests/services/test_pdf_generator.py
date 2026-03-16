"""Unit tests for PDFGenerator service.

Pure unit tests: no database fixtures, no Flask client required.
All monetary inputs are decimal.Decimal — never float.

Covers:
    - All three report types return valid PDF bytes
    - Header fields (company name, NIT) are present in output
    - Monetary values formatted to 4 decimal places
    - Logo path None / missing file does not raise
    - Invalid report_type raises ValueError
    - asset_register sorted by category
    - monthly_summary totals row present
"""

import base64
import re
import zlib
from decimal import Decimal

import pytest

from app.services.pdf_generator import PDFGenerator


# ---------------------------------------------------------------------------
# PDF content extraction helper
# ---------------------------------------------------------------------------


def _decode_pdf_streams(pdf_bytes: bytes) -> bytes:
    """Decode content streams from a ReportLab-generated PDF.

    ReportLab default encoding: stream data = ASCII85(zlib(content)).
    The ASCII85 `~>` end marker may appear on the same line as `endstream`.

    Returns concatenated decoded bytes from all content streams.
    """
    # Note: `~>endstream` may be on the same line — don't require \n before endstream
    pattern = re.compile(rb"stream\r?\n(.*?)endstream", re.DOTALL)
    parts = []
    for raw in pattern.findall(pdf_bytes):
        raw = raw.strip()  # Remove surrounding whitespace
        try:
            a85_decoded = base64.a85decode(raw, adobe=True)
            try:
                parts.append(zlib.decompress(a85_decoded))
            except zlib.error:
                parts.append(a85_decoded)
        except Exception:
            parts.append(raw)
    return b"".join(parts)

# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

COMPANY_NO_LOGO = {
    "company_name": "Aceros del Valle SA",
    "company_nit": "900123456-1",
    "logo_path": None,
}

COMPANY_MISSING_LOGO = {
    "company_name": "Test Corp",
    "company_nit": "800111222-3",
    "logo_path": "/nonexistent/path/logo.png",
}

_MINIMAL_ASSET = {
    "code": "M-001",
    "description": "Maquinaria Industrial",
    "category": "Maquinaria",
    "depreciation_method": "straight_line",
    "historical_cost": Decimal("12000.0000"),
    "salvage_value": Decimal("1200.0000"),
    "useful_life_months": 60,
}

_MINIMAL_SCHEDULE = [
    {
        "period_number": 1,
        "monthly_charge": Decimal("180.0000"),
        "accumulated_depreciation": Decimal("180.0000"),
        "net_book_value": Decimal("11820.0000"),
    },
    {
        "period_number": 2,
        "monthly_charge": Decimal("180.0000"),
        "accumulated_depreciation": Decimal("360.0000"),
        "net_book_value": Decimal("11640.0000"),
    },
]

_MINIMAL_ASSETS_RESULTS = [
    {
        "code": "E-001",
        "description": "Equipo de Cómputo",
        "depreciation_amount": Decimal("250.0000"),
        "calculated_at": "2026-03-05T14:30:00Z",
    },
    {
        "code": "M-001",
        "description": "Maquinaria Industrial",
        "depreciation_amount": Decimal("180.0000"),
        "calculated_at": "2026-03-05T14:30:00Z",
    },
]

_MINIMAL_ASSETS_REGISTER = [
    {
        "code": "V-001",
        "description": "Vehículo Camioneta",
        "category": "Vehículos",
        "historical_cost": Decimal("45000.0000"),
        "accumulated_depreciation": Decimal("9000.0000"),
        "net_book_value": Decimal("36000.0000"),
    },
    {
        "code": "E-001",
        "description": "Laptop Dell",
        "category": "Equipos de Cómputo",
        "historical_cost": Decimal("3000.0000"),
        "accumulated_depreciation": Decimal("600.0000"),
        "net_book_value": Decimal("2400.0000"),
    },
    {
        "code": "M-001",
        "description": "Torno CNC",
        "category": "Maquinaria",
        "historical_cost": Decimal("80000.0000"),
        "accumulated_depreciation": Decimal("0.0000"),
        "net_book_value": Decimal("80000.0000"),
    },
]

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _is_valid_pdf(data: bytes) -> bool:
    """Check that data is a non-empty bytes object starting with %PDF."""
    return isinstance(data, bytes) and len(data) > 0 and data.startswith(b"%PDF")


# ---------------------------------------------------------------------------
# per_asset report
# ---------------------------------------------------------------------------


class TestPerAssetReport:
    def test_returns_pdf_bytes(self):
        result = PDFGenerator().generate_report(
            "per_asset",
            company_config=COMPANY_NO_LOGO,
            asset=_MINIMAL_ASSET,
            schedule=_MINIMAL_SCHEDULE,
            period_month=3,
            period_year=2026,
        )
        assert _is_valid_pdf(result)

    def test_contains_company_name(self):
        result = PDFGenerator().generate_report(
            "per_asset",
            company_config=COMPANY_NO_LOGO,
            asset=_MINIMAL_ASSET,
            schedule=_MINIMAL_SCHEDULE,
            period_month=3,
            period_year=2026,
        )
        content = _decode_pdf_streams(result)
        # ReportLab encodes text as parenthesized strings in PDF content stream
        # e.g., (Aceros del Valle SA) Tj
        assert b"Aceros del Valle SA" in content

    def test_contains_nit(self):
        result = PDFGenerator().generate_report(
            "per_asset",
            company_config=COMPANY_NO_LOGO,
            asset=_MINIMAL_ASSET,
            schedule=_MINIMAL_SCHEDULE,
            period_month=3,
            period_year=2026,
        )
        content = _decode_pdf_streams(result)
        assert b"900123456-1" in content

    def test_monetary_values_4_decimal_places(self):
        result = PDFGenerator().generate_report(
            "per_asset",
            company_config=COMPANY_NO_LOGO,
            asset=_MINIMAL_ASSET,
            schedule=_MINIMAL_SCHEDULE,
            period_month=3,
            period_year=2026,
        )
        content = _decode_pdf_streams(result)
        # Known values from _MINIMAL_SCHEDULE
        assert b"180.0000" in content
        assert b"11820.0000" in content

    def test_logo_none_does_not_raise(self):
        result = PDFGenerator().generate_report(
            "per_asset",
            company_config=COMPANY_NO_LOGO,
            asset=_MINIMAL_ASSET,
            schedule=_MINIMAL_SCHEDULE,
            period_month=3,
            period_year=2026,
        )
        assert _is_valid_pdf(result)

    def test_logo_missing_file_does_not_raise(self):
        result = PDFGenerator().generate_report(
            "per_asset",
            company_config=COMPANY_MISSING_LOGO,
            asset=_MINIMAL_ASSET,
            schedule=_MINIMAL_SCHEDULE,
            period_month=3,
            period_year=2026,
        )
        assert _is_valid_pdf(result)

    def test_empty_schedule_produces_valid_pdf(self):
        """Edge case: asset with 0-period schedule (should not crash)."""
        result = PDFGenerator().generate_report(
            "per_asset",
            company_config=COMPANY_NO_LOGO,
            asset=_MINIMAL_ASSET,
            schedule=[],
            period_month=1,
            period_year=2026,
        )
        assert _is_valid_pdf(result)


# ---------------------------------------------------------------------------
# monthly_summary report
# ---------------------------------------------------------------------------


class TestMonthlySummaryReport:
    def test_returns_pdf_bytes(self):
        result = PDFGenerator().generate_report(
            "monthly_summary",
            company_config=COMPANY_NO_LOGO,
            assets_results=_MINIMAL_ASSETS_RESULTS,
            period_month=3,
            period_year=2026,
        )
        assert _is_valid_pdf(result)

    def test_contains_company_name(self):
        result = PDFGenerator().generate_report(
            "monthly_summary",
            company_config=COMPANY_NO_LOGO,
            assets_results=_MINIMAL_ASSETS_RESULTS,
            period_month=3,
            period_year=2026,
        )
        content = _decode_pdf_streams(result)
        assert b"Aceros del Valle SA" in content

    def test_contains_totals_row(self):
        result = PDFGenerator().generate_report(
            "monthly_summary",
            company_config=COMPANY_NO_LOGO,
            assets_results=_MINIMAL_ASSETS_RESULTS,
            period_month=3,
            period_year=2026,
        )
        content = _decode_pdf_streams(result)
        # Total = 250.0000 + 180.0000 = 430.0000
        assert b"430.0000" in content
        assert b"TOTAL" in content

    def test_empty_results_produces_valid_pdf(self):
        result = PDFGenerator().generate_report(
            "monthly_summary",
            company_config=COMPANY_NO_LOGO,
            assets_results=[],
            period_month=3,
            period_year=2026,
        )
        assert _is_valid_pdf(result)

    def test_logo_missing_file_does_not_raise(self):
        result = PDFGenerator().generate_report(
            "monthly_summary",
            company_config=COMPANY_MISSING_LOGO,
            assets_results=_MINIMAL_ASSETS_RESULTS,
            period_month=3,
            period_year=2026,
        )
        assert _is_valid_pdf(result)


# ---------------------------------------------------------------------------
# asset_register report
# ---------------------------------------------------------------------------


class TestAssetRegisterReport:
    def test_returns_pdf_bytes(self):
        result = PDFGenerator().generate_report(
            "asset_register",
            company_config=COMPANY_NO_LOGO,
            assets=_MINIMAL_ASSETS_REGISTER,
        )
        assert _is_valid_pdf(result)

    def test_contains_company_name(self):
        result = PDFGenerator().generate_report(
            "asset_register",
            company_config=COMPANY_NO_LOGO,
            assets=_MINIMAL_ASSETS_REGISTER,
        )
        content = _decode_pdf_streams(result)
        assert b"Aceros del Valle SA" in content

    def test_sorted_by_category(self):
        """Assets passed in unsorted order; PDF must contain categories alphabetically sorted."""
        # _MINIMAL_ASSETS_REGISTER has: Vehículos, Equipos de Cómputo, Maquinaria
        # Alphabetically sorted: Equipos de Cómputo, Maquinaria, Vehículos
        result = PDFGenerator().generate_report(
            "asset_register",
            company_config=COMPANY_NO_LOGO,
            assets=_MINIMAL_ASSETS_REGISTER,
        )
        content = _decode_pdf_streams(result)
        pos_equipos = content.find(b"Equipos")
        pos_maquinaria = content.find(b"Maquinaria")
        assert pos_equipos != -1, "Expected 'Equipos' text in decoded PDF content"
        assert pos_maquinaria != -1, "Expected 'Maquinaria' text in decoded PDF content"
        assert pos_equipos < pos_maquinaria, (
            "'Equipos de Cómputo' should appear before 'Maquinaria' (alphabetical sort by category)"
        )

    def test_monetary_values_present(self):
        result = PDFGenerator().generate_report(
            "asset_register",
            company_config=COMPANY_NO_LOGO,
            assets=_MINIMAL_ASSETS_REGISTER,
        )
        content = _decode_pdf_streams(result)
        assert b"45000.0000" in content
        assert b"9000.0000" in content
        assert b"36000.0000" in content

    def test_empty_assets_produces_valid_pdf(self):
        result = PDFGenerator().generate_report(
            "asset_register",
            company_config=COMPANY_NO_LOGO,
            assets=[],
        )
        assert _is_valid_pdf(result)

    def test_logo_missing_file_does_not_raise(self):
        result = PDFGenerator().generate_report(
            "asset_register",
            company_config=COMPANY_MISSING_LOGO,
            assets=_MINIMAL_ASSETS_REGISTER,
        )
        assert _is_valid_pdf(result)


# ---------------------------------------------------------------------------
# Invalid report type
# ---------------------------------------------------------------------------


class TestInvalidReportType:
    def test_invalid_report_type_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown report_type"):
            PDFGenerator().generate_report(
                "unknown_type",
                company_config=COMPANY_NO_LOGO,
            )

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError):
            PDFGenerator().generate_report(
                "",
                company_config=COMPANY_NO_LOGO,
            )


# ---------------------------------------------------------------------------
# Edge cases: negative values
# ---------------------------------------------------------------------------


class TestNegativeValues:
    """Negative values should produce valid PDFs (business validation is route's job)."""

    def test_negative_depreciation_amount_monthly_summary(self):
        """Negative depreciation (e.g., due to reversal) produces valid PDF."""
        assets_results = [
            {
                "code": "E-001",
                "description": "Equipo",
                "depreciation_amount": Decimal("-100.0000"),  # Reversal
                "calculated_at": "2026-03-05T14:30:00Z",
            },
        ]
        result = PDFGenerator().generate_report(
            "monthly_summary",
            company_config=COMPANY_NO_LOGO,
            assets_results=assets_results,
            period_month=3,
            period_year=2026,
        )
        assert _is_valid_pdf(result)
        content = _decode_pdf_streams(result)
        assert b"-100.0000" in content

    def test_zero_net_book_value_asset_register(self):
        """Asset fully depreciated (zero net book value) produces valid PDF."""
        assets = [
            {
                "code": "M-001",
                "description": "Maquinaria",
                "category": "Maquinaria",
                "historical_cost": Decimal("10000.0000"),
                "accumulated_depreciation": Decimal("10000.0000"),
                "net_book_value": Decimal("0.0000"),
            },
        ]
        result = PDFGenerator().generate_report(
            "asset_register",
            company_config=COMPANY_NO_LOGO,
            assets=assets,
        )
        assert _is_valid_pdf(result)
        content = _decode_pdf_streams(result)
        assert b"0.0000" in content
