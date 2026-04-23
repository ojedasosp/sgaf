-- Migration 011: Add index on asset_id for asset_photos
-- ON DELETE CASCADE was included in migration 010 (PostgreSQL supports it natively;
-- the SQLite table-recreation workaround is not needed here).
CREATE INDEX IF NOT EXISTS ix_asset_photos_asset_id ON asset_photos(asset_id)
