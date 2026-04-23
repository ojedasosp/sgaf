-- Migration 010: Add asset_photos table for multi-photo support per asset
CREATE TABLE IF NOT EXISTS asset_photos (
    photo_id SERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    is_primary INTEGER NOT NULL DEFAULT 0,
    uploaded_at TEXT NOT NULL,
    CONSTRAINT asset_photos_asset_id_fkey
        FOREIGN KEY (asset_id) REFERENCES fixed_assets(asset_id) ON DELETE CASCADE
);
