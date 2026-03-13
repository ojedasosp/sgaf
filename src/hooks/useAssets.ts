/// TanStack Query hooks for asset management (queries and mutations).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";
import { useAppStore } from "../store/appStore";
import type {
  Asset,
  CreateAssetPayload,
  RetireAssetPayload,
  UpdateAssetPayload,
} from "../types/asset";

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

/**
 * Query hook for GET /api/v1/assets/<id> — fetch a single asset by ID.
 * Returns Asset unwrapped from {"data": <asset>}.
 */
export function useGetAsset(id: number) {
  const token = useAppStore((s) => s.token);
  return useQuery({
    queryKey: ["assets", id],
    queryFn: () =>
      apiFetch<{ data: Asset }>(`/assets/${id}`, {
        token: token ?? undefined,
      }),
    select: (response) => response.data,
  });
}

/**
 * Mutation hook for PATCH /api/v1/assets/<id> — partial update of an asset.
 * On success, invalidates both the list cache and the specific asset cache.
 */
export function useUpdateAsset() {
  const queryClient = useQueryClient();
  const token = useAppStore((s) => s.token);

  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: UpdateAssetPayload }) =>
      apiFetch<{ data: Asset }>(`/assets/${id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
        token: token ?? undefined,
      }),
    onSuccess: (_data, { id }) => {
      queryClient.invalidateQueries({ queryKey: ["assets"] });
      queryClient.invalidateQueries({ queryKey: ["assets", id] });
      queryClient.invalidateQueries({ queryKey: ["audit", "asset", id] });
    },
  });
}

/**
 * Mutation hook for POST /api/v1/assets/<id>/retire — retire an active asset.
 * On success, invalidates asset list, asset detail, and audit log caches.
 */
export function useRetireAsset() {
  const queryClient = useQueryClient();
  const token = useAppStore((s) => s.token);

  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: RetireAssetPayload }) =>
      apiFetch<{ data: Asset }>(`/assets/${id}/retire`, {
        method: "POST",
        body: JSON.stringify(payload),
        token: token ?? undefined,
      }),
    onSuccess: (_data, { id }) => {
      queryClient.invalidateQueries({ queryKey: ["assets"] });
      queryClient.invalidateQueries({ queryKey: ["assets", id] });
      queryClient.invalidateQueries({ queryKey: ["audit", "asset", id] });
    },
  });
}

/**
 * Mutation hook for DELETE /api/v1/assets/<id> — delete an asset with no history.
 * On success, invalidates the asset list cache.
 */
export function useDeleteAsset() {
  const queryClient = useQueryClient();
  const token = useAppStore((s) => s.token);

  return useMutation({
    mutationFn: (id: number) =>
      apiFetch<void>(`/assets/${id}`, {
        method: "DELETE",
        token: token ?? undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["assets"] });
    },
  });
}
