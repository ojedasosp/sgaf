import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createMaintenanceEvent,
  getMaintenanceEvents,
} from "../lib/api";
import { useAppStore } from "../store/appStore";
import type { CreateMaintenancePayload } from "../types/maintenance";

/// Fetch maintenance events for a specific asset.
/// GET /api/v1/maintenance/?asset_id=<assetId>
/// Returns unwrapped MaintenanceEvent[].
export function useGetMaintenanceEvents(assetId: number) {
  const token = useAppStore((s) => s.token);
  return useQuery({
    queryKey: ["maintenanceEvents", assetId],
    queryFn: async () => {
      const result = await getMaintenanceEvents(assetId, token ?? "");
      return result.data;
    },
    enabled: !!token && assetId > 0,
  });
}

/// Create a new maintenance event for an asset (created directly as completed).
/// Invalidates maintenanceEvents and asset caches on success.
export function useCreateMaintenanceEvent() {
  const token = useAppStore((s) => s.token);
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateMaintenancePayload) =>
      createMaintenanceEvent(payload, token ?? ""),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: ["maintenanceEvents", variables.asset_id],
      });
      queryClient.invalidateQueries({ queryKey: ["assets", variables.asset_id] });
      queryClient.invalidateQueries({ queryKey: ["assets"] });
    },
  });
}
