/**
 * Shared helpers for maintenance feature components (Story 5.2).
 *
 * Extracted from MaintenancePage and MaintenanceHistory to avoid duplication.
 */

/** Format ISO date string (YYYY-MM-DD) to DD/MM/YYYY for display. */
export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const parts = iso.split("-");
  if (parts.length !== 3) return iso;
  return `${parts[2]}/${parts[1]}/${parts[0]}`;
}

/** Format decimal string to Colombian currency display (2 decimals, rounded). */
export function formatCurrency(value: string | null): string {
  if (!value) return "—";
  const num = parseFloat(value);
  if (isNaN(num)) return value;
  // Round to 2 decimals, then format with Colombian convention (. thousands, , decimals)
  const rounded = Math.round(num * 100) / 100;
  const [intPart, decPart] = rounded.toFixed(2).split(".");
  const formattedInt = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `$${formattedInt},${decPart}`;
}

export const EVENT_TYPE_LABELS: Record<string, string> = {
  preventivo: "Preventivo",
  correctivo: "Correctivo",
  inspeccion: "Inspección",
};
