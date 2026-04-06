/**
 * Tests for maintenance API functions.
 *
 * Covers:
 *  - getMaintenanceEvents: correct URL, token, response parsing
 *  - createMaintenanceEvent: POST with correct body + response (event created as completed)
 *  - Error propagation via ApiError
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  createMaintenanceEvent,
  getMaintenanceEvents,
  setApiPort,
} from "../lib/api";
import type { MaintenanceEvent } from "../types/maintenance";

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

const MOCK_EVENT: MaintenanceEvent = {
  event_id: 1,
  asset_id: 42,
  description: "Falla en pantalla",
  start_date: "2026-03-16",
  event_type: "correctivo",
  vendor: "TechService S.A.",
  estimated_delivery_date: "2026-03-20",
  actual_delivery_date: null,
  actual_cost: null,
  received_by: null,
  closing_observation: null,
  status: "completed",
  created_at: "2026-03-16T10:00:00Z",
  updated_at: "2026-03-16T10:00:00Z",
};

describe("maintenance API functions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setApiPort(5000);
  });

  // -------------------------------------------------------------------------
  // getMaintenanceEvents
  // -------------------------------------------------------------------------
  describe("getMaintenanceEvents", () => {
    it("calls correct URL with asset_id filter", async () => {
      mockResponse({ data: [MOCK_EVENT], total: 1 });

      await getMaintenanceEvents(42, "test-token");

      expect(globalThis.fetch).toHaveBeenCalledWith(
        "http://127.0.0.1:5000/api/v1/maintenance/?asset_id=42",
        expect.objectContaining({
          headers: expect.objectContaining({
            Authorization: "Bearer test-token",
          }),
        }),
      );
    });

    it("returns parsed maintenance events", async () => {
      mockResponse({ data: [MOCK_EVENT], total: 1 });

      const result = await getMaintenanceEvents(42, "test-token");

      expect(result.data).toHaveLength(1);
      expect(result.data[0].event_id).toBe(1);
      expect(result.data[0].status).toBe("completed");
      expect(result.total).toBe(1);
    });

    it("returns empty list when no events", async () => {
      mockResponse({ data: [], total: 0 });

      const result = await getMaintenanceEvents(99, "test-token");

      expect(result.data).toHaveLength(0);
      expect(result.total).toBe(0);
    });

    it("throws ApiError on 401", async () => {
      vi.mocked(globalThis.fetch).mockResolvedValueOnce(
        new Response(
          JSON.stringify({ error: "UNAUTHORIZED", message: "Invalid token" }),
          {
            status: 401,
            headers: { "Content-Type": "application/json" },
          },
        ),
      );

      await expect(getMaintenanceEvents(42, "bad-token")).rejects.toThrow(
        ApiError,
      );
    });
  });

  // -------------------------------------------------------------------------
  // createMaintenanceEvent
  // -------------------------------------------------------------------------
  describe("createMaintenanceEvent", () => {
    it("calls POST /maintenance/ with correct body", async () => {
      mockResponse({ data: MOCK_EVENT });

      await createMaintenanceEvent(
        {
          asset_id: 42,
          entry_date: "2026-03-16",
          event_type: "correctivo",
          vendor: "TechService S.A.",
        },
        "test-token",
      );

      expect(globalThis.fetch).toHaveBeenCalledWith(
        "http://127.0.0.1:5000/api/v1/maintenance/",
        expect.objectContaining({
          method: "POST",
          headers: expect.objectContaining({
            Authorization: "Bearer test-token",
            "Content-Type": "application/json",
          }),
        }),
      );

      const callArgs = vi.mocked(globalThis.fetch).mock.calls[0];
      const body = JSON.parse((callArgs[1] as RequestInit).body as string);
      expect(body.asset_id).toBe(42);
      expect(body.entry_date).toBe("2026-03-16");
      expect(body.event_type).toBe("correctivo");
    });

    it("returns created event data with status completed", async () => {
      mockResponse({ data: MOCK_EVENT });

      const result = await createMaintenanceEvent(
        { asset_id: 42, entry_date: "2026-03-16" },
        "test-token",
      );

      expect(result.data.event_id).toBe(1);
      expect(result.data.status).toBe("completed");
      expect(result.data.asset_id).toBe(42);
    });

    it("sends closure fields when provided", async () => {
      mockResponse({ data: MOCK_EVENT });

      await createMaintenanceEvent(
        {
          asset_id: 42,
          entry_date: "2026-03-16",
          actual_delivery_date: "2026-03-19",
          actual_cost: "140.00",
          received_by: "Juan Pérez",
          closing_observation: "Reparación exitosa",
        },
        "test-token",
      );

      const callArgs = vi.mocked(globalThis.fetch).mock.calls[0];
      const body = JSON.parse((callArgs[1] as RequestInit).body as string);
      expect(body.actual_delivery_date).toBe("2026-03-19");
      expect(body.actual_cost).toBe("140.00");
      expect(body.received_by).toBe("Juan Pérez");
      expect(body.closing_observation).toBe("Reparación exitosa");
    });

    it("throws ApiError with field on 400 validation error", async () => {
      vi.mocked(globalThis.fetch).mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            error: "VALIDATION_ERROR",
            message: "La fecha de ingreso es obligatoria",
            field: "entry_date",
          }),
          {
            status: 400,
            headers: { "Content-Type": "application/json" },
          },
        ),
      );

      try {
        await createMaintenanceEvent({ asset_id: 42, entry_date: "" }, "test-token");
        expect.fail("Should have thrown");
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError);
        expect((err as ApiError).status).toBe(400);
        expect((err as ApiError).field).toBe("entry_date");
      }
    });

    it("throws ApiError on 409 when asset not active", async () => {
      vi.mocked(globalThis.fetch).mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            error: "CONFLICT",
            message: "El activo no está disponible para mantenimiento",
          }),
          {
            status: 409,
            headers: { "Content-Type": "application/json" },
          },
        ),
      );

      await expect(
        createMaintenanceEvent(
          { asset_id: 42, entry_date: "2026-03-16" },
          "test-token",
        ),
      ).rejects.toThrow(ApiError);
    });
  });
});
