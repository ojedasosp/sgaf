-- Migration 004: Add PDF tracking columns to app_config
-- Tracks the last monthly_summary PDF generation for the Monthly Close Dashboard.
--
-- Note: SQLite ALTER TABLE ADD COLUMN does not support DEFAULT with expressions.
-- These nullable columns default to NULL implicitly (correct behaviour).

ALTER TABLE app_config ADD COLUMN last_monthly_pdf_generated_at TEXT;
ALTER TABLE app_config ADD COLUMN last_monthly_pdf_period_month INTEGER;
ALTER TABLE app_config ADD COLUMN last_monthly_pdf_period_year INTEGER;
