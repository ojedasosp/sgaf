/**
 * DashboardPage — Monthly Close Dashboard, Pantalla de Inicio (Base).
 * Story 3.4: Shell with 2 status rows (Assets + Depreciation).
 *
 * PDF status row added in Story 4.2 (Epic 4).
 * ZEUS export row + "Mes Cerrado" state added in Story 5.2 (Epic 5).
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useGetAssets } from "../../hooks/useAssets";
import { useGetDepreciationResults } from "../../hooks/useDepreciation";
import { useGetReportStatus } from "../../hooks/useReports";
import AppLayout from "@/components/layout/AppLayout";

// Reuse same month labels as DepreciationPage — defined inline (no premature abstraction)
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

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString("es-ES", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function DashboardPage() {
  const navigate = useNavigate();
  const now = new Date();
  const [periodMonth, setPeriodMonth] = useState(now.getMonth() + 1);
  const [periodYear, setPeriodYear] = useState(now.getFullYear());

  const {
    data: assets,
    isLoading: assetsLoading,
    isError: assetsError,
  } = useGetAssets();
  const {
    data: deprResults,
    isLoading: deprLoading,
    isError: deprError,
  } = useGetDepreciationResults(periodMonth, periodYear);
  const {
    data: reportStatus,
    isLoading: reportStatusLoading,
    isError: reportStatusError,
  } = useGetReportStatus(periodMonth, periodYear);

  const isLoading = assetsLoading || deprLoading || reportStatusLoading;
  const hasError = assetsError || deprError || reportStatusError;

  // Asset summary — active assets only
  const activeAssets = (assets ?? []).filter((a) => a.status === "active");
  const readyCount = activeAssets.filter(
    (a) => a.useful_life_months > 0,
  ).length;
  const incompleteCount = activeAssets.filter(
    (a) => a.useful_life_months <= 0,
  ).length;

  // Depreciation status for selected period
  const isCalculated = (deprResults?.total ?? 0) > 0;
  const calculatedAt = deprResults?.calculated_at ?? null;

  // PDF status for selected period
  const isPdfGenerated = !!reportStatus?.monthly_summary_generated_at;
  const pdfGeneratedAt = reportStatus?.monthly_summary_generated_at ?? null;

  // CTA 3-state logic
  const ctaLabel = !isCalculated
    ? `Calcular Depreciación — ${MONTH_LABELS[periodMonth]} ${periodYear}`
    : !isPdfGenerated
      ? "Generar Reporte PDF"
      : "Exportar a ZEUS";
  const ctaPath = !isCalculated ? "/depreciation" : "/reports";

  function prevPeriod() {
    if (periodMonth === 1) {
      setPeriodMonth(12);
      setPeriodYear((y) => y - 1);
    } else {
      setPeriodMonth((m) => m - 1);
    }
  }

  function nextPeriod() {
    if (periodMonth === 12) {
      setPeriodMonth(1);
      setPeriodYear((y) => y + 1);
    } else {
      setPeriodMonth((m) => m + 1);
    }
  }

  return (
    <AppLayout>
      {/* Period navigator */}
      <div className="border-b border-[#d5c4a1] bg-[#ebdbb2] px-6 py-4">
        <div className="flex items-center justify-end">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={prevPeriod}
              className="rounded-md border border-[#d5c4a1] bg-[#ebdbb2] px-3 py-1 text-sm text-[#3c3836] hover:bg-[#d5c4a1]"
              aria-label="Mes anterior"
            >
              ←
            </button>
            <span
              className="text-base font-semibold text-[#3c3836]"
              aria-label="Período activo"
            >
              {MONTH_LABELS[periodMonth]} {periodYear}
            </span>
            <button
              type="button"
              onClick={nextPeriod}
              className="rounded-md border border-[#d5c4a1] bg-[#ebdbb2] px-3 py-1 text-sm text-[#3c3836] hover:bg-[#d5c4a1]"
              aria-label="Mes siguiente"
            >
              →
            </button>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="mx-auto max-w-2xl px-6 py-8">
        {isLoading ? (
          /* Loading skeleton */
          <div className="space-y-3" aria-label="Cargando estado del período">
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="h-16 animate-pulse rounded-lg bg-[#d5c4a1]"
              />
            ))}
          </div>
        ) : hasError ? (
          /* Error state */
          <div
            className="rounded-lg border border-[#9d0006] bg-[#fbf1c7] px-6 py-4"
            role="alert"
          >
            <p className="text-sm font-medium text-[#9d0006]">
              Error al cargar el estado del período. Por favor, recarga la
              página.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Assets status row */}
            <div className="rounded-lg border border-[#d5c4a1] bg-[#f2e5bc] px-6 py-4">
              <div className="flex items-start gap-3">
                {incompleteCount === 0 ? (
                  <span
                    className="mt-0.5 text-lg leading-none text-[#98971a]"
                    aria-hidden="true"
                  >
                    ✓
                  </span>
                ) : (
                  <span
                    className="mt-0.5 text-lg leading-none text-[#d79921]"
                    aria-hidden="true"
                  >
                    ○
                  </span>
                )}
                <div>
                  <p className="text-sm font-medium text-[#3c3836]">
                    Activos: {readyCount} listos
                    {incompleteCount > 0 && ` — ${incompleteCount} incompletos`}
                  </p>
                  {incompleteCount > 0 && (
                    <button
                      type="button"
                      onClick={() => navigate("/assets")}
                      className="mt-0.5 text-xs text-[#665c54] hover:text-[#458588] hover:underline"
                    >
                      Ver activos incompletos
                    </button>
                  )}
                </div>
              </div>
            </div>

            {/* Depreciation status row */}
            <div className="rounded-lg border border-[#d5c4a1] bg-[#f2e5bc] px-6 py-4">
              <div className="flex items-start gap-3">
                {isCalculated ? (
                  <span
                    className="mt-0.5 text-lg leading-none text-[#98971a]"
                    aria-hidden="true"
                  >
                    ✓
                  </span>
                ) : (
                  <span
                    className="mt-0.5 text-lg leading-none text-[#d79921]"
                    aria-hidden="true"
                  >
                    ○
                  </span>
                )}
                <p className="text-sm font-medium text-[#3c3836]">
                  Depreciación:{" "}
                  {isCalculated
                    ? `Calculada — ${formatTimestamp(calculatedAt!)} — ${deprResults!.total} activo(s)`
                    : "No calculada"}
                </p>
              </div>
            </div>

            {/* PDF report status row */}
            <div className="rounded-lg border border-[#d5c4a1] bg-[#f2e5bc] px-6 py-4">
              <div className="flex items-start gap-3">
                {isPdfGenerated ? (
                  <span className="mt-0.5 text-lg leading-none text-[#98971a]" aria-hidden="true">✓</span>
                ) : (
                  <span className="mt-0.5 text-lg leading-none text-[#d79921]" aria-hidden="true">○</span>
                )}
                <p className="text-sm font-medium text-[#3c3836]">
                  Reporte PDF:{" "}
                  {isPdfGenerated
                    ? `Generado — ${formatTimestamp(pdfGeneratedAt!)}`
                    : "Pendiente"}
                </p>
              </div>
            </div>

            {/* Primary CTA */}
            <div className="pt-2">
              <button
                type="button"
                onClick={() => navigate(ctaPath)}
                disabled={isLoading}
                className="rounded-md bg-[#458588] px-6 py-2 text-sm font-medium text-white hover:bg-[#076678] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {ctaLabel}
              </button>
            </div>
          </div>
        )}
      </div>
    </AppLayout>
  );
}
