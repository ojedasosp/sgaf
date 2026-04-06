-- Migration 007: Remove estimated_cost from maintenance_events
-- Sprint Change 2026-03-20: field removed per client request
-- REQUIRES: SQLite 3.35.0+ (DROP COLUMN support added in 3.35)
-- Verify: SELECT sqlite_version();

ALTER TABLE maintenance_events DROP COLUMN estimated_cost;
