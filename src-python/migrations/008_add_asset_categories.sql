-- Migration 008: Add asset_categories to app_config
ALTER TABLE app_config ADD COLUMN asset_categories TEXT NOT NULL DEFAULT '[]';
UPDATE app_config
SET asset_categories = '["Equipos de Cómputo","Muebles y Enseres","Vehículos","Maquinaria y Equipo"]'
WHERE config_id = 1;
