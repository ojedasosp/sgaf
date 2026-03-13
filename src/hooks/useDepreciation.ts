/// TanStack Query hooks for depreciation calculation (queries and mutations).

import { useMutation, useQuery } from "@tanstack/react-query";
import {
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
 */
export function useTriggerDepreciation() {
  const token = useAppStore((s) => s.token);
  return useMutation({
    mutationFn: (params: { periodMonth: number; periodYear: number }) =>
      triggerDepreciation(params.periodMonth, params.periodYear, token ?? ""),
  });
}
