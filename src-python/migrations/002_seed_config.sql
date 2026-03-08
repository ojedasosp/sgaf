INSERT OR IGNORE INTO app_config (config_id, company_name, company_nit, password_hash, jwt_secret, export_folder, created_at, updated_at)
VALUES (1, '', '', '', '', '', strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
