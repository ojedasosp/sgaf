import { describe, it, expect, beforeEach } from "vitest";
import { useAppStore } from "../store/appStore";

describe("appStore.ts — Zustand JWT token store", () => {
  beforeEach(() => {
    // Reset store to initial state before each test
    const { clearToken } = useAppStore.getState();
    clearToken();
  });

  describe("Initial state", () => {
    it("initializes with null token", () => {
      const { token } = useAppStore.getState();
      expect(token).toBeNull();
    });
  });

  describe("setToken action", () => {
    it("sets token in store", () => {
      const { setToken } = useAppStore.getState();
      const testToken = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...";

      setToken(testToken);

      const { token } = useAppStore.getState();
      expect(token).toBe(testToken);
    });

    it("overwrites previous token", () => {
      const { setToken } = useAppStore.getState();

      setToken("token-1");
      expect(useAppStore.getState().token).toBe("token-1");

      setToken("token-2");
      expect(useAppStore.getState().token).toBe("token-2");
    });

    it("handles empty string token", () => {
      const { setToken } = useAppStore.getState();

      setToken("");

      expect(useAppStore.getState().token).toBe("");
    });

    it("handles very long JWT tokens", () => {
      const { setToken } = useAppStore.getState();
      const longToken = "x".repeat(10000); // Simulate large JWT

      setToken(longToken);

      expect(useAppStore.getState().token).toBe(longToken);
      expect(useAppStore.getState().token?.length).toBe(10000);
    });
  });

  describe("clearToken action", () => {
    it("clears token back to null", () => {
      const { setToken, clearToken } = useAppStore.getState();

      setToken("some-token");
      expect(useAppStore.getState().token).not.toBeNull();

      clearToken();

      expect(useAppStore.getState().token).toBeNull();
    });

    it("clears already-null token without error", () => {
      const { clearToken } = useAppStore.getState();

      expect(useAppStore.getState().token).toBeNull();
      clearToken(); // Should not throw

      expect(useAppStore.getState().token).toBeNull();
    });
  });

  describe("Store reactivity", () => {
    it("token state persists across store operations", () => {
      const { setToken, clearToken } = useAppStore.getState();

      setToken("persistent-token");
      expect(useAppStore.getState().token).toBe("persistent-token");

      // Token remains until explicitly cleared
      const snapshot1 = useAppStore.getState().token;
      const snapshot2 = useAppStore.getState().token;
      expect(snapshot1).toBe(snapshot2);

      clearToken();
      expect(useAppStore.getState().token).toBeNull();
    });

    it("getState returns current store state", () => {
      const { setToken } = useAppStore.getState();

      setToken("test-token");
      const state = useAppStore.getState();

      expect(state).toHaveProperty("token", "test-token");
      expect(state).toHaveProperty("setToken");
      expect(state).toHaveProperty("clearToken");
    });
  });

  describe("Store isolation between tests", () => {
    it("Token in one test doesn't affect another (test 1)", () => {
      const { setToken } = useAppStore.getState();
      setToken("test-token-1");
      expect(useAppStore.getState().token).toBe("test-token-1");
    });

    it("Token isolated in separate test (test 2)", () => {
      // beforeEach clears the store, so this starts fresh
      const { token } = useAppStore.getState();
      expect(token).toBeNull();
    });
  });

  describe("Security considerations", () => {
    it("stores JWT in memory only (ephemeral)", () => {
      const { setToken } = useAppStore.getState();
      const jwt = "jwt.token.here";

      setToken(jwt);

      // Verify it's in the store
      expect(useAppStore.getState().token).toBe(jwt);

      // In real app: token is cleared on logout or app close
      // This test just verifies the API works
    });

    it("clearToken removes sensitive data", () => {
      const { setToken, clearToken } = useAppStore.getState();
      const jwt = "sensitive.jwt.token";

      setToken(jwt);
      expect(useAppStore.getState().token).toContain("jwt");

      clearToken();
      expect(useAppStore.getState().token).toBeNull();
    });
  });
});
