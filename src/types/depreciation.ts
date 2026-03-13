/// Depreciation domain types for SGAF.
/// Monetary values are strings (Decimal TEXT from SQLite — 4 decimal places).

import type { DepreciationMethod } from "./asset";

export interface DepreciationResult {
  result_id: number;
  asset_id: number;
  code: string;
  description: string;
  depreciation_method: DepreciationMethod;
  opening_book_value: string; // Decimal string, 4 decimal places — computed, not stored
  depreciation_amount: string; // Decimal string, 4 decimal places
  accumulated_depreciation: string; // Decimal string, 4 decimal places
  book_value: string; // Decimal string, 4 decimal places
  period_month: number;
  period_year: number;
  calculated_at: string; // ISO 8601 UTC
}

export interface DepreciationResponse {
  data: DepreciationResult[];
  total: number;
  period_month: number;
  period_year: number;
  calculated_at?: string; // present when total > 0
  message?: string; // present when no active assets
}
