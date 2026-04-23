/**
 * ReportsPage — Generate and save NIIF PDF reports (Story 4.2).
 *
 * Three report types:
 *  - per_asset: depreciation schedule for a single asset (requires asset + period)
 *  - monthly_summary: consolidated monthly depreciation (requires period)
 *  - asset_register: full register of all active assets (no period required)
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useGetAssets } from "../../hooks/useAssets";
import AppLayout from "../../components/layout/AppLayout";
import PdfReportCard from "./PdfReportCard";

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

const CURRENT_YEAR = new Date().getFullYear();
const YEAR_OPTIONS = Array.from(
  { length: CURRENT_YEAR - (CURRENT_YEAR - 5) + 2 },
  (_, i) => CURRENT_YEAR - 5 + i,
);

export default function ReportsPage() {
  const navigate = useNavigate();

  const now = new Date();
  const [periodMonth, setPeriodMonth] = useState(now.getMonth() + 1);
  const [periodYear, setPeriodYear] = useState(now.getFullYear());
  const [selectedAssetId, setSelectedAssetId] = useState<number | undefined>(undefined);

  // Life sheet state
  const [lifeSheetAssetId, setLifeSheetAssetId] = useState<number | undefined>(undefined);
  const [lifeSheetFilterAll, setLifeSheetFilterAll] = useState(true);
  const [lifeSheetMonth, setLifeSheetMonth] = useState(now.getMonth() + 1);
  const [lifeSheetYear, setLifeSheetYear] = useState(now.getFullYear());

  const { data: assets } = useGetAssets();
  const activeAssets = (assets ?? []).filter((a) => a.status !== "retired");

  return (
    <AppLayout>
      {/* Header */}
      <div className="border-b border-[#d5c4a1] bg-[#ebdbb2] px-6 py-4">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => navigate("/dashboard")}
            className="text-sm text-[#665c54] hover:text-[#458588] hover:underline"
          >
            ← Dashboard
          </button>
          <h1 className="text-base font-semibold text-[#3c3836]">Reportes PDF</h1>
        </div>
      </div>

      <div className="mx-auto max-w-2xl px-6 py-8">
        {/* Period selector */}
        <div className="mb-6 flex flex-wrap items-center gap-3">
          <label className="text-sm font-medium text-[#3c3836]">Período:</label>
          <select
            value={periodMonth}
            onChange={(e) => setPeriodMonth(Number(e.target.value))}
            className="rounded-md border border-[#d5c4a1] bg-[#fbf1c7] px-3 py-1.5 text-sm text-[#3c3836]"
            aria-label="Mes"
          >
            {Object.entries(MONTH_LABELS).map(([num, name]) => (
              <option key={num} value={num}>
                {name}
              </option>
            ))}
          </select>
          <select
            value={periodYear}
            onChange={(e) => setPeriodYear(Number(e.target.value))}
            className="rounded-md border border-[#d5c4a1] bg-[#fbf1c7] px-3 py-1.5 text-sm text-[#3c3836]"
            aria-label="Año"
          >
            {YEAR_OPTIONS.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </div>

        {/* Asset selector — only used for per_asset report */}
        <div className="mb-6 flex flex-wrap items-center gap-3">
          <label className="text-sm font-medium text-[#3c3836]">Activo (para reporte individual):</label>
          <select
            value={selectedAssetId ?? ""}
            onChange={(e) =>
              setSelectedAssetId(e.target.value ? Number(e.target.value) : undefined)
            }
            className="rounded-md border border-[#d5c4a1] bg-[#fbf1c7] px-3 py-1.5 text-sm text-[#3c3836]"
            aria-label="Activo"
          >
            <option value="">— Seleccionar activo —</option>
            {activeAssets.map((a) => (
              <option key={a.asset_id} value={a.asset_id}>
                {a.code} — {a.description}
              </option>
            ))}
          </select>
        </div>

        {/* Report cards */}
        <div className="space-y-4">
          <PdfReportCard
            reportType="per_asset"
            label="Calendario de Depreciación por Activo"
            periodMonth={periodMonth}
            periodYear={periodYear}
            assetId={selectedAssetId}
          />

          <PdfReportCard
            reportType="monthly_summary"
            label="Resumen Mensual Consolidado"
            periodMonth={periodMonth}
            periodYear={periodYear}
          />

          <PdfReportCard
            reportType="asset_register"
            label="Registro de Activos Fijos"
          />

          {/* Hoja de Vida del Activo */}
          <div className="rounded-lg border border-[#d5c4a1] bg-[#f2e5bc] px-6 py-4">
            <h3 className="mb-3 text-sm font-semibold text-[#3c3836]">Hoja de Vida del Activo</h3>

            {/* Asset selector for life sheet */}
            <div className="mb-3 flex flex-wrap items-center gap-3">
              <label className="text-sm font-medium text-[#3c3836]">Activo:</label>
              <select
                value={lifeSheetAssetId ?? ""}
                onChange={(e) =>
                  setLifeSheetAssetId(e.target.value ? Number(e.target.value) : undefined)
                }
                className="rounded-md border border-[#d5c4a1] bg-[#fbf1c7] px-3 py-1.5 text-sm text-[#3c3836]"
                aria-label="Activo para hoja de vida"
              >
                <option value="">— Seleccionar activo —</option>
                {activeAssets.map((a) => (
                  <option key={a.asset_id} value={a.asset_id}>
                    {a.code} — {a.description}
                  </option>
                ))}
              </select>
            </div>

            {/* Filter selector */}
            <div className="mb-4 space-y-2">
              <label className="flex items-center gap-2 text-sm text-[#3c3836]">
                <input
                  type="checkbox"
                  checked={lifeSheetFilterAll}
                  onChange={(e) => setLifeSheetFilterAll(e.target.checked)}
                  className="accent-[#458588]"
                />
                Todos los mantenimientos
              </label>
              {!lifeSheetFilterAll && (
                <div className="flex flex-wrap items-center gap-3 pl-6">
                  <label className="text-sm text-[#665c54]">Período:</label>
                  <select
                    value={lifeSheetMonth}
                    onChange={(e) => setLifeSheetMonth(Number(e.target.value))}
                    className="rounded-md border border-[#d5c4a1] bg-[#fbf1c7] px-3 py-1.5 text-sm text-[#3c3836]"
                    aria-label="Mes filtro hoja de vida"
                  >
                    {Object.entries(MONTH_LABELS).map(([num, name]) => (
                      <option key={num} value={num}>{name}</option>
                    ))}
                  </select>
                  <select
                    value={lifeSheetYear}
                    onChange={(e) => setLifeSheetYear(Number(e.target.value))}
                    className="rounded-md border border-[#d5c4a1] bg-[#fbf1c7] px-3 py-1.5 text-sm text-[#3c3836]"
                    aria-label="Año filtro hoja de vida"
                  >
                    {YEAR_OPTIONS.map((y) => (
                      <option key={y} value={y}>{y}</option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            <PdfReportCard
              reportType="asset_life_sheet"
              label=""
              assetId={lifeSheetAssetId}
              filterMonth={lifeSheetFilterAll ? null : lifeSheetMonth}
              filterYear={lifeSheetFilterAll ? null : lifeSheetYear}
            />
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
