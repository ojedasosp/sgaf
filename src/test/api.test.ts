import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { setApiPort, getBaseUrl, apiFetch } from "../lib/api";

// Mock global fetch
global.fetch = vi.fn();

describe("api.ts — Flask HTTP communication", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setApiPort(5000); // Reset to default
  });

  describe("setApiPort & getBaseUrl", () => {
    it("sets and returns correct base URL with default port", () => {
      setApiPort(5000);
      expect(getBaseUrl()).toBe("http://127.0.0.1:5000/api/v1");
    });

    it("updates base URL when port changes", () => {
      setApiPort(5001);
      expect(getBaseUrl()).toBe("http://127.0.0.1:5001/api/v1");
    });

    it("handles arbitrary port numbers", () => {
      setApiPort(8080);
      expect(getBaseUrl()).toBe("http://127.0.0.1:8080/api/v1");
    });
  });

  describe("apiFetch", () => {
    beforeEach(() => {
      setApiPort(5000);
    });

    it("makes GET request to correct endpoint", async () => {
      const mockResponse = new Response(JSON.stringify({ status: "ok" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
      vi.mocked(global.fetch).mockResolvedValueOnce(mockResponse);

      await apiFetch("/health");

      expect(global.fetch).toHaveBeenCalledWith(
        "http://127.0.0.1:5000/api/v1/health",
        expect.objectContaining({
          headers: expect.objectContaining({
            "Content-Type": "application/json",
          }),
        })
      );
    });

    it("adds Authorization header when token provided", async () => {
      const mockResponse = new Response(JSON.stringify({}), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
      vi.mocked(global.fetch).mockResolvedValueOnce(mockResponse);

      await apiFetch("/protected", { token: "jwt-token-123" });

      expect(global.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            Authorization: "Bearer jwt-token-123",
          }),
        })
      );
    });

    it("parses JSON response on success (200)", async () => {
      const responseData = { status: "ok", data: [1, 2, 3] };
      const mockResponse = new Response(JSON.stringify(responseData), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
      vi.mocked(global.fetch).mockResolvedValueOnce(mockResponse);

      const result = await apiFetch("/health");

      expect(result).toEqual(responseData);
    });

    it("throws error on non-ok status with JSON error body", async () => {
      const errorBody = {
        error: "INVALID_REQUEST",
        message: "Missing required field",
      };
      const mockResponse = new Response(JSON.stringify(errorBody), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
      vi.mocked(global.fetch).mockResolvedValueOnce(mockResponse);

      await expect(apiFetch("/bad-endpoint")).rejects.toThrow(
        "Missing required field"
      );
    });

    it("handles error response when JSON parsing fails", async () => {
      const mockResponse = new Response("Internal Server Error", {
        status: 500,
        headers: { "Content-Type": "text/plain" },
      });
      vi.mocked(global.fetch).mockResolvedValueOnce(mockResponse);

      await expect(apiFetch("/error")).rejects.toThrow("Request failed: 500");
    });

    it("respects custom fetch options (method, body)", async () => {
      const mockResponse = new Response(JSON.stringify({ id: 123 }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      });
      vi.mocked(global.fetch).mockResolvedValueOnce(mockResponse);

      await apiFetch("/assets", {
        method: "POST",
        body: JSON.stringify({ name: "Asset 1" }),
      });

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/v1/assets"),
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ name: "Asset 1" }),
        })
      );
    });

    it("merges custom headers with default Content-Type", async () => {
      const mockResponse = new Response(JSON.stringify({}), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
      vi.mocked(global.fetch).mockResolvedValueOnce(mockResponse);

      await apiFetch("/endpoint", {
        headers: { "X-Custom": "value" },
      });

      const callArgs = vi.mocked(global.fetch).mock.calls[0][1];
      expect(callArgs?.headers).toEqual(
        expect.objectContaining({
          "Content-Type": "application/json",
          "X-Custom": "value",
        })
      );
    });

    it("handles network failure gracefully", async () => {
      vi.mocked(global.fetch).mockRejectedValueOnce(
        new Error("Network error")
      );

      await expect(apiFetch("/endpoint")).rejects.toThrow("Network error");
    });

    it("works with different response status codes (201, 204)", async () => {
      const mockResponse = new Response(JSON.stringify({ id: 1 }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      });
      vi.mocked(global.fetch).mockResolvedValueOnce(mockResponse);

      const result = await apiFetch("/create");
      expect(result).toEqual({ id: 1 });
    });

    it("rejects response with non-JSON content-type on success status", async () => {
      const mockResponse = new Response("<html>Server error</html>", {
        status: 200,
        headers: { "Content-Type": "text/html" },
      });
      vi.mocked(global.fetch).mockResolvedValueOnce(mockResponse);

      await expect(apiFetch("/endpoint")).rejects.toThrow(
        "Expected JSON response, got text/html"
      );
    });

    it("rejects response with missing content-type header", async () => {
      const mockResponse = new Response(JSON.stringify({ data: "test" }), {
        status: 200,
        // No Content-Type header
      });
      vi.mocked(global.fetch).mockResolvedValueOnce(mockResponse);

      await expect(apiFetch("/endpoint")).rejects.toThrow(
        "Expected JSON response"
      );
    });
  });
});
