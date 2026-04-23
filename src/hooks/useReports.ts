/// TanStack Query hooks for PDF report generation and status.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { generatePdfReport, getReportStatus } from "../lib/api";
import { useAppStore } from "../store/appStore";

/**
 * Mutation hook for POST /api/v1/reports/generate.
 * Returns a Blob with the generated PDF bytes.
 * On success for monthly_summary, invalidates the report status cache.
 */
export function useGenerateReport() {
  const token = useAppStore((s) => s.token);
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (params: {
      report_type: "per_asset" | "monthly_summary" | "asset_register" | "asset_life_sheet";
      asset_id?: number;
      period_month?: number;
      period_year?: number;
      filter_month?: number | null;
      filter_year?: number | null;
    }) => generatePdfReport(params, token ?? ""),
    onSuccess: (_data, variables) => {
      if (variables.report_type === "monthly_summary") {
        queryClient.invalidateQueries({
          queryKey: ["reportStatus", variables.period_month, variables.period_year],
        });
      }
    },
  });
}

/**
 * Query hook for GET /api/v1/reports/status — PDF generation status for a period.
 */
export function useGetReportStatus(periodMonth: number, periodYear: number) {
  const token = useAppStore((s) => s.token);
  return useQuery({
    queryKey: ["reportStatus", periodMonth, periodYear],
    queryFn: () => getReportStatus(periodMonth, periodYear, token ?? ""),
    enabled: !!token,
  });
}
