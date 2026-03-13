/// TanStack Query hooks for depreciation calculation (queries and mutations).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getAssetDepreciationHistory,
  getDepreciationResults,
  triggerDepreciation,
} from "../lib/api";
import { useAppStore } from "../store/appStore";

/**
 * Query hook for GET /api/v1/depreciation/ — fetch results for a period.
 */
export function useGetDepreciationResults(
  periodMonth: number,
  periodYear: number
) {
  const token = useAppStore((s) => s.token);
  return useQuery({
    queryKey: ["depreciation", periodMonth, periodYear],
    queryFn: () =>
      getDepreciationResults(periodMonth, periodYear, token ?? ""),
    enabled: !!token,
  });
}

/**
 * Mutation hook for POST /api/v1/depreciation/ — trigger calculation.
 * Invalidates the GET cache for the affected period on success so DepreciationPage
 * reflects the new results without requiring a period change.
 */
export function useTriggerDepreciation() {
  const token = useAppStore((s) => s.token);
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (params: { periodMonth: number; periodYear: number }) =>
      triggerDepreciation(params.periodMonth, params.periodYear, token ?? ""),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: ["depreciation", variables.periodMonth, variables.periodYear],
      });
      queryClient.invalidateQueries({
        queryKey: ["depreciation", "asset"],
      });
    },
  });
}

/**
 * Query hook for GET /api/v1/depreciation/assets/{assetId} —
 * full period-by-period depreciation schedule for a single asset.
 */
export function useGetAssetDepreciationHistory(assetId: number) {
  const token = useAppStore((s) => s.token);
  return useQuery({
    queryKey: ["depreciation", "asset", assetId],
    queryFn: () => getAssetDepreciationHistory(assetId, token ?? ""),
    enabled: assetId > 0 && !!token,
  });
}
