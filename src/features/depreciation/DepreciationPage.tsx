/**
 * DepreciationPage — FR11, FR12: Period selector, calculation trigger, results table.
 *
 * Flow:
 *  1. On mount / period change: GET existing results for selected period.
 *  2. "Calcular Depreciación" button: if results exist, show confirmation dialog.
 *     Otherwise trigger POST immediately.
 *  3. During POST: progress overlay blocks navigation.
 *  4. Results rendered in DepreciationTable.
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "@/lib/api";
import { useGetDepreciationResults, useTriggerDepreciation } from "@/hooks/useDepreciation";
import DepreciationTable from "./DepreciationTable";

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

const CURRENT_YEAR = new Date().getFullYear();
const YEAR_OPTIONS = Array.from(
  { length: CURRENT_YEAR - (CURRENT_YEAR - 5) + 2 },
  (_, i) => CURRENT_YEAR - 5 + i
);

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function DepreciationPage() {
  const navigate = useNavigate();

  const [periodMonth, setPeriodMonth] = useState<number>(new Date().getMonth() + 1);
  const [periodYear, setPeriodYear] = useState<number>(CURRENT_YEAR);
  const [showConfirm, setShowConfirm] = useState(false);

  // Load existing results whenever period changes (useQuery handles caching + refetch)
  const {
    data: existingResults,
    isLoading: loadingExisting,
    error: queryError,
  } = useGetDepreciationResults(periodMonth, periodYear);

  // Trigger calculation (useMutation handles loading state)
  const {
    mutate: calculateMutation,
    isPending: isCalculating,
    error: mutationError,
  } = useTriggerDepreciation();

  const error = queryError
    ? queryError instanceof ApiError
      ? queryError.message
      : "Error al cargar resultados"
    : mutationError
      ? mutationError instanceof ApiError
        ? mutationError.message
        : "Error inesperado al calcular la depreciación."
      : null;

  const displayResults = existingResults && existingResults.total > 0 ? existingResults : null;

  const handleCalculate = () => {
    if (existingResults && existingResults.total > 0) {
      setShowConfirm(true);
    } else {
      runCalculation();
    }
  };

  const runCalculation = () => {
    setShowConfirm(false);
    calculateMutation({ periodMonth, periodYear });
  };

  const formatDate = (isoString: string): string => {
    const date = new Date(isoString);
    return date.toLocaleDateString("es-ES", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    });
  };

  const confirmLabel =
    existingResults && existingResults.total > 0 && existingResults.calculated_at
      ? `¿Reemplazar depreciación calculada el ${formatDate(existingResults.calculated_at)} para ${existingResults.total} activo(s)?`
      : "¿Calcular depreciación para este período?";

  return (
    <div className="min-h-screen bg-background">
      {/* Progress overlay — blocks navigation during calculation */}
      {isCalculating && (
        <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-background/80 backdrop-blur-sm">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-[#458588] border-t-transparent" />
          <p className="mt-4 text-sm text-foreground">Calculando depreciación...</p>
        </div>
      )}

      {/* Recalculation confirmation dialog */}
      {showConfirm && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-md rounded-lg bg-background p-6 shadow-xl">
            <h2 className="mb-2 text-base font-semibold text-foreground">
              Confirmar recalculación
            </h2>
            <p className="mb-6 text-sm text-muted-foreground">{confirmLabel}</p>
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setShowConfirm(false)}
                className="rounded-md border border-border px-4 py-2 text-sm text-foreground hover:bg-muted"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={runCalculation}
                className="rounded-md bg-[#458588] px-4 py-2 text-sm font-medium text-white hover:bg-[#458588]/90"
              >
                Recalcular
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Page header */}
      <div className="border-b border-border px-6 py-4">
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={() => navigate("/dashboard")}
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            ← Volver
          </button>
          <h1 className="text-xl font-semibold text-foreground">Depreciación</h1>
        </div>
      </div>

      {/* Controls */}
      <div className="px-6 py-4">
        <div className="flex flex-wrap items-end gap-4">
          {/* Month selector */}
          <div className="flex flex-col gap-1">
            <label htmlFor="period-month" className="text-xs font-medium text-muted-foreground">
              Mes
            </label>
            <select
              id="period-month"
              value={periodMonth}
              onChange={(e) => setPeriodMonth(Number(e.target.value))}
              className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-[#458588]"
            >
              {Object.entries(MONTH_LABELS).map(([num, label]) => (
                <option key={num} value={num}>
                  {label}
                </option>
              ))}
            </select>
          </div>

          {/* Year selector */}
          <div className="flex flex-col gap-1">
            <label htmlFor="period-year" className="text-xs font-medium text-muted-foreground">
              Año
            </label>
            <select
              id="period-year"
              value={periodYear}
              onChange={(e) => setPeriodYear(Number(e.target.value))}
              className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-[#458588]"
            >
              {YEAR_OPTIONS.map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          </div>

          {/* Calculate button */}
          <button
            type="button"
            onClick={handleCalculate}
            disabled={isCalculating || loadingExisting}
            className="rounded-md bg-[#458588] px-5 py-2 text-sm font-medium text-white hover:bg-[#458588]/90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Calcular Depreciación
          </button>
        </div>

        {/* Error message */}
        {error && (
          <p className="mt-3 text-sm text-red-500">{error}</p>
        )}
      </div>

      {/* Results area */}
      <div className="px-6 pb-6">
        {loadingExisting ? (
          <p className="text-sm text-muted-foreground">Cargando resultados...</p>
        ) : displayResults && displayResults.total > 0 ? (
          <div>
            <p className="mb-3 text-xs text-muted-foreground">
              {displayResults.total} activo(s) — calculado el{" "}
              {displayResults.calculated_at ?? ""}
            </p>
            <DepreciationTable rows={displayResults.data} />
          </div>
        ) : existingResults && existingResults.total === 0 && existingResults.message ? (
          <p className="text-sm text-muted-foreground">{existingResults.message}</p>
        ) : existingResults && existingResults.total === 0 && !existingResults.message ? (
          <p className="text-sm text-muted-foreground">
            Calcular depreciación para este período.
          </p>
        ) : null}
      </div>
    </div>
  );
}
