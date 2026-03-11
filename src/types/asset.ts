/// Asset domain types for SGAF.
/// Monetary values are strings (Decimal TEXT from SQLite — 4 decimal places).
/// Dates are ISO 8601 strings: "YYYY-MM-DD" for dates, "YYYY-MM-DDTHH:mm:ssZ" for timestamps.

export type AssetStatus = "active" | "in_maintenance" | "retired";

export type DepreciationMethod =
  | "straight_line"
  | "sum_of_digits"
  | "declining_balance";

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
