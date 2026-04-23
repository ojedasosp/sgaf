"""PDF generation service for SGAF — NIIF-compliant audit reports.

Pure generation service: zero Flask imports, zero database calls.
All monetary values must be decimal.Decimal — never float.

Three report types:
    per_asset       — Full depreciation schedule for one asset (FR15)
    monthly_summary — Consolidated depreciation summary for a period (FR16)
    asset_register  — Register of all non-retired assets with book values (FR17)
"""

import os
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

FOUR_PLACES = Decimal("0.0001")

MONTH_NAMES = {
    1: "Enero",
    2: "Febrero",
    3: "Marzo",
    4: "Abril",
    5: "Mayo",
    6: "Junio",
    7: "Julio",
    8: "Agosto",
    9: "Septiembre",
    10: "Octubre",
    11: "Noviembre",
    12: "Diciembre",
}

METHOD_LABELS = {
    "straight_line": "Línea Recta (Lineal)",
    "sum_of_digits": "Suma de Dígitos",
    "declining_balance": "Saldo Decreciente",
    "none": "Sin Depreciación (Terrenos)",
}

# Gruvbox Light palette for PDF styling
_GRUVBOX_BG1 = colors.HexColor("#ebdbb2")   # Table header background
_GRUVBOX_FG1 = colors.HexColor("#3c3836")   # Primary text
_GRUVBOX_BG2 = colors.HexColor("#d5c4a1")   # Alternating row background
_GRUVBOX_BLUE = colors.HexColor("#458588")  # Accent / section headers

