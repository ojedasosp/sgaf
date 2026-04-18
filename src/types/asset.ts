/// Asset domain types for SGAF.
/// Monetary values are strings (Decimal TEXT from SQLite — 4 decimal places).
/// Dates are ISO 8601 strings: "YYYY-MM-DD" for dates, "YYYY-MM-DDTHH:mm:ssZ" for timestamps.

export type AssetStatus = "active" | "in_maintenance" | "retired";

export type DepreciationMethod =
  | "straight_line"
  | "sum_of_digits"
  | "declining_balance"
  | "none"; // TERRENOS — no depreciation (Story 8.5)

export interface Asset {
  asset_id: number;
  code: string;
  description: string;
  historical_cost: string; // Decimal string, 4 decimal places
  salvage_value: string; // Decimal string, 4 decimal places
  useful_life_months: number;
  acquisition_date: string; // ISO 8601 date: "YYYY-MM-DD"
  category: string;
  depreciation_method: DepreciationMethod;
  status: AssetStatus;
  retirement_date: string | null;
  created_at: string; // ISO 8601 UTC
  updated_at: string; // ISO 8601 UTC
  // Import fields — added by migration 009 (Story 8.1), editable per Story 8.5
  imported_accumulated_depreciation: string | null; // Decimal string or null
  additions_improvements: string | null; // Decimal string or null
  accounting_code: string | null;
  cost_center: string | null;
  supplier: string | null;
  invoice_number: string | null;
  location: string | null;
  characteristics: string | null;
}

export interface CreateAssetPayload {
  code: string;
  description: string;
  historical_cost: string;
  salvage_value: string;
  useful_life_months: number;
  acquisition_date: string;
  category: string;
  depreciation_method: DepreciationMethod;
}

export interface UpdateAssetPayload {
  // Original editable fields (all optional for PATCH)
  code?: string;
  description?: string;
  historical_cost?: string;
  salvage_value?: string;
  useful_life_months?: number;
  acquisition_date?: string;
  category?: string;
  depreciation_method?: DepreciationMethod;
  // Import fields (Story 8.5)
  imported_accumulated_depreciation?: string | null;
  additions_improvements?: string | null;
  accounting_code?: string | null;
  cost_center?: string | null;
  supplier?: string | null;
  invoice_number?: string | null;
  location?: string | null;
  characteristics?: string | null;
}

export interface RetireAssetPayload {
  retirement_date: string; // ISO 8601 date "YYYY-MM-DD"
}

export interface AuditLogEntry {
  log_id: number;
  timestamp: string; // ISO 8601 UTC
  actor: string;
  entity_type: string;
  entity_id: number;
  action: string; // CREATE | UPDATE | RETIRE
  field: string | null;
  old_value: string | null;
  new_value: string | null;
}
