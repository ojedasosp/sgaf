/**
 * MaintenanceHistory — Per-asset maintenance event history (Story 5.2).
 *
 * Displays all maintenance events for a single asset in reverse-chronological
 * order (data already ordered DESC by backend). Open events are visually
 * distinguished from completed events via status badge color.
 */

import type { MaintenanceEvent } from "../../types/maintenance";
import { EVENT_TYPE_LABELS, formatCurrency, formatDate } from "./helpers";

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface Props {
  events: MaintenanceEvent[];
}

export default function MaintenanceHistory({ events }: Props) {
  if (events.length === 0) {
    return (
      <p className="text-[#928374] text-sm">
        Sin eventos de mantenimiento registrados.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm text-[#3c3836]">
        <thead>
          <tr className="border-b border-[#d5c4a1]">
            <th className="text-left text-xs text-[#7c6f64] uppercase tracking-wide pb-2 pr-4 font-medium">
              Fecha Ingreso
            </th>
            <th className="text-left text-xs text-[#7c6f64] uppercase tracking-wide pb-2 pr-4 font-medium">
              Tipo
            </th>
            <th className="text-left text-xs text-[#7c6f64] uppercase tracking-wide pb-2 pr-4 font-medium">
              Descripción
            </th>
            <th className="text-left text-xs text-[#7c6f64] uppercase tracking-wide pb-2 pr-4 font-medium">
              Proveedor
            </th>
            <th className="text-left text-xs text-[#7c6f64] uppercase tracking-wide pb-2 pr-4 font-medium">
              F. Est. Entrega
            </th>
            <th className="text-left text-xs text-[#7c6f64] uppercase tracking-wide pb-2 pr-4 font-medium">
              F. Entrega Real
            </th>
            <th className="text-left text-xs text-[#7c6f64] uppercase tracking-wide pb-2 pr-4 font-medium">
              Costo Real
            </th>
            <th className="text-left text-xs text-[#7c6f64] uppercase tracking-wide pb-2 pr-4 font-medium">
              Estado
            </th>
            <th className="text-left text-xs text-[#7c6f64] uppercase tracking-wide pb-2 font-medium">
              Notas de Cierre
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[#ebdbb2]">
          {events.map((event) => (
            <tr key={event.event_id} className="py-2">
              <td className="py-2 pr-4">{formatDate(event.start_date)}</td>
              <td className="py-2 pr-4">
                {event.event_type
                  ? (EVENT_TYPE_LABELS[event.event_type] ?? event.event_type)
                  : "—"}
              </td>
              <td className="py-2 pr-4">{event.description || "—"}</td>
              <td className="py-2 pr-4">{event.vendor ?? "—"}</td>
              <td className="py-2 pr-4">
                {formatDate(event.estimated_delivery_date)}
              </td>
              <td className="py-2 pr-4">
                {formatDate(event.actual_delivery_date)}
              </td>
              <td className="py-2 pr-4">
                {formatCurrency(event.actual_cost)}
              </td>
              <td className="py-2 pr-4">
                {event.status === "open" ? (
                  <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-[#d79921]/10 text-[#d79921] border border-[#d79921]/30">
                    Abierto
                  </span>
                ) : (
                  <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-[#98971a]/10 text-[#98971a] border border-[#98971a]/30">
                    Completado
                  </span>
                )}
              </td>
              <td className="py-2 text-xs text-[#665c54]">
                {event.received_by && (
                  <div>Recibido por: {event.received_by}</div>
                )}
                {event.closing_observation && (
                  <div>Observación: {event.closing_observation}</div>
                )}
                {!event.received_by && !event.closing_observation && "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
