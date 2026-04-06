import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAppStore } from "../store/appStore";
import { getCompanyConfig, updateCompanyConfig, changePassword } from "../lib/api";

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
