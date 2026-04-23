import { useState } from "react";
import { useGenerateReport } from "../../hooks/useReports";
import { ApiError } from "../../lib/api";
import { saveFilePicker, writeBinaryFile } from "../../lib/tauri";

interface PdfReportCardProps {
  reportType: "per_asset" | "monthly_summary" | "asset_register" | "asset_life_sheet";
  label: string;
  periodMonth?: number;
  periodYear?: number;
  assetId?: number;
  filterMonth?: number | null;
  filterYear?: number | null;
}

function buildFilename(
  reportType: string,
  periodMonth?: number,
  periodYear?: number,
  assetId?: number,
  filterMonth?: number | null,
  filterYear?: number | null,
): string {
  if (reportType === "asset_register") {
    return "registro_activos_fijos.pdf";
  }
  if (reportType === "asset_life_sheet") {
    const suffix = filterMonth != null && filterYear != null
      ? `_${filterYear}-${String(filterMonth).padStart(2, "0")}`
      : "_todos";
    return `hoja_vida_asset${assetId ?? ""}${suffix}.pdf`;
  }
  if (reportType === "per_asset" && assetId != null) {
    return `reporte_per_asset_${periodYear}-${String(periodMonth).padStart(2, "0")}_asset${assetId}.pdf`;
  }
  return `reporte_${reportType}_${periodYear}-${String(periodMonth).padStart(2, "0")}.pdf`;
}

export default function PdfReportCard({
  reportType,
  label,
  periodMonth,
  periodYear,
  assetId,
  filterMonth,
  filterYear,
}: PdfReportCardProps) {
  const [pdfBlob, setPdfBlob] = useState<Blob | null>(null);
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const generateMutation = useGenerateReport();

  const isPerAssetWithoutAsset = reportType === "per_asset" && !assetId;
  const isLifeSheetWithoutAsset = reportType === "asset_life_sheet" && !assetId;

  function handleGenerate() {
    setError(null);
    setPdfBlob(null);
    setGeneratedAt(null);
    generateMutation.mutate(
      {
        report_type: reportType,
        asset_id: assetId,
        period_month: periodMonth,
        period_year: periodYear,
        filter_month: filterMonth,
        filter_year: filterYear,
      },
      {
        onSuccess: (blob) => {
          setPdfBlob(blob);
          setGeneratedAt(
            new Date().toLocaleString("es-ES", {
              day: "2-digit",
              month: "2-digit",
              year: "numeric",
              hour: "2-digit",
              minute: "2-digit",
            }),
          );
        },
        onError: (err) => {
          if (err instanceof ApiError) {
            setError(err.message);
          } else {
            setError("Error desconocido al generar el reporte");
          }
        },
      },
    );
  }

  async function handleSave() {
    if (!pdfBlob) return;
    setIsSaving(true);
    try {
      const filename = buildFilename(reportType, periodMonth, periodYear, assetId, filterMonth, filterYear);
      const path = await saveFilePicker({
        title: "Guardar reporte PDF",
        defaultPath: filename,
        filters: [{ name: "PDF", extensions: ["pdf"] }],
      });
      if (!path) return;
      const arrayBuffer = await pdfBlob.arrayBuffer();
      const bytes = new Uint8Array(arrayBuffer);
      await writeBinaryFile(path, bytes);
    } catch (err) {
      setError(
        err instanceof Error
          ? `Error al guardar: ${err.message}`
          : "Error desconocido al guardar el archivo",
      );
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div
      className="rounded-lg border border-[#d5c4a1] bg-[#f2e5bc] px-6 py-4"
      data-testid={`report-card-${reportType}`}
    >
      <h3 className="mb-3 text-sm font-semibold text-[#3c3836]">{label}</h3>

      {/* Loading skeleton */}
      {generateMutation.isPending && (
        <div className="mb-3 h-4 w-3/4 animate-pulse rounded bg-[#d5c4a1]" />
      )}

      {/* Success state */}
      {generatedAt && !generateMutation.isPending && (
        <p className="mb-3 text-xs text-[#98971a]">Generado — {generatedAt}</p>
      )}

      {/* Error state */}
      {error && !generateMutation.isPending && (
        <p className="mb-3 text-xs text-[#9d0006]">{error}</p>
      )}

      {/* Actions */}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={handleGenerate}
          disabled={generateMutation.isPending || isPerAssetWithoutAsset || isLifeSheetWithoutAsset}
          className="rounded-md bg-[#458588] px-4 py-1.5 text-xs font-medium text-white hover:bg-[#076678] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {generateMutation.isPending ? "Generando..." : error ? "Reintentar" : "Generar PDF"}
        </button>

        {pdfBlob && !generateMutation.isPending && (
          <button
            type="button"
            onClick={handleSave}
            disabled={isSaving}
            className="rounded-md border border-[#458588] px-4 py-1.5 text-xs font-medium text-[#458588] hover:bg-[#d5c4a1] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSaving ? "Guardando..." : "Descargar / Guardar"}
          </button>
        )}
      </div>
    </div>
  );
}