# Base table style commands — extend per report type
_BASE_TABLE_CMDS = [
    ("BACKGROUND", (0, 0), (-1, 0), _GRUVBOX_BG1),
    ("TEXTCOLOR", (0, 0), (-1, 0), _GRUVBOX_FG1),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, 0), 9),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _GRUVBOX_BG2]),
    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
    ("FONTSIZE", (0, 1), (-1, -1), 8),
    ("GRID", (0, 0), (-1, -1), 0.5, _GRUVBOX_BG2),
    ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ("TOPPADDING", (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
]


def _fmt(value: Decimal) -> str:
    """Format a Decimal monetary value to a 4-decimal-place string.

    Raises TypeError if value is not a Decimal (float guard).
    """
    if not isinstance(value, Decimal):
        raise TypeError(
            f"Expected decimal.Decimal, got {type(value).__name__}. "
            "Never pass float to financial formatting."
        )
    return str(value.quantize(FOUR_PLACES, rounding=ROUND_HALF_UP))


class PDFGenerator:
    """Generates NIIF-compliant PDF reports for SGAF.

    Pure generation service — zero Flask imports, zero database calls.
    All monetary values use decimal.Decimal; never float.

    Performance: ReportLab local generation (no network calls) guarantees
    completion in <2 minutes for up to 50 assets on Intel Core i5 with 8GB RAM.
    This is due to purely local processing with no external dependencies.
    """

    def generate_report(
        self,
        report_type: str,
        company_config: dict,
        _compress: bool = True,
        **kwargs,
    ) -> bytes:
        """Dispatch to the correct generator and return PDF bytes.

        Args:
            report_type: "per_asset" | "monthly_summary" | "asset_register"
            company_config: {
                "company_name": str,
                "company_nit": str,
                "logo_path": str | None
            }
            _compress: Internal test hook. Set to False to disable PDF stream compression,
                       enabling byte-level content assertions. Always True in production.
            **kwargs: report-type-specific data (see _generate_* methods)

        Returns:
            PDF content as bytes (starts with b"%PDF").

        Raises:
            ValueError: if report_type is not one of the three supported values.
        """
        if report_type == "per_asset":
            return self._generate_per_asset(
                company_config=company_config, _compress=_compress, **kwargs
            )
        elif report_type == "monthly_summary":
            return self._generate_monthly_summary(
                company_config=company_config, _compress=_compress, **kwargs
            )
        elif report_type == "asset_register":
            return self._generate_asset_register(
                company_config=company_config, _compress=_compress, **kwargs
            )
        elif report_type == "asset_life_sheet":
            return self._generate_asset_life_sheet(
                company_config=company_config, _compress=_compress, **kwargs
            )
        else:
            raise ValueError(
                f"Unknown report_type: {report_type!r}. "
                "Must be 'per_asset', 'monthly_summary', 'asset_register', or 'asset_life_sheet'."
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_styles(self) -> dict:
        """Return a dict of named ParagraphStyles for consistent formatting."""
        base = getSampleStyleSheet()
        return {
            "header_title": ParagraphStyle(
                "header_title",
                parent=base["Normal"],
                fontSize=14,
                fontName="Helvetica-Bold",
                textColor=_GRUVBOX_FG1,
                spaceAfter=2,
            ),
            "header_sub": ParagraphStyle(
                "header_sub",
                parent=base["Normal"],
                fontSize=10,
                fontName="Helvetica",
                textColor=_GRUVBOX_FG1,
                spaceAfter=2,
            ),
            "report_title": ParagraphStyle(
                "report_title",
                parent=base["Normal"],
                fontSize=12,
                fontName="Helvetica-Bold",
                textColor=_GRUVBOX_BLUE,
                spaceBefore=6,
                spaceAfter=4,
            ),
            "section_label": ParagraphStyle(
                "section_label",
                parent=base["Normal"],
                fontSize=9,
                fontName="Helvetica",
                textColor=_GRUVBOX_FG1,
                spaceAfter=2,
            ),
        }

    def _make_doc(self, buffer: BytesIO, compress: bool = True) -> SimpleDocTemplate:
        """Create a standard A4 SimpleDocTemplate with consistent margins.

        Args:
            compress: Set to False in tests to produce uncompressed PDF streams,
                      enabling byte-level content assertions. Production always uses True.
        """
        return SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
            compress=int(compress),
        )

    def _build_header_elements(self, company_config: dict, styles: dict) -> list:
        """Return a list of ReportLab flowables for the company header.

        Logo is optional — silently skipped if logo_path is None or file missing.
        """
        elements = []

        logo_path = company_config.get("logo_path")
        company_name = company_config.get("company_name", "")
        company_nit = company_config.get("company_nit", "")

        if logo_path and os.path.exists(logo_path):
            try:
                elements.append(Image(logo_path, width=60, height=60))
                elements.append(Spacer(1, 0.2 * cm))
            except Exception:
                # Silently skip unloadable images — header degrades gracefully
                pass

        if company_name:
            elements.append(Paragraph(company_name, styles["header_title"]))
        if company_nit:
            elements.append(Paragraph(f"NIT: {company_nit}", styles["header_sub"]))

        elements.append(Spacer(1, 0.3 * cm))
        return elements

    # ------------------------------------------------------------------
    # Report generators
    # ------------------------------------------------------------------

    def _generate_per_asset(
        self,
        company_config: dict,
        asset: dict,
        schedule: list,
        period_month: int,
        period_year: int,
        _compress: bool = True,
    ) -> bytes:
        """Generate per-asset depreciation schedule PDF (FR15).

        Args:
            asset: dict with keys: code, description, category, depreciation_method,
                   historical_cost (Decimal), salvage_value (Decimal),
                   useful_life_months (int).
            schedule: list of dicts with keys: period_number (int),
                      monthly_charge (Decimal), accumulated_depreciation (Decimal),
                      net_book_value (Decimal).
            period_month: 1–12 (used in report title).
            period_year: e.g. 2026 (used in report title).
        """
        buffer = BytesIO()
        doc = self._make_doc(buffer, compress=_compress)
        styles = self._make_styles()

        story = self._build_header_elements(company_config, styles)

        # Report title
        month_name = MONTH_NAMES.get(period_month, str(period_month))
        story.append(
            Paragraph(
                f"Calendario de Depreciación — {month_name} {period_year}",
                styles["report_title"],
            )
        )

        # Asset metadata lines
        method_label = METHOD_LABELS.get(
            asset.get("depreciation_method", ""),
            asset.get("depreciation_method", ""),
        )
        story.append(
            Paragraph(
                f"Activo: {asset.get('code', '')} — {asset.get('description', '')}",
                styles["section_label"],
            )
        )
        story.append(
            Paragraph(
                f"Categoría: {asset.get('category', '')} | "
                f"Método: {method_label} | "
                f"Vida Útil: {asset.get('useful_life_months', '')} meses",
                styles["section_label"],
            )
        )
        story.append(
            Paragraph(
                f"Costo Histórico: {_fmt(asset['historical_cost'])} | "
                f"Valor Salvamento: {_fmt(asset['salvage_value'])}",
                styles["section_label"],
            )
        )
        story.append(Spacer(1, 0.3 * cm))

        # Schedule table
        headers = ["Período", "Cargo Mensual", "Dep. Acumulada", "Valor Libro"]
        table_data = [headers]
        for row in schedule:
            table_data.append(
                [
                    str(row["period_number"]),
                    _fmt(row["monthly_charge"]),
                    _fmt(row["accumulated_depreciation"]),
                    _fmt(row["net_book_value"]),
                ]
            )

        col_widths = [2.5 * cm, 4.5 * cm, 4.5 * cm, 4.5 * cm]
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(
            TableStyle(
                _BASE_TABLE_CMDS
                + [
                    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ]
            )
        )
        story.append(table)

        doc.build(story)
        return buffer.getvalue()

    def _generate_monthly_summary(
        self,
        company_config: dict,
        assets_results: list,
        period_month: int,
        period_year: int,
        _compress: bool = True,
    ) -> bytes:
        """Generate monthly consolidated depreciation summary PDF (FR16).

        Args:
            assets_results: list of dicts with keys: code, description,
                            depreciation_amount (Decimal), calculated_at (str).
            period_month: 1–12.
            period_year: e.g. 2026.
        """
        buffer = BytesIO()
        doc = self._make_doc(buffer, compress=_compress)
        styles = self._make_styles()

        story = self._build_header_elements(company_config, styles)

        month_name = MONTH_NAMES.get(period_month, str(period_month))
        story.append(
            Paragraph(
                f"Resumen Mensual de Depreciación — {month_name} {period_year}",
                styles["report_title"],
            )
        )

        # Calculation date from first result if available
        if assets_results:
            calc_date = assets_results[0].get("calculated_at", "")
            if calc_date:
                story.append(
                    Paragraph(
                        f"Fecha de cálculo: {calc_date}",
                        styles["section_label"],
                    )
                )
        story.append(Spacer(1, 0.3 * cm))

        headers = ["Código", "Descripción", "Cargo Mensual"]
        table_data = [headers]
        total = Decimal("0")
        for row in assets_results:
            monthly_charge = row["depreciation_amount"]  # Must be Decimal from route
            total += monthly_charge
            table_data.append(
                [
                    row.get("code", ""),
                    row.get("description", ""),
                    _fmt(monthly_charge),
                ]
            )

        # Totals row
        table_data.append(["", "TOTAL", _fmt(total)])

        col_widths = [3.5 * cm, 8.5 * cm, 4.5 * cm]
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(
            TableStyle(
                _BASE_TABLE_CMDS
                + [
                    ("ALIGN", (2, 0), (2, -1), "RIGHT"),
                    ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                    ("BACKGROUND", (0, -1), (-1, -1), _GRUVBOX_BG1),
                ]
            )
        )
        story.append(table)

        doc.build(story)
        return buffer.getvalue()

    def _generate_asset_life_sheet(
        self,
        company_config: dict,
        asset: dict,
        maintenance_events: list,
        filter_label: str,
        _compress: bool = True,
    ) -> bytes:
        """Generate asset life sheet PDF.

        Args:
            asset: dict with keys: code, description, category, status,
                   acquisition_date (str), historical_cost (Decimal),
                   supplier, invoice_number, location, characteristics,
                   photo_path (str | None).
            maintenance_events: list of dicts with keys: start_date, event_type,
                                description, vendor, actual_cost (str | None), status.
            filter_label: section title indicating the applied filter.
        """
        buffer = BytesIO()
        doc = self._make_doc(buffer, compress=_compress)
        styles = self._make_styles()

        story = self._build_header_elements(company_config, styles)

        story.append(Paragraph("Hoja de Vida del Activo", styles["report_title"]))
        story.append(Spacer(1, 0.2 * cm))

        # Asset data table (2-column: label | value)
        asset_fields = [
            ("Código", asset.get("code", "") or "—"),
            ("Descripción", asset.get("description", "") or "—"),
            ("Categoría", asset.get("category", "") or "—"),
            ("Estado", asset.get("status", "") or "—"),
            ("Fecha de Adquisición", asset.get("acquisition_date", "") or "—"),
            ("Costo Histórico", _fmt(asset["historical_cost"]) if asset.get("historical_cost") else "—"),
            ("Proveedor", asset.get("supplier") or "—"),
            ("Factura", asset.get("invoice_number") or "—"),
            ("Ubicación", asset.get("location") or "—"),
            ("Características", asset.get("characteristics") or "—"),
        ]
        asset_table_data = [[Paragraph(f"<b>{label}</b>", styles["section_label"]), Paragraph(str(value), styles["section_label"])] for label, value in asset_fields]
        asset_table = Table(asset_table_data, colWidths=[4.5 * cm, 12 * cm])
        asset_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), _GRUVBOX_BG2),
                    ("ROWBACKGROUNDS", (1, 0), (1, -1), [colors.white, _GRUVBOX_BG2]),
                    ("GRID", (0, 0), (-1, -1), 0.5, _GRUVBOX_BG2),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(asset_table)
        story.append(Spacer(1, 0.4 * cm))

        # Primary photo — silently skip if path missing or file not on disk
        photo_path = asset.get("photo_path")
        if photo_path and os.path.isfile(photo_path):
            try:
                img = Image(photo_path, width=8 * cm, height=8 * cm, kind="proportional")
                story.append(img)
                story.append(Spacer(1, 0.4 * cm))
            except Exception:
                pass

        # Maintenance section title
        story.append(Paragraph(filter_label, styles["report_title"]))
        story.append(Spacer(1, 0.2 * cm))

        if not maintenance_events:
            story.append(Paragraph("No hay eventos de mantenimiento registrados.", styles["section_label"]))
        else:
            cell_style = ParagraphStyle(
                "maint_cell",
                parent=styles["section_label"],
                fontSize=8,
                leading=10,
            )
            header_style = ParagraphStyle(
                "maint_header",
                parent=styles["section_label"],
                fontSize=9,
                fontName="Helvetica-Bold",
                leading=11,
            )
            headers = [
                Paragraph("Fecha", header_style),
                Paragraph("Tipo", header_style),
                Paragraph("Descripción", header_style),
                Paragraph("Proveedor", header_style),
                Paragraph("Costo", header_style),
                Paragraph("Estado", header_style),
            ]
            table_data = [headers]
            for evt in maintenance_events:
                table_data.append([
                    Paragraph(evt.get("start_date", "—") or "—", cell_style),
                    Paragraph(evt.get("event_type", "—") or "—", cell_style),
                    Paragraph(evt.get("description", "—") or "—", cell_style),
                    Paragraph(evt.get("vendor", "—") or "—", cell_style),
                    Paragraph(evt.get("actual_cost", "—") or "—", cell_style),
                    Paragraph(evt.get("status", "—") or "—", cell_style),
                ])
            # Column widths must sum to 17 cm (A4 width 21 cm − 2 cm left − 2 cm right margin)
            col_widths = [2 * cm, 2.5 * cm, 6 * cm, 3 * cm, 1.5 * cm, 2 * cm]
            maint_table = Table(table_data, colWidths=col_widths, repeatRows=1)
            maint_table.setStyle(TableStyle(
                _BASE_TABLE_CMDS + [("VALIGN", (0, 0), (-1, -1), "TOP")]
            ))
            story.append(maint_table)

        doc.build(story)
        return buffer.getvalue()

    def _generate_asset_register(
        self,
        company_config: dict,
        assets: list,
        _compress: bool = True,
    ) -> bytes:
        """Generate asset register PDF (FR17) — sorted by category.

        Args:
            assets: list of dicts with keys: code, description, category,
                    historical_cost (Decimal), accumulated_depreciation (Decimal),
                    net_book_value (Decimal).
        """
        buffer = BytesIO()
        doc = self._make_doc(buffer, compress=_compress)
        styles = self._make_styles()

        story = self._build_header_elements(company_config, styles)

        story.append(
            Paragraph("Registro de Activos Fijos", styles["report_title"])
        )
        story.append(Spacer(1, 0.3 * cm))

        # Sort by category (defensive — route should pre-sort, but ensure correct order)
        sorted_assets = sorted(assets, key=lambda a: a.get("category", ""))

        headers = [
            "Código",
            "Descripción",
            "Categoría",
            "Costo Histórico",
            "Dep. Acumulada",
            "Valor Neto",
        ]
        table_data = [headers]
        for asset in sorted_assets:
            hist_cost = asset.get("historical_cost", Decimal("0"))  # Must be Decimal from route
            accum_dep = asset.get("accumulated_depreciation", Decimal("0"))  # Must be Decimal from route
            net_bv = asset.get("net_book_value", Decimal("0"))  # Must be Decimal from route
            table_data.append(
                [
                    asset.get("code", ""),
                    asset.get("description", ""),
                    asset.get("category", ""),
                    _fmt(hist_cost),
                    _fmt(accum_dep),
                    _fmt(net_bv),
                ]
            )

        col_widths = [2.5 * cm, 5 * cm, 3 * cm, 3.5 * cm, 3.5 * cm, 3 * cm]
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(
            TableStyle(
                _BASE_TABLE_CMDS
                + [
                    ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
                ]
            )
        )
        story.append(table)

        doc.build(story)
        return buffer.getvalue()
