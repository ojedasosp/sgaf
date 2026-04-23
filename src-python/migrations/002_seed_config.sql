INSERT INTO app_config (config_id, company_name, company_nit, password_hash, jwt_secret, export_folder, created_at, updated_at)
VALUES (
    1, '', '', '', '', '',
    TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
    TO_CHAR(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
)
ON CONFLICT (config_id) DO NOTHING
