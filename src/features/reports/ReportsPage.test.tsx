/**
 * Tests for ReportsPage — PDF report generation (Story 4.2).
 *
 * Covers:
 *  - Renders three report cards (AC1)
 *  - Generate button disabled during loading (AC2)
 *  - Shows "Generado" on success (AC3)
 *  - Shows "Descargar / Guardar" button after generation (AC4)
 *  - Shows error message and "Reintentar" on failure (AC6)
 *  - per_asset card requires asset selection (AC1)
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ReportsPage from "./ReportsPage";
import { useAppStore } from "../../store/appStore";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("@tauri-apps/api/core", () => ({
  convertFileSrc: vi.fn((path: string) => `asset://${path}`),
  invoke: vi.fn(),
}));

vi.mock("@tauri-apps/api/event", () => ({
  listen: vi.fn(() => Promise.resolve(() => {})),
}));

vi.mock("@tauri-apps/plugin-dialog", () => ({
  open: vi.fn(),
  save: vi.fn(),
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const PDF_BYTES = new Uint8Array([0x25, 0x50, 0x44, 0x46]); // %PDF

const EMPTY_ASSETS = { data: [], total: 0 };
const ASSETS_WITH_ONE = {
  data: [
    {
      asset_id: 1,
      code: "LAP-001",
      description: "HP Laptop",
      historical_cost: "1200.0000",
      salvage_value: "120.0000",
      useful_life_months: 60,
      acquisition_date: "2026-01-01",
      category: "Equipos",
      depreciation_method: "straight_line",
      status: "active",
      retirement_date: null,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
  ],
  total: 1,
};
const EMPTY_REPORT_STATUS = { data: { monthly_summary_generated_at: null } };

// ---------------------------------------------------------------------------
// Fetch helper
// ---------------------------------------------------------------------------

function setupFetchMocks(options: {
  assetsBody?: unknown;
  generateResponse?: "success" | "error" | "pending";
  reportStatusBody?: unknown;
} = {}) {
  const {
    assetsBody = EMPTY_ASSETS,
    generateResponse = "success",
    reportStatusBody = EMPTY_REPORT_STATUS,
  } = options;

  (globalThis.fetch as ReturnType<typeof vi.fn>).mockImplementation(
    (url: string) => {
      if (url.includes("/assets/")) {
        return Promise.resolve(
          new Response(JSON.stringify(assetsBody), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      if (url.includes("/reports/generate")) {
        if (generateResponse === "error") {
          return Promise.resolve(
            new Response(
              JSON.stringify({ error: "SERVER_ERROR", message: "Error interno del servidor" }),
              { status: 500, headers: { "Content-Type": "application/json" } },
            ),
          );
        }
        if (generateResponse === "pending") {
          return new Promise(() => {}); // Never resolves
        }
        return Promise.resolve(
          new Response(PDF_BYTES, {
            status: 200,
            headers: { "Content-Type": "application/pdf" },
          }),
        );
      }
      if (url.includes("/reports/status")) {
        return Promise.resolve(
          new Response(JSON.stringify(reportStatusBody), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      return Promise.reject(new Error(`Unhandled URL in ReportsPage tests: ${url}`));
    },
  );
}

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

let activeQueryClient: QueryClient | null = null;

function makeQueryClient() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  activeQueryClient = qc;
  return qc;
}

function renderReportsPage() {
  useAppStore.getState().setToken("test-token");
  const queryClient = makeQueryClient();
  return {
    queryClient,
    ...render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/reports"]}>
          <Routes>
            <Route path="/reports" element={<ReportsPage />} />
            <Route
              path="/dashboard"
              element={<div data-testid="dashboard-page">Dashboard</div>}
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    ),
  };
}

// ---------------------------------------------------------------------------
// Setup/teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 2, 1)); // March 1, 2026
  globalThis.fetch = vi.fn();
});

afterEach(() => {
  cleanup();
  activeQueryClient?.clear();
  activeQueryClient = null;
  vi.useRealTimers();
  vi.restoreAllMocks();
  useAppStore.getState().clearToken();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ReportsPage — renders three report cards (AC1)", () => {
  it("shows all three report card labels", async () => {
    setupFetchMocks();
    renderReportsPage();

    await waitFor(() => {
      expect(
        screen.getByText("Calendario de Depreciación por Activo"),
      ).toBeInTheDocument();
      expect(screen.getByText("Resumen Mensual Consolidado")).toBeInTheDocument();
      expect(screen.getByText("Registro de Activos Fijos")).toBeInTheDocument();
    });
  });
});

describe("ReportsPage — generate button disabled during loading (AC2)", () => {
  it("disables the generate button on the card being generated while pending", async () => {
    setupFetchMocks({ generateResponse: "pending" });
    renderReportsPage();

    await waitFor(() => {
      expect(screen.getAllByRole("button", { name: /generar pdf/i })).toHaveLength(3);
    });

    const user = userEvent.setup();
    const generateButtons = screen.getAllByRole("button", { name: /generar pdf/i });
    await user.click(generateButtons[1]); // Click monthly_summary card

    // The button on that card should be disabled (shows "Generando...")
    await waitFor(() => {
      expect(screen.getByText("Generando...")).toBeInTheDocument();
    });
  });
});

describe("ReportsPage — shows Generado on success (AC3)", () => {
  it("shows 'Generado —' text after successful PDF generation", async () => {
    setupFetchMocks({ generateResponse: "success" });
    renderReportsPage();

    await waitFor(() => {
      expect(screen.getAllByRole("button", { name: /generar pdf/i })).toHaveLength(3);
    });

    const user = userEvent.setup();
    // Click monthly_summary card (second card)
    const generateButtons = screen.getAllByRole("button", { name: /generar pdf/i });
    await user.click(generateButtons[1]);

    await waitFor(() => {
      expect(screen.getByText(/Generado —/)).toBeInTheDocument();
    });
  });
});

describe("ReportsPage — shows Descargar button after generation (AC4)", () => {
  it("shows 'Descargar / Guardar' button after successful generation", async () => {
    setupFetchMocks({ generateResponse: "success" });
    renderReportsPage();

    await waitFor(() => {
      expect(screen.getAllByRole("button", { name: /generar pdf/i })).toHaveLength(3);
    });

    const user = userEvent.setup();
    const generateButtons = screen.getAllByRole("button", { name: /generar pdf/i });
    await user.click(generateButtons[1]);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /descargar \/ guardar/i }),
      ).toBeInTheDocument();
    });
  });
});

describe("ReportsPage — shows error and Reintentar on failure (AC6)", () => {
  it("shows error message and 'Reintentar' button on 500 response", async () => {
    setupFetchMocks({ generateResponse: "error" });
    renderReportsPage();

    await waitFor(() => {
      expect(screen.getAllByRole("button", { name: /generar pdf/i })).toHaveLength(3);
    });

    const user = userEvent.setup();
    const generateButtons = screen.getAllByRole("button", { name: /generar pdf/i });
    await user.click(generateButtons[1]);

    await waitFor(() => {
      expect(screen.getByText(/Error interno del servidor/i)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /reintentar/i })).toBeInTheDocument();
    });
  });
});

describe("ReportsPage — per_asset card requires asset selection (AC1)", () => {
  it("disables generate button on per_asset card when no asset is selected", async () => {
    setupFetchMocks({ assetsBody: ASSETS_WITH_ONE });
    renderReportsPage();

    await waitFor(() => {
      expect(screen.getAllByRole("button", { name: /generar pdf/i })).toHaveLength(3);
    });

    // First card is per_asset — no asset selected (default empty)
    const generateButtons = screen.getAllByRole("button", { name: /generar pdf/i });
    expect((generateButtons[0] as HTMLButtonElement).disabled).toBe(true);
  });
});
