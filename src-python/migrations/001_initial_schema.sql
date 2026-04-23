CREATE TABLE IF NOT EXISTS app_config (
    config_id INTEGER PRIMARY KEY,
    company_name TEXT NOT NULL DEFAULT '',
    company_nit TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL DEFAULT '',
    jwt_secret TEXT NOT NULL DEFAULT '',
    export_folder TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fixed_assets (
    asset_id SERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    historical_cost TEXT NOT NULL,
    salvage_value TEXT NOT NULL,
    useful_life_months INTEGER NOT NULL,
    acquisition_date TEXT NOT NULL,
    category TEXT NOT NULL,
    depreciation_method TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    retirement_date TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS depreciation_results (
    result_id SERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL REFERENCES fixed_assets(asset_id),
    period_month INTEGER NOT NULL,
    period_year INTEGER NOT NULL,
    depreciation_amount TEXT NOT NULL,
    accumulated_depreciation TEXT NOT NULL,
    book_value TEXT NOT NULL,
    calculated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS maintenance_events (
    event_id SERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL REFERENCES fixed_assets(asset_id),
    description TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    cost TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_logs (
    log_id SERIAL PRIMARY KEY,
    timestamp TEXT NOT NULL,
    actor TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    field TEXT,
    old_value TEXT,
    new_value TEXT
);

CREATE INDEX IF NOT EXISTS idx_fixed_assets_status ON fixed_assets(status);
CREATE INDEX IF NOT EXISTS idx_fixed_assets_category ON fixed_assets(category);
CREATE INDEX IF NOT EXISTS idx_maintenance_events_asset_id ON maintenance_events(asset_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_entity ON audit_logs(entity_type, entity_id)
