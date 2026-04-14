-- Migration 009: Add import fields to fixed_assets for CSV legacy import (Epic 8)
ALTER TABLE fixed_assets ADD COLUMN accounting_code TEXT;
ALTER TABLE fixed_assets ADD COLUMN characteristics TEXT;
ALTER TABLE fixed_assets ADD COLUMN location TEXT;
ALTER TABLE fixed_assets ADD COLUMN cost_center TEXT;
ALTER TABLE fixed_assets ADD COLUMN quantity INTEGER NOT NULL DEFAULT 1;
ALTER TABLE fixed_assets ADD COLUMN vat_amount TEXT;
ALTER TABLE fixed_assets ADD COLUMN additions_improvements TEXT;
ALTER TABLE fixed_assets ADD COLUMN fiscal_value TEXT;
ALTER TABLE fixed_assets ADD COLUMN revaluation TEXT;
ALTER TABLE fixed_assets ADD COLUMN supplier TEXT;
ALTER TABLE fixed_assets ADD COLUMN invoice_number TEXT;
ALTER TABLE fixed_assets ADD COLUMN imported_accumulated_depreciation TEXT;
