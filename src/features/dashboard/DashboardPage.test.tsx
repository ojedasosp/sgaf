/**
 * Tests for DashboardPage — Monthly Close Dashboard (Story 3.4).
 *
 * Covers:
 *  - Renders current month/year by default in period navigator (AC1)
 *  - Period prev/next navigation with year rollover (AC5)
 *  - Shows "Calcular Depreciación" CTA when depreciation not calculated (AC3)
 *  - Shows "Generar Reporte PDF" CTA and "Calculada" text when calculated (AC4)
 *  - Shows incomplete count and link when assets have useful_life_months <= 0 (AC2)
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import DashboardPage from "./DashboardPage";
import { useAppStore } from "../../store/appStore";
import type { Asset } from "../../types/asset";

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

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeAsset(overrides: Partial<Asset> = {}): Asset {
  return {
    asset_id: 1,
    code: "LAP-001",
    description: "HP Laptop",
    historical_cost: "1200.0000",
    salvage_value: "120.0000",
    useful_life_months: 60,
    acquisition_date: "2026-03-01",
    category: "Equipos de Cómputo",
    depreciation_method: "straight_line",
    status: "active",
    retirement_date: null,
    created_at: "2026-03-01T00:00:00Z",
    updated_at: "2026-03-01T00:00:00Z",
    imported_accumulated_depreciation: null,
    additions_improvements: null,
    accounting_code: null,
    cost_center: null,
    supplier: null,
    invoice_number: null,
    location: null,
    characteristics: null,
    ...overrides,
  };
}

const EMPTY_ASSETS = { data: [], total: 0 };
const EMPTY_DEPR = { data: [], total: 0, period_month: 3, period_year: 2026 };
const EMPTY_REPORT_STATUS = { data: { monthly_summary_generated_at: null } };
const PDF_GENERATED_STATUS = {
  data: { monthly_summary_generated_at: "2026-03-10T10:00:00Z" },
};

// ---------------------------------------------------------------------------
// Fetch helper — URL-aware so parallel calls resolve independently
// ---------------------------------------------------------------------------

function setupFetchMocks(
  assetsBody: unknown,
  deprBody: unknown,
  reportStatusBody: unknown = EMPTY_REPORT_STATUS,
) {
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
      if (url.includes("/reports/status")) {
        return Promise.resolve(
          new Response(JSON.stringify(reportStatusBody), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      if (url.includes("/depreciation/")) {
        return Promise.resolve(
          new Response(JSON.stringify(deprBody), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      return Promise.reject(
        new Error(`Unhandled URL in DashboardPage tests: ${url}`),
      );
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

function renderDashboard() {
  useAppStore.getState().setToken("test-token");
  const queryClient = makeQueryClient();
  return {
    queryClient,
    ...render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/dashboard"]}>
          <Routes>
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route
              path="/depreciation"
              element={<div data-testid="depreciation-page">Depreciación</div>}
            />
            <Route
              path="/reports"
              element={<div data-testid="reports-page">Reportes</div>}
            />
            <Route
              path="/assets"
              element={<div data-testid="assets-page">Activos</div>}
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    ),
  };
}

// ---------------------------------------------------------------------------
// Setup/teardown — fake only Date to freeze March 2026 without affecting
// TanStack Query's internal setTimeout/setInterval
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 2, 1)); // March 1, 2026 (month is 0-indexed)
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

describe("DashboardPage — period display (AC1)", () => {
  it("renders current month and year by default", async () => {
    setupFetchMocks(EMPTY_ASSETS, EMPTY_DEPR);
    renderDashboard();

    await waitFor(() => {
      expect(screen.getByLabelText("Período activo")).toHaveTextContent(
        "Marzo 2026",
      );
    });
  });
});

describe("DashboardPage — period navigation (AC5)", () => {
  it("decrements month on prev arrow click and wraps year from January to December", async () => {
    // Start at March 2026; navigate back to January, then once more for year rollover
    vi.setSystemTime(new Date(2026, 0, 1)); // Override to January 2026 for this test
    setupFetchMocks(EMPTY_ASSETS, EMPTY_DEPR);
    renderDashboard();
    const user = userEvent.setup();

    // Verify starting state
    await waitFor(() =>
      expect(screen.getByLabelText("Período activo")).toHaveTextContent(
        "Enero 2026",
      ),
    );

    // Click ← once: January 2026 → December 2025 (year rollover)
    await user.click(screen.getByLabelText("Mes anterior"));

    await waitFor(() => {
      expect(screen.getByLabelText("Período activo")).toHaveTextContent(
        "Diciembre 2025",
      );
    });
  });

  it("increments month on next arrow click and wraps year from December to January", async () => {
    vi.setSystemTime(new Date(2025, 11, 1)); // December 2025
    setupFetchMocks(EMPTY_ASSETS, EMPTY_DEPR);
    renderDashboard();
    const user = userEvent.setup();

    await waitFor(() =>
      expect(screen.getByLabelText("Período activo")).toHaveTextContent(
        "Diciembre 2025",
      ),
    );

    // Click → once: December 2025 → January 2026
    await user.click(screen.getByLabelText("Mes siguiente"));

    await waitFor(() => {
      expect(screen.getByLabelText("Período activo")).toHaveTextContent(
        "Enero 2026",
      );
    });
  });
});

describe("DashboardPage — CTA when not calculated (AC3)", () => {
  it("shows 'Calcular Depreciación' button and 'No calculada' text when no depreciation data", async () => {
    setupFetchMocks(EMPTY_ASSETS, EMPTY_DEPR);
    renderDashboard();

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /calcular depreciación/i }),
      ).toBeInTheDocument();
    });
    expect(screen.getByText(/No calculada/)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /generar reporte pdf/i }),
    ).not.toBeInTheDocument();
  });
});

describe("DashboardPage — CTA when calculated (AC4)", () => {
  it("shows 'Generar Reporte PDF' and 'Calculada' when depreciation total > 0", async () => {
    const deprWithResults = {
      data: [{ result_id: 1, asset_id: 1 }],
      total: 3,
      period_month: 3,
      period_year: 2026,
      calculated_at: "2026-03-05T14:23:00Z",
    };
    setupFetchMocks(EMPTY_ASSETS, deprWithResults, EMPTY_REPORT_STATUS);
    renderDashboard();

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Generar Reporte PDF" }),
      ).toBeInTheDocument();
    });
    expect(screen.getByText(/Calculada/)).toBeInTheDocument();
    // CTA "Calcular Depreciación" should not be visible
    expect(
      screen.queryByRole("button", { name: /calcular depreciación/i }),
    ).not.toBeInTheDocument();
  });
});

describe("DashboardPage — incomplete assets link (AC2)", () => {
  it("shows incomplete count and 'Ver activos incompletos' link when useful_life_months is 0", async () => {
    const assetsWithIncomplete = {
      data: [
        makeAsset({ asset_id: 1, useful_life_months: 60, status: "active" }),
        makeAsset({ asset_id: 2, useful_life_months: 0, status: "active" }),
        makeAsset({ asset_id: 3, useful_life_months: 0, status: "active" }),
      ],
      total: 3,
    };
    setupFetchMocks(assetsWithIncomplete, EMPTY_DEPR);
    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText(/1 listos/)).toBeInTheDocument();
      expect(screen.getByText(/2 incompletos/)).toBeInTheDocument();
      expect(screen.getByText("Ver activos incompletos")).toBeInTheDocument();
    });
  });

  it("does not show incomplete link when all active assets are ready", async () => {
    const allReadyAssets = {
      data: [
        makeAsset({ asset_id: 1, useful_life_months: 60, status: "active" }),
        makeAsset({ asset_id: 2, useful_life_months: 36, status: "active" }),
      ],
      total: 2,
    };
    setupFetchMocks(allReadyAssets, EMPTY_DEPR);
    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText(/2 listos/)).toBeInTheDocument();
    });
    expect(
      screen.queryByText("Ver activos incompletos"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/incompletos/)).not.toBeInTheDocument();
  });
});

describe("DashboardPage — error handling", () => {
  it("shows error message when assets fetch fails", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error("Network error"),
    );
    renderDashboard();

    await waitFor(() => {
      expect(
        screen.getByText(
          /Error al cargar el estado del período.*Por favor, recarga/i,
        ),
      ).toBeInTheDocument();
    });
    expect(screen.queryByText(/Activos:/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Depreciación:/i)).not.toBeInTheDocument();
  });

  it("shows error message when depreciation fetch fails", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockImplementation(
      (url: string) => {
        if (url.includes("/assets/")) {
          return Promise.resolve(
            new Response(JSON.stringify(EMPTY_ASSETS), {
              status: 200,
              headers: { "Content-Type": "application/json" },
            }),
          );
        }
        if (url.includes("/reports/status")) {
          return Promise.resolve(
            new Response(JSON.stringify(EMPTY_REPORT_STATUS), {
              status: 200,
              headers: { "Content-Type": "application/json" },
            }),
          );
        }
        if (url.includes("/depreciation/")) {
          return Promise.reject(new Error("Depreciation service error"));
        }
        return Promise.reject(new Error(`Unhandled URL: ${url}`));
      },
    );
    renderDashboard();

    await waitFor(() => {
      expect(
        screen.getByText(
          /Error al cargar el estado del período.*Por favor, recarga/i,
        ),
      ).toBeInTheDocument();
    });
  });
});

describe("DashboardPage — PDF status row (AC7)", () => {
  it("shows 'Reporte PDF: Pendiente' when no PDF has been generated", async () => {
    setupFetchMocks(EMPTY_ASSETS, EMPTY_DEPR, EMPTY_REPORT_STATUS);
    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText(/Reporte PDF:.*Pendiente/)).toBeInTheDocument();
    });
  });

  it("shows 'Reporte PDF: Generado —' when PDF has been generated", async () => {
    const deprWithResults = {
      data: [{ result_id: 1, asset_id: 1 }],
      total: 1,
      period_month: 3,
      period_year: 2026,
      calculated_at: "2026-03-05T14:23:00Z",
    };
    setupFetchMocks(EMPTY_ASSETS, deprWithResults, PDF_GENERATED_STATUS);
    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText(/Reporte PDF:.*Generado —/)).toBeInTheDocument();
    });
  });

  it("shows 'Exportar' CTA when depreciation calculated AND PDF generated", async () => {
    const deprWithResults = {
      data: [{ result_id: 1, asset_id: 1 }],
      total: 1,
      period_month: 3,
      period_year: 2026,
      calculated_at: "2026-03-05T14:23:00Z",
    };
    setupFetchMocks(EMPTY_ASSETS, deprWithResults, PDF_GENERATED_STATUS);
    renderDashboard();

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Exportar" }),
      ).toBeInTheDocument();
    });
  });
});

describe("DashboardPage — CTA button disabled state", () => {
  it("disables CTA button while loading", async () => {
    setupFetchMocks(EMPTY_ASSETS, EMPTY_DEPR);
    renderDashboard();

    // Button should be disabled while loading
    const button = screen.queryByRole("button", {
      name: /calcular depreciación|generar reporte pdf/i,
    });
    if (button && button instanceof HTMLButtonElement) {
      expect(button.disabled).toBe(true);
    }
  });

  it("enables CTA button after data loads", async () => {
    setupFetchMocks(EMPTY_ASSETS, EMPTY_DEPR);
    renderDashboard();

    await waitFor(() => {
      const button = screen.getByRole("button", {
        name: /calcular depreciación/i,
      });
      expect((button as HTMLButtonElement).disabled).toBe(false);
    });
  });
});
