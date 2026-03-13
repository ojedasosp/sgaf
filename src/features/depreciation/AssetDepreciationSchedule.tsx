/**
 * AssetDepreciationSchedule — FR12, FR14 (Story 3.3)
 *
 * Displays the full period-by-period depreciation schedule for a single asset.
 * Fetched lazily: only renders and requests data when the parent mounts this component.
 *
 * Columns: Período | Valor Libro Apertura | Cargo Mensual | Dep. Acumulada | Valor Libro Neto
 * Monetary values displayed as-is (4-decimal strings from API).
 * Color system: Gruvbox Light (matches AssetDetail.tsx).
 */

import { useGetAssetDepreciationHistory } from "../../hooks/useDepreciation";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MONTH_LABELS: Record<number, string> = {
  1: "Enero",
  2: "Febrero",
  3: "Marzo",
  4: "Abril",
  5: "Mayo",
  6: "Junio",
  7: "Julio",
  8: "Agosto",
  9: "Septiembre",
  10: "Octubre",
  11: "Noviembre",
  12: "Diciembre",
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ScheduleSkeleton() {
  return (
    <div className="space-y-2 p-4">
      {[...Array(3)].map((_, i) => (
        <div key={i} className="flex gap-3">
          <div className="h-4 w-28 animate-pulse rounded bg-[#d5c4a1]" />
          <div className="h-4 w-24 animate-pulse rounded bg-[#d5c4a1]" />
          <div className="h-4 w-24 animate-pulse rounded bg-[#d5c4a1]" />
          <div className="h-4 w-24 animate-pulse rounded bg-[#d5c4a1]" />
          <div className="h-4 w-24 animate-pulse rounded bg-[#d5c4a1]" />
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function AssetDepreciationSchedule({ assetId }: { assetId: number }) {
  const { data, isLoading, isError } = useGetAssetDepreciationHistory(assetId);

  if (isLoading) {
    return <ScheduleSkeleton />;
  }

  if (isError) {
    return (
      <div className="px-6 py-6 text-center">
        <p className="text-sm text-[#cc241d]">No se pudo cargar la tabla de depreciación.</p>
      </div>
    );
  }

  if (!data || data.total === 0) {
    return (
      <div className="px-6 py-8 text-center">
        <p className="text-sm text-[#7c6f64]">
          No hay registros de depreciación para este activo.
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-[#ebdbb2]">
          <tr>
            <th className="px-4 py-3 text-left font-medium text-[#665c54]">Período</th>
            <th className="px-4 py-3 text-right font-medium text-[#665c54]">
              Valor Libro Apertura
            </th>
            <th className="px-4 py-3 text-right font-medium text-[#665c54]">Cargo Mensual</th>
            <th className="px-4 py-3 text-right font-medium text-[#665c54]">Dep. Acumulada</th>
            <th className="px-4 py-3 text-right font-medium text-[#665c54]">Valor Libro Neto</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[#d5c4a1]">
          {data.data.map((row) => (
            <tr key={row.result_id} className="hover:bg-[#ebdbb2]/50">
              <td className="px-4 py-3 text-[#3c3836]">
                {MONTH_LABELS[row.period_month]} {row.period_year}
              </td>
              <td className="px-4 py-3 text-right font-[IBM_Plex_Mono,monospace] text-xs text-[#3c3836]">
                {row.opening_book_value}
              </td>
              <td className="px-4 py-3 text-right font-[IBM_Plex_Mono,monospace] text-xs text-[#3c3836]">
                {row.depreciation_amount}
              </td>
              <td className="px-4 py-3 text-right font-[IBM_Plex_Mono,monospace] text-xs text-[#3c3836]">
                {row.accumulated_depreciation}
              </td>
              <td className="px-4 py-3 text-right font-[IBM_Plex_Mono,monospace] text-xs text-[#3c3836]">
                {row.book_value}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
