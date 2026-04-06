export type MaintenanceStatus = "open" | "completed";

export type MaintenanceEventType = "preventivo" | "correctivo" | "inspeccion";

export interface MaintenanceEvent {
  event_id: number;
  asset_id: number;
  description: string;
  /** ISO 8601 date — maps to "entry_date" concept in the UI */
  start_date: string;
  event_type: MaintenanceEventType | null;
  vendor: string | null;
  estimated_delivery_date: string | null;
  actual_delivery_date: string | null;
  /** Decimal string with 4 decimal places */
  actual_cost: string | null;
  received_by: string | null;
  closing_observation: string | null;
  status: MaintenanceStatus;
  created_at: string; // ISO 8601 UTC
  updated_at: string; // ISO 8601 UTC
}

export interface CreateMaintenancePayload {
  asset_id: number;
  entry_date: string; // ISO date YYYY-MM-DD
  event_type?: MaintenanceEventType;
  description?: string;
  vendor?: string;
  estimated_delivery_date?: string;
  actual_delivery_date?: string;
  actual_cost?: string;
  received_by?: string;
  closing_observation?: string;
}

export interface CompleteMaintenancePayload {
  status: "completed";
  actual_delivery_date?: string;
  actual_cost?: string;
  received_by?: string;
  closing_observation?: string;
}
