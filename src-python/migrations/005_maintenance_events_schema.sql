-- Migration 005: Add missing columns to maintenance_events
-- Story 5.1: Registro y Actualización de Eventos de Mantenimiento
--
-- The initial schema (001_initial_schema.sql) defined maintenance_events with a
-- simplified layout. Story 5.1 requires additional columns for FR23/FR24 fields.
--
-- NOTE: SQLite ALTER TABLE ADD COLUMN does not support non-literal DEFAULT values.
-- All new columns are nullable (no DEFAULT clause) — existing rows get NULL.

ALTER TABLE maintenance_events ADD COLUMN event_type TEXT;
ALTER TABLE maintenance_events ADD COLUMN vendor TEXT;
ALTER TABLE maintenance_events ADD COLUMN estimated_delivery_date TEXT;
ALTER TABLE maintenance_events ADD COLUMN estimated_cost TEXT;
ALTER TABLE maintenance_events ADD COLUMN actual_delivery_date TEXT;
ALTER TABLE maintenance_events ADD COLUMN actual_cost TEXT;
