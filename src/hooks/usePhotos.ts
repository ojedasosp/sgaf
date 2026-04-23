/// TanStack Query hooks for asset photo management.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  deleteAssetPhoto,
  getAssetPhotos,
  setAssetPhotoPrimary,
  uploadAssetPhoto,
} from "../lib/api";
import { useAppStore } from "../store/appStore";

export function useGetAssetPhotos(assetId: number) {
  const token = useAppStore((s) => s.token);
  return useQuery({
    queryKey: ["assetPhotos", assetId],
    queryFn: () => getAssetPhotos(assetId, token ?? ""),
    enabled: !!token && assetId > 0,
    select: (res) => res.data,
  });
}

export function useUploadAssetPhoto() {
  const token = useAppStore((s) => s.token);
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { asset_id: number; file_path: string }) =>
      uploadAssetPhoto(payload, token ?? ""),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["assetPhotos", variables.asset_id] });
    },
  });
}

export function useDeleteAssetPhoto() {
  const token = useAppStore((s) => s.token);
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ photoId }: { photoId: number; assetId: number }) =>
      deleteAssetPhoto(photoId, token ?? ""),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["assetPhotos", variables.assetId] });
    },
  });
}

export function useSetAssetPhotoPrimary() {
  const token = useAppStore((s) => s.token);
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ photoId }: { photoId: number; assetId: number }) =>
      setAssetPhotoPrimary(photoId, token ?? ""),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["assetPhotos", variables.assetId] });
    },
  });
}
