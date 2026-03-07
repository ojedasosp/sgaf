import { create } from "zustand";

interface AppState {
  /// JWT token stored in memory only — never persisted to disk (NFR8)
  token: string | null;
  setToken: (token: string) => void;
  clearToken: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  token: null,
  setToken: (token) => set({ token }),
  clearToken: () => set({ token: null }),
}));
