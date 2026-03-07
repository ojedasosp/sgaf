import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Refetch on window focus in dev; disable in prod for desktop UX
      refetchOnWindowFocus: false,
      // Retry once on failure before showing error
      retry: 1,
      // Keep data fresh for 5 minutes
      staleTime: 5 * 60 * 1000,
    },
    mutations: {
      retry: 0,
    },
  },
});
