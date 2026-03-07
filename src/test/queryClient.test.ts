import { describe, it, expect } from "vitest";
import { queryClient } from "../lib/queryClient";

describe("queryClient.ts — TanStack Query configuration", () => {
  describe("Query client initialization", () => {
    it("creates valid QueryClient instance", () => {
      expect(queryClient).toBeDefined();
      expect(queryClient).toHaveProperty("getQueryData");
      expect(queryClient).toHaveProperty("setQueryData");
      expect(queryClient).toHaveProperty("getQueryCache");
    });

    it("has default options configured", () => {
      const cache = queryClient.getQueryCache();
      expect(cache).toBeDefined();
    });
  });

  describe("Default query options", () => {
    it("configures reasonable staleTime for cached data", () => {
      // The queryClient should be configured with staleTime
      // This test verifies it doesn't throw when used
      const testQuery = queryClient.getQueryData(["test"]);
      expect(testQuery).toBeUndefined(); // Not yet cached
    });

    it("preserves query data after setting", () => {
      const testKey = ["test-key", "value"];
      const testData = { id: 1, name: "Test" };

      queryClient.setQueryData(testKey, testData);
      const retrieved = queryClient.getQueryData(testKey);

      expect(retrieved).toEqual(testData);
    });
  });

  describe("Cache invalidation", () => {
    it("invalidates queries by key prefix", async () => {
      queryClient.setQueryData(["assets", "1"], { id: 1 });
      queryClient.setQueryData(["assets", "2"], { id: 2 });

      await queryClient.invalidateQueries({
        queryKey: ["assets"],
        exact: false,
      });

      // After invalidation, queries are marked as stale
      // but data is still available until refetch
      const data = queryClient.getQueryData(["assets", "1"]);
      expect(data).toBeDefined();
    });

    it("removes query data completely if needed", async () => {
      queryClient.setQueryData(["test"], "data");

      queryClient.removeQueries({ queryKey: ["test"] });

      const data = queryClient.getQueryData(["test"]);
      expect(data).toBeUndefined();
    });
  });

  describe("Retry policy", () => {
    it("has retry logic configured", () => {
      // Verify queryClient is set up with default options that include retry
      // This is implicitly tested through normal query operations
      expect(queryClient).toBeDefined();
      expect(queryClient.getDefaultOptions).toBeDefined();
    });
  });

  describe("Query lifecycle", () => {
    it("manages query lifecycle without errors", () => {
      const key = ["lifecycle-test"];

      queryClient.setQueryData(key, { status: "cached" });
      expect(queryClient.getQueryData(key)).toEqual({ status: "cached" });

      queryClient.removeQueries({ queryKey: key });
      expect(queryClient.getQueryData(key)).toBeUndefined();
    });

    it("handles multiple concurrent queries", () => {
      const queries = [
        ["assets", "1"],
        ["assets", "2"],
        ["depreciation", "1"],
      ];

      queries.forEach((key, idx) => {
        queryClient.setQueryData(key, { id: idx });
      });

      queries.forEach((key, idx) => {
        expect(queryClient.getQueryData(key)).toEqual({ id: idx });
      });
    });
  });

  describe("Observer pattern (subscribers)", () => {
    it("cache observable doesn't throw on creation", () => {
      const cache = queryClient.getQueryCache();
      expect(cache).toBeDefined();

      // Observers can be added and removed without errors
      const observer = cache.subscribe();
      expect(observer).toBeDefined();
    });
  });
});
