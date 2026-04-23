/**
 * Tests for AssetList — asset list with filters and search (Story 2.2).
 *
 * Covers:
 *  - Renders table with correct column headers (AC1)
 *  - Displays asset data in correct columns (AC1)
 *  - Search input filters rows by code/description/category (AC2)
 *  - Status filter shows only matching assets (AC3)
 *  - Category filter shows only matching assets (AC3)
 *  - Filter badges appear and are clearable (AC3)
 *  - Row click navigates to /assets/:id (AC6)
 *  - Loading state shows skeleton (AC1)
 *  - Empty state (no assets) shows CTA (AC1)
 *  - Empty state (filters active) shows clear CTA (AC3)
 *  - Status badges render with correct text (AC4)
 *  - Monetary values displayed in mono font (AC1)
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AssetList from "../features/assets/AssetList";
import { useAppStore } from "../store/appStore";
import type { Asset } from "../types/asset";

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
// Fetch helpers
// ---------------------------------------------------------------------------

function mockFetchResponse(body: unknown, status = 200) {
  (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

function mockFetchError() {
  (globalThis.fetch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
    new Error("Network error"),
  );
}

// ---------------------------------------------------------------------------
// Asset fixtures
// ---------------------------------------------------------------------------

function makeAsset(overrides: Partial<Asset> = {}): Asset {
  return {
    asset_id: 1,
    code: "LAP-001",
    description: "HP Laptop 14 pulgadas",
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

const ASSET_1 = makeAsset({
  asset_id: 1,
  code: "LAP-001",
  description: "HP Laptop",
  category: "Equipos de Cómputo",
  status: "active",
});
const ASSET_2 = makeAsset({
  asset_id: 2,
  code: "MON-001",
  description: "Monitor Samsung",
  category: "Mobiliario",
  status: "in_maintenance",
});
const ASSET_3 = makeAsset({
  asset_id: 3,
  code: "DESK-001",
  description: "Mesa de trabajo",
  category: "Mobiliario",
  status: "retired",
});

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function renderAssetList(initialPath = "/assets") {
  useAppStore.getState().setToken("test-token");
  const queryClient = makeQueryClient();
  return {
    queryClient,
    ...render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[initialPath]}>
          <Routes>
            <Route path="/assets" element={<AssetList />} />
            <Route path="/assets/new" element={<div>New Asset Page</div>} />
            <Route
              path="/assets/:id"
              element={<div data-testid="asset-detail">Asset Detail</div>}
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
  globalThis.fetch = vi.fn();
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AssetList — table headers", () => {
  it("renders all expected column headers", async () => {
    mockFetchResponse({ data: [], total: 0 });
    renderAssetList();
    await waitFor(() => {
      expect(screen.getByText("Código")).toBeInTheDocument();
      expect(screen.getByText("Descripción")).toBeInTheDocument();
      expect(screen.getByText("Categoría")).toBeInTheDocument();
      expect(screen.getByText("Fecha Adquisición")).toBeInTheDocument();
      expect(screen.getByText("Estado")).toBeInTheDocument();
      expect(screen.getByText("Costo Histórico")).toBeInTheDocument();
    });
  });
});

describe("AssetList — data display", () => {
  it("displays asset code, description, category, and date in rows", async () => {
    mockFetchResponse({ data: [ASSET_1], total: 1 });
    renderAssetList();
    await waitFor(() => {
      expect(screen.getByText("LAP-001")).toBeInTheDocument();
      expect(screen.getByText("HP Laptop")).toBeInTheDocument();
      // Category appears in both dropdown and table cell — use getAllByText
      expect(
        screen.getAllByText("Equipos de Cómputo").length,
      ).toBeGreaterThanOrEqual(1);
      // Date displayed as dd/mm/yyyy
      expect(screen.getByText("01/03/2026")).toBeInTheDocument();
    });
  });

  it("displays historical_cost formatted as currency in a monospace element", async () => {
    mockFetchResponse({ data: [ASSET_1], total: 1 });
    renderAssetList();
    await waitFor(() => {
      const costEl = screen.getByText("$1.200,0000");
      expect(costEl).toHaveClass("font-mono");
    });
  });

  it("shows total asset count badge", async () => {
    mockFetchResponse({ data: [ASSET_1, ASSET_2], total: 2 });
    renderAssetList();
    await waitFor(() => {
      expect(screen.getByText("2")).toBeInTheDocument();
    });
  });
});

describe("AssetList — status badges", () => {
  it("renders 'Activo' badge for active status", async () => {
    mockFetchResponse({ data: [makeAsset({ status: "active" })], total: 1 });
    renderAssetList();
    await waitFor(() => {
      expect(screen.getByText("Activo")).toBeInTheDocument();
    });
  });

  it("renders 'En Mantenimiento' badge for in_maintenance status", async () => {
    mockFetchResponse({
      data: [makeAsset({ status: "in_maintenance" })],
      total: 1,
    });
    renderAssetList();
    await waitFor(() => {
      expect(screen.getByText("En Mantenimiento")).toBeInTheDocument();
    });
  });

  it("renders 'Retirado' badge for retired status", async () => {
    mockFetchResponse({ data: [makeAsset({ status: "retired" })], total: 1 });
    renderAssetList();
    await waitFor(() => {
      expect(screen.getByText("Retirado")).toBeInTheDocument();
    });
  });
});

describe("AssetList — search (AC2)", () => {
  it("filters rows by search input matching code", async () => {
    mockFetchResponse({ data: [ASSET_1, ASSET_2], total: 2 });
    renderAssetList();
    const user = userEvent.setup();

    await waitFor(() => screen.getByText("LAP-001"));

    const searchInput = screen.getByPlaceholderText(/buscar por código/i);
    await user.type(searchInput, "MON");

    await waitFor(() => {
      expect(screen.queryByText("LAP-001")).not.toBeInTheDocument();
      expect(screen.getByText("MON-001")).toBeInTheDocument();
    });
  });

  it("filters rows by search input matching description", async () => {
    mockFetchResponse({ data: [ASSET_1, ASSET_2], total: 2 });
    renderAssetList();
    const user = userEvent.setup();

    await waitFor(() => screen.getByText("LAP-001"));

    const searchInput = screen.getByPlaceholderText(/buscar por código/i);
    await user.type(searchInput, "Samsung");

    await waitFor(() => {
      expect(screen.queryByText("LAP-001")).not.toBeInTheDocument();
      expect(screen.getByText("MON-001")).toBeInTheDocument();
    });
  });

  it("shows clear (×) button when search has text", async () => {
    mockFetchResponse({ data: [ASSET_1], total: 1 });
    renderAssetList();
    const user = userEvent.setup();

    await waitFor(() => screen.getByText("LAP-001"));
    const searchInput = screen.getByPlaceholderText(/buscar por código/i);
    await user.type(searchInput, "LAP");

    expect(screen.getByLabelText("Limpiar búsqueda")).toBeInTheDocument();
  });
});

describe("AssetList — status filter (AC3)", () => {
  it("shows only assets matching selected status", async () => {
    mockFetchResponse({ data: [ASSET_1, ASSET_2], total: 2 });
    renderAssetList();
    const user = userEvent.setup();

    await waitFor(() => screen.getByText("LAP-001"));

    const statusSelect = screen.getByLabelText("Filtrar por estado");
    await user.selectOptions(statusSelect, "active");

    await waitFor(() => {
      expect(screen.getByText("LAP-001")).toBeInTheDocument();
      expect(screen.queryByText("MON-001")).not.toBeInTheDocument();
    });
  });
});

describe("AssetList — category filter (AC3)", () => {
  it("shows only assets matching selected category", async () => {
    mockFetchResponse({ data: [ASSET_1, ASSET_2], total: 2 });
    renderAssetList();
    const user = userEvent.setup();

    await waitFor(() => screen.getByText("LAP-001"));

    const categorySelect = screen.getByLabelText("Filtrar por categoría");
    await user.selectOptions(categorySelect, "Mobiliario");

    await waitFor(() => {
      expect(screen.queryByText("LAP-001")).not.toBeInTheDocument();
      expect(screen.getByText("MON-001")).toBeInTheDocument();
    });
  });

  it("populates category dropdown with unique categories from data", async () => {
    mockFetchResponse({ data: [ASSET_1, ASSET_2, ASSET_3], total: 3 });
    renderAssetList();

    await waitFor(() => screen.getByText("LAP-001"));

    const categorySelect = screen.getByLabelText("Filtrar por categoría");
    expect(categorySelect).toBeInTheDocument();
    // Both categories should appear as options
    expect(categorySelect.innerHTML).toContain("Equipos de Cómputo");
    expect(categorySelect.innerHTML).toContain("Mobiliario");
  });
});

describe("AssetList — filter badges (AC3)", () => {
  it("shows status filter badge when status filter is active", async () => {
    mockFetchResponse({ data: [ASSET_1, ASSET_2], total: 2 });
    renderAssetList();
    const user = userEvent.setup();

    await waitFor(() => screen.getByText("LAP-001"));

    const statusSelect = screen.getByLabelText("Filtrar por estado");
    await user.selectOptions(statusSelect, "active");

    await waitFor(() => {
      expect(screen.getByText(/Estado:/)).toBeInTheDocument();
    });
  });

  it("clears status filter when badge × is clicked", async () => {
    mockFetchResponse({ data: [ASSET_1, ASSET_2], total: 2 });
    renderAssetList();
    const user = userEvent.setup();

    await waitFor(() => screen.getByText("LAP-001"));

    await user.selectOptions(
      screen.getByLabelText("Filtrar por estado"),
      "active",
    );
    await waitFor(() => screen.getByLabelText("Quitar filtro de estado"));

    await user.click(screen.getByLabelText("Quitar filtro de estado"));

    // Both assets should be visible again
    await waitFor(() => {
      expect(screen.getByText("LAP-001")).toBeInTheDocument();
      expect(screen.getByText("MON-001")).toBeInTheDocument();
    });
  });

  it("shows 'Limpiar filtros' button when any filter is active", async () => {
    mockFetchResponse({ data: [ASSET_1], total: 1 });
    renderAssetList();
    const user = userEvent.setup();

    await waitFor(() => screen.getByText("LAP-001"));
    await user.selectOptions(
      screen.getByLabelText("Filtrar por estado"),
      "active",
    );

    await waitFor(() => {
      expect(screen.getByText("Limpiar filtros")).toBeInTheDocument();
    });
  });
});

describe("AssetList — row click navigation (AC6)", () => {
  it("navigates to /assets/:id when a row is clicked", async () => {
    mockFetchResponse({ data: [ASSET_1], total: 1 });
    renderAssetList();
    const user = userEvent.setup();

    await waitFor(() => screen.getByText("LAP-001"));
    await user.click(screen.getByText("LAP-001"));

    await waitFor(() => {
      expect(screen.getByTestId("asset-detail")).toBeInTheDocument();
    });
  });
});

describe("AssetList — loading state", () => {
  it("shows skeleton rows while loading", () => {
    // Never resolves — stays loading
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockImplementation(
      () => new Promise(() => {}),
    );
    const { container } = renderAssetList();

    const skeletons = container.querySelectorAll(".animate-pulse");
    expect(skeletons.length).toBeGreaterThan(0);
  });
});

describe("AssetList — empty states", () => {
  it("shows empty state CTA when no assets registered", async () => {
    mockFetchResponse({ data: [], total: 0 });
    renderAssetList();

    await waitFor(() => {
      expect(
        screen.getByText("Aún no has registrado activos."),
      ).toBeInTheDocument();
      expect(screen.getByText("+ Registrar primer activo")).toBeInTheDocument();
    });
  });

  it("shows 'no results' empty state when filters are active but nothing matches", async () => {
    mockFetchResponse({ data: [ASSET_1], total: 1 });
    renderAssetList();
    const user = userEvent.setup();

    await waitFor(() => screen.getByText("LAP-001"));

    // Filter by retired status — ASSET_1 is active, no match
    await user.selectOptions(
      screen.getByLabelText("Filtrar por estado"),
      "retired",
    );

    await waitFor(() => {
      expect(
        screen.getByText(
          "No se encontraron activos con los filtros aplicados.",
        ),
      ).toBeInTheDocument();
      // "Limpiar filtros" appears in both badge area and empty state — at least 2
      expect(
        screen.getAllByText("Limpiar filtros").length,
      ).toBeGreaterThanOrEqual(2);
    });
  });
});

describe("AssetList — error state", () => {
  it("shows error message with retry button on fetch failure", async () => {
    mockFetchError();
    renderAssetList();

    await waitFor(() => {
      expect(
        screen.getByText(/No se pudieron cargar los activos/),
      ).toBeInTheDocument();
      expect(screen.getByText("Reintentar")).toBeInTheDocument();
    });
  });
});

describe("AssetList — page header", () => {
  it("shows page title 'Activos'", async () => {
    mockFetchResponse({ data: [], total: 0 });
    renderAssetList();

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Activos" }),
      ).toBeInTheDocument();
    });
  });

  it("shows '+ Nuevo Activo' button that navigates to /assets/new", async () => {
    mockFetchResponse({ data: [], total: 0 });
    renderAssetList();
    const user = userEvent.setup();

    await waitFor(() => screen.getByText("+ Nuevo Activo"));
    await user.click(screen.getByText("+ Nuevo Activo"));

    await waitFor(() => {
      expect(screen.getByText("New Asset Page")).toBeInTheDocument();
    });
  });
});

describe("AssetList — column sorting", () => {
  it("sorts by code column when header is clicked", async () => {
    const assetA = makeAsset({
      asset_id: 1,
      code: "AAA-001",
      acquisition_date: "2026-01-01",
    });
    const assetB = makeAsset({
      asset_id: 2,
      code: "ZZZ-001",
      acquisition_date: "2026-02-01",
    });
    mockFetchResponse({ data: [assetB, assetA], total: 2 });
    renderAssetList();
    const user = userEvent.setup();

    await waitFor(() => screen.getByText("ZZZ-001"));

    // Click "Código" header to sort ascending
    await user.click(screen.getByText("Código"));

    await waitFor(() => {
      const rows = screen.getAllByRole("link");
      const codes = rows.map((row) => row.textContent);
      // AAA-001 should appear before ZZZ-001 in ascending sort
      const aaaIndex = codes.findIndex((t) => t?.includes("AAA-001"));
      const zzzIndex = codes.findIndex((t) => t?.includes("ZZZ-001"));
      expect(aaaIndex).toBeLessThan(zzzIndex);
    });
  });
});

describe("AssetList — keyboard navigation", () => {
  it("navigates to asset detail on Enter key press on a row", async () => {
    mockFetchResponse({ data: [ASSET_1], total: 1 });
    renderAssetList();
    const user = userEvent.setup();

    await waitFor(() => screen.getByText("LAP-001"));

    const row = screen.getByRole("link");
    row.focus();
    await user.keyboard("{Enter}");

    await waitFor(() => {
      expect(screen.getByTestId("asset-detail")).toBeInTheDocument();
    });
  });
});
