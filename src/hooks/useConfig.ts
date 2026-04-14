import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAppStore } from "../store/appStore";
import { getCompanyConfig, updateCompanyConfig, changePassword, getCategories, updateCategories } from "../lib/api";

/// Fetch current company config (name, NIT, logo path).
export function useGetCompanyConfig() {
  const token = useAppStore((s) => s.token);
  return useQuery({
    queryKey: ["companyConfig"],
    queryFn: async () => getCompanyConfig(token ?? ""),
    enabled: !!token,
  });
}

/// Update company info (name, NIT, logo).
export function useUpdateCompanyConfig() {
  const token = useAppStore((s) => s.token);
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      company_name: string;
      company_nit: string;
      logo_path: string | null;
    }) => updateCompanyConfig(payload, token ?? ""),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["companyConfig"] });
    },
  });
}

/// Change application password.
export function useChangePassword() {
  const token = useAppStore((s) => s.token);
  return useMutation({
    mutationFn: (payload: {
      current_password: string;
      new_password: string;
      new_password_confirm: string;
    }) => changePassword(payload, token ?? ""),
  });
}

/// Fetch the configured asset category list.
export function useGetCategories() {
  const token = useAppStore((s) => s.token);
  return useQuery({
    queryKey: ["categories"],
    queryFn: async () => getCategories(token ?? ""),
    enabled: !!token,
    staleTime: 5 * 60 * 1000, // 5 minutes — categories change infrequently
  });
}

/// Replace the full asset category list.
export function useUpdateCategories() {
  const token = useAppStore((s) => s.token);
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (categories: string[]) => updateCategories(categories, token ?? ""),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["categories"] });
    },
  });
}
