"""SQLAlchemy Core table definitions for SGAF.

All monetary columns are TEXT (never REAL) to prevent IEEE 754 rounding.
All timestamp columns are TEXT in ISO 8601 UTC format.
"""

from sqlalchemy import Column, Integer, MetaData, Table, Text

metadata = MetaData()

schema_version = Table(
    "schema_version",
    metadata,
    Column("version_id", Integer, primary_key=True, autoincrement=True),
    Column("script_name", Text, nullable=False, unique=True),
    Column("applied_at", Text, nullable=False),  # ISO 8601 UTC
)

app_config = Table(
    "app_config",
    metadata,
    Column("config_id", Integer, primary_key=True),
    Column("company_name", Text, nullable=False, server_default=""),
    Column("company_nit", Text, nullable=False, server_default=""),
    Column("password_hash", Text, nullable=False, server_default=""),
    Column("jwt_secret", Text, nullable=False, server_default=""),
    Column("export_folder", Text, nullable=False, server_default=""),
    Column("logo_path", Text),  # nullable — set during first-launch wizard (Story 1.3)
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    Column("last_monthly_pdf_generated_at", Text, nullable=True),
    Column("last_monthly_pdf_period_month", Integer, nullable=True),
    Column("last_monthly_pdf_period_year", Integer, nullable=True),
    Column("asset_categories", Text, nullable=False, server_default="[]"),
)

fixed_assets = Table(
    "fixed_assets",
    metadata,
    Column("asset_id", Integer, primary_key=True, autoincrement=True),
    Column("code", Text, nullable=False, unique=True),
    Column("description", Text, nullable=False),
    Column("historical_cost", Text, nullable=False),  # Decimal string, 4 dec places
    Column("salvage_value", Text, nullable=False),  # Decimal string, 4 dec places
    Column("useful_life_months", Integer, nullable=False),
    Column("acquisition_date", Text, nullable=False),  # ISO 8601 date
    Column("category", Text, nullable=False),
    Column(
        "depreciation_method", Text, nullable=False
    ),  # straight_line | sum_of_digits | declining_balance
    Column(
        "status", Text, nullable=False, server_default="active"
    ),  # active | in_maintenance | retired
    Column("retirement_date", Text),  # nullable
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    # Import fields — added by migration 009 (Epic 8)
    Column("accounting_code", Text),          # nullable — PUC accounting code
    Column("characteristics", Text),           # nullable — technical specs
    Column("location", Text),                  # nullable — physical location
    Column("cost_center", Text),               # nullable — cost center
    Column("quantity", Integer, nullable=False, server_default="1"),
    Column("vat_amount", Text),                # nullable — TEXT per D3 (informational, no depreciation impact)
    Column("additions_improvements", Text),    # nullable — TEXT per D3 (affects depreciable base in Story 8.4)
    Column("fiscal_value", Text),              # nullable — TEXT per D3 (informational)
    Column("revaluation", Text),               # nullable — TEXT per D3 (informational)
    Column("supplier", Text),                  # nullable
    Column("invoice_number", Text),            # nullable
    Column("imported_accumulated_depreciation", Text),  # nullable — TEXT per D3 (editable by accountant, Story 8.4/8.5)
)

depreciation_results = Table(
    "depreciation_results",
    metadata,
    Column("result_id", Integer, primary_key=True, autoincrement=True),
    Column("asset_id", Integer, nullable=False),  # FK to fixed_assets
    Column("period_month", Integer, nullable=False),  # 1-12
    Column("period_year", Integer, nullable=False),
    Column("depreciation_amount", Text, nullable=False),  # Decimal string
    Column("accumulated_depreciation", Text, nullable=False),  # Decimal string
    Column("book_value", Text, nullable=False),  # Decimal string
    Column("calculated_at", Text, nullable=False),  # ISO 8601 UTC
)

maintenance_events = Table(
    "maintenance_events",
    metadata,
    Column("event_id", Integer, primary_key=True, autoincrement=True),
    Column("asset_id", Integer, nullable=False),  # FK to fixed_assets
    Column("description", Text, nullable=False),
    Column("start_date", Text, nullable=False),  # ISO 8601 date — entry date
    Column("end_date", Text),  # nullable — kept for legacy compatibility
    Column("status", Text, nullable=False, server_default="open"),  # open | completed
    Column("cost", Text),  # nullable — kept for legacy compatibility
    Column("event_type", Text),  # preventive | corrective | inspection
    Column("vendor", Text),  # vendor / responsible party
    Column("estimated_delivery_date", Text),  # ISO 8601 date, nullable
    Column("actual_delivery_date", Text),  # ISO 8601 date, nullable
    Column("actual_cost", Text),  # Decimal string, nullable
    Column("received_by", Text),  # free text, nullable
    Column("closing_observation", Text),  # free text, nullable
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
)

audit_logs = Table(
    "audit_logs",
    metadata,
    Column("log_id", Integer, primary_key=True, autoincrement=True),
    Column("timestamp", Text, nullable=False),  # ISO 8601 UTC
    Column("actor", Text, nullable=False),  # "system" in MVP
    Column("entity_type", Text, nullable=False),  # asset | maintenance_event | config
    Column("entity_id", Integer, nullable=False),
    Column("action", Text, nullable=False),  # CREATE | UPDATE | RETIRE | DELETE
    Column("field", Text),  # nullable for CREATE/RETIRE/DELETE
    Column("old_value", Text),  # nullable for CREATE
    Column("new_value", Text),  # nullable for DELETE
)
