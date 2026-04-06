-- Migration 006: Add closure fields to maintenance_events
-- Sprint Change 2026-03-20: received_by + closing_observation for completion tracking

ALTER TABLE maintenance_events ADD COLUMN received_by TEXT NULL;
ALTER TABLE maintenance_events ADD COLUMN closing_observation TEXT NULL;
