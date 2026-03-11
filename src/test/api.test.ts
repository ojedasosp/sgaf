import { describe, it, expect, vi, beforeEach } from "vitest";
import { setApiPort, getBaseUrl, apiFetch, ApiError } from "../lib/api";
import { useAppStore } from "../store/appStore";

// Mock global fetch
globalThis.fetch = vi.fn();

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
      vi.mocked(globalThis.fetch).mockResolvedValueOnce(mockResponse);

      await apiFetch("/health");

      expect(globalThis.fetch).toHaveBeenCalledWith(
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
      vi.mocked(globalThis.fetch).mockResolvedValueOnce(mockResponse);

      await apiFetch("/protected", { token: "jwt-token-123" });

      expect(globalThis.fetch).toHaveBeenCalledWith(
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
      vi.mocked(globalThis.fetch).mockResolvedValueOnce(mockResponse);

      const result = await apiFetch("/health");

      expect(result).toEqual(responseData);
    });

    it("throws ApiError on non-ok status with JSON error body", async () => {
      const errorBody = {
        error: "INVALID_REQUEST",
        message: "Missing required field",
        field: "code",
      };
      const mockResponse = new Response(JSON.stringify(errorBody), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
      vi.mocked(globalThis.fetch).mockResolvedValueOnce(mockResponse);

      try {
        await apiFetch("/bad-endpoint");
        expect.fail("Should have thrown");
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError);
        const apiErr = err as ApiError;
        expect(apiErr.message).toBe("Missing required field");
        expect(apiErr.status).toBe(400);
        expect(apiErr.field).toBe("code");
        expect(apiErr.errorCode).toBe("INVALID_REQUEST");
      }
    });

    it("handles error response when JSON parsing fails", async () => {
      const mockResponse = new Response("Internal Server Error", {
        status: 500,
        headers: { "Content-Type": "text/plain" },
      });
      vi.mocked(globalThis.fetch).mockResolvedValueOnce(mockResponse);

      await expect(apiFetch("/error")).rejects.toThrow("Request failed: 500");
    });

    it("respects custom fetch options (method, body)", async () => {
      const mockResponse = new Response(JSON.stringify({ id: 123 }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      });
      vi.mocked(globalThis.fetch).mockResolvedValueOnce(mockResponse);

      await apiFetch("/assets", {
        method: "POST",
        body: JSON.stringify({ name: "Asset 1" }),
      });

      expect(globalThis.fetch).toHaveBeenCalledWith(
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
      vi.mocked(globalThis.fetch).mockResolvedValueOnce(mockResponse);

      await apiFetch("/endpoint", {
        headers: { "X-Custom": "value" },
      });

      const callArgs = vi.mocked(globalThis.fetch).mock.calls[0][1];
      expect(callArgs?.headers).toEqual(
        expect.objectContaining({
          "Content-Type": "application/json",
          "X-Custom": "value",
        })
      );
    });

    it("handles network failure gracefully", async () => {
      vi.mocked(globalThis.fetch).mockRejectedValueOnce(
        new Error("Network error")
      );

      await expect(apiFetch("/endpoint")).rejects.toThrow("Network error");
    });

    it("works with different response status codes (201, 204)", async () => {
      const mockResponse = new Response(JSON.stringify({ id: 1 }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      });
      vi.mocked(globalThis.fetch).mockResolvedValueOnce(mockResponse);

      const result = await apiFetch("/create");
      expect(result).toEqual({ id: 1 });
    });

    it("rejects response with non-JSON content-type on success status", async () => {
      const mockResponse = new Response("<html>Server error</html>", {
        status: 200,
        headers: { "Content-Type": "text/html" },
      });
      vi.mocked(globalThis.fetch).mockResolvedValueOnce(mockResponse);

      await expect(apiFetch("/endpoint")).rejects.toThrow(
        "Expected JSON response, got text/html"
      );
    });

    it("rejects response with missing content-type header", async () => {
      const mockResponse = new Response(JSON.stringify({ data: "test" }), {
        status: 200,
        // No Content-Type header
      });
      vi.mocked(globalThis.fetch).mockResolvedValueOnce(mockResponse);

      await expect(apiFetch("/endpoint")).rejects.toThrow(
        "Expected JSON response"
      );
    });

    it("clears Zustand token on 401 when token was provided", async () => {
      useAppStore.getState().setToken("stale-jwt");
      const mockResponse = new Response(
        JSON.stringify({ error: "UNAUTHORIZED", message: "Invalid or missing token" }),
        { status: 401, headers: { "Content-Type": "application/json" } }
      );
      vi.mocked(globalThis.fetch).mockResolvedValueOnce(mockResponse);

      await expect(apiFetch("/protected", { token: "stale-jwt" })).rejects.toThrow(
        "Invalid or missing token"
      );
      expect(useAppStore.getState().token).toBeNull();
    });

    it("does not clear token on 401 when no token was sent (e.g. login)", async () => {
      useAppStore.getState().setToken("existing-jwt");
      const mockResponse = new Response(
        JSON.stringify({ error: "UNAUTHORIZED", message: "Invalid credentials" }),
        { status: 401, headers: { "Content-Type": "application/json" } }
      );
      vi.mocked(globalThis.fetch).mockResolvedValueOnce(mockResponse);

      await expect(apiFetch("/auth/login", { method: "POST" })).rejects.toThrow(
        "Invalid credentials"
      );
      // Token should remain — this was a login attempt, not a session rejection
      expect(useAppStore.getState().token).toBe("existing-jwt");
    });
  });
});
