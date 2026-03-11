/// TanStack Query hooks for asset management (queries and mutations).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";
import { useAppStore } from "../store/appStore";
import type { Asset, CreateAssetPayload } from "../types/asset";

/**
 * Query hook for GET /api/v1/assets/ — fetch all fixed assets.
 * Returns Asset[] unwrapped from {"data": [...], "total": N}.
 * Filtering is done client-side via TanStack Table (≤500 assets per NFR4).
 */
export function useGetAssets() {
  const token = useAppStore((s) => s.token);
  return useQuery({
    queryKey: ["assets"],
    queryFn: () =>
      apiFetch<{ data: Asset[]; total: number }>("/assets/", {
        token: token ?? undefined,
      }),
    select: (response) => response.data,
  });
}

/**
 * Mutation hook for POST /api/v1/assets/ — register a new fixed asset.
 * On success, invalidates the ["assets"] query cache.
 */
export function useCreateAsset() {
  const queryClient = useQueryClient();
  const token = useAppStore((s) => s.token);

  return useMutation({
    mutationFn: (payload: CreateAssetPayload) =>
      apiFetch<{ data: Asset }>("/assets/", {
        method: "POST",
        body: JSON.stringify(payload),
        token: token ?? undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["assets"] });
    },
  });
}
