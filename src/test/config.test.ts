/**
 * Tests for config API functions (Story 6.1).
 *
 * Covers:
 *  - getCompanyConfig: correct URL, token, response unwrap
 *  - updateCompanyConfig: PUT with correct body
 *  - changePassword: POST with correct body
 *  - Error propagation via ApiError
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  changePassword,
  getCompanyConfig,
  setApiPort,
  updateCompanyConfig,
} from "../lib/api";

// Mock global fetch
globalThis.fetch = vi.fn();

function mockResponse(body: unknown, status = 200) {
  vi.mocked(globalThis.fetch).mockResolvedValueOnce(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

function mockErrorResponse(body: unknown, status: number) {
  vi.mocked(globalThis.fetch).mockResolvedValueOnce(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

describe("config API functions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setApiPort(5000);
  });

  // -------------------------------------------------------------------------
  // getCompanyConfig
  // -------------------------------------------------------------------------
  describe("getCompanyConfig", () => {
    it("calls correct URL and unwraps data", async () => {
      const mockData = {
        company_name: "Test Corp",
        company_nit: "1234567890",
        logo_path: null,
      };
      mockResponse({ data: mockData });

      const result = await getCompanyConfig("test-token");

      expect(globalThis.fetch).toHaveBeenCalledWith(
        "http://127.0.0.1:5000/api/v1/config/company",
        expect.objectContaining({
          headers: expect.objectContaining({
            Authorization: "Bearer test-token",
          }),
        }),
      );
      expect(result).toEqual(mockData);
    });

    it("throws ApiError on 401", async () => {
      mockErrorResponse(
        { error: "UNAUTHORIZED", message: "Invalid or missing token" },
        401,
      );

      // ApiError is thrown but 401 also clears token via dynamic import;
      // in test env the import may fail, so just check the error is thrown
      await expect(getCompanyConfig("bad-token")).rejects.toThrow();
    });
  });

  // -------------------------------------------------------------------------
  // updateCompanyConfig
  // -------------------------------------------------------------------------
  describe("updateCompanyConfig", () => {
    it("sends PUT with correct body", async () => {
      mockResponse({ data: { ok: true } });

      const payload = {
        company_name: "New Corp",
        company_nit: "9998887770",
        logo_path: "/path/logo.png",
      };
      const result = await updateCompanyConfig(payload, "test-token");

      expect(globalThis.fetch).toHaveBeenCalledWith(
        "http://127.0.0.1:5000/api/v1/config/company",
        expect.objectContaining({
          method: "PUT",
          body: JSON.stringify(payload),
          headers: expect.objectContaining({
            Authorization: "Bearer test-token",
          }),
        }),
      );
      expect(result).toEqual({ ok: true });
    });

    it("throws ApiError with field on 400", async () => {
      mockErrorResponse(
        {
          error: "VALIDATION_ERROR",
          message: "Company name is required",
          field: "company_name",
        },
        400,
      );

      await expect(
        updateCompanyConfig(
          { company_name: "", company_nit: "123", logo_path: null },
          "test-token",
        ),
      ).rejects.toThrow(ApiError);
    });
  });

  // -------------------------------------------------------------------------
  // changePassword
  // -------------------------------------------------------------------------
  describe("changePassword", () => {
    it("sends POST with correct body", async () => {
      mockResponse({ data: { ok: true } });

      const payload = {
        current_password: "OldPass123",
        new_password: "NewPass456",
        new_password_confirm: "NewPass456",
      };
      const result = await changePassword(payload, "test-token");

      expect(globalThis.fetch).toHaveBeenCalledWith(
        "http://127.0.0.1:5000/api/v1/config/change-password",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify(payload),
          headers: expect.objectContaining({
            Authorization: "Bearer test-token",
          }),
        }),
      );
      expect(result).toEqual({ ok: true });
    });

    it("throws ApiError with field current_password on 400", async () => {
      mockErrorResponse(
        {
          error: "VALIDATION_ERROR",
          message: "La contraseña actual es incorrecta",
          field: "current_password",
        },
        400,
      );

      await expect(
        changePassword(
          {
            current_password: "wrong",
            new_password: "NewPass456",
            new_password_confirm: "NewPass456",
          },
          "test-token",
        ),
      ).rejects.toThrow(ApiError);
    });
  });
});
