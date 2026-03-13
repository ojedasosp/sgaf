/// TanStack Query hook for the read-only audit log endpoint.

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";
import { useAppStore } from "../store/appStore";
import type { AuditLogEntry } from "../types/asset";

/**
 * Query hook for GET /api/v1/audit/?entity_type=asset&entity_id=<assetId>
 * Returns AuditLogEntry[] unwrapped from {"data": [...], "total": N}.
 * Entries are already ordered by timestamp DESC (most recent first).
 */
export function useGetAssetAuditLog(assetId: number) {
  const token = useAppStore((s) => s.token);
  return useQuery({
    queryKey: ["audit", "asset", assetId],
    queryFn: () =>
      apiFetch<{ data: AuditLogEntry[]; total: number }>(
        `/audit/?entity_type=asset&entity_id=${assetId}`,
        { token: token ?? undefined }
      ),
    select: (response) => response.data,
  });
}
