/**
 * Tests for AssetDetail — asset profile, edit form, and audit history (Story 2.3).
 *
 * Covers:
 *  - View mode renders all asset fields with correct values (AC1)
 *  - Status badge renders with correct color class (AC1)
 *  - "Editar" button switches to edit mode with pre-populated values (AC2)
 *  - Edit form "Cancelar" reverts to view mode (AC2)
 *  - "Guardar Cambios" triggers PATCH mutation; success shows view mode (AC3)
 *  - Audit history section renders entries in reverse-chronological order (AC5)
 *  - Empty audit history state (AC5)
 *  - Loading skeleton renders while data is loading (AC1)
 *  - Error state renders with retry button (AC1)
 *  - Back navigation button navigates to /assets (AC1)
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AssetDetail from "../features/assets/AssetDetail";
import { useAppStore } from "../store/appStore";
import type { Asset, AuditLogEntry } from "../types/asset";

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
// Fixtures
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
    created_at: "2026-03-09T14:00:00Z",
    updated_at: "2026-03-09T14:00:00Z",
    // import fields — null by default (Story 8.5)
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

function makeAuditEntry(overrides: Partial<AuditLogEntry> = {}): AuditLogEntry {
  return {
    log_id: 1,
    timestamp: "2026-03-09T14:00:00Z",
    actor: "Test Corp",
    entity_type: "asset",
    entity_id: 1,
    action: "CREATE",
    field: null,
    old_value: null,
    new_value: null,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function renderAssetDetail(assetId = 1) {
  useAppStore.getState().setToken("test-token");
  const queryClient = makeQueryClient();
  return {
    queryClient,
    ...render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[`/assets/${assetId}`]}>
          <Routes>
            <Route
              path="/assets"
              element={<div data-testid="asset-list">Asset List</div>}
            />
            <Route path="/assets/:id" element={<AssetDetail />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    ),
  };
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  globalThis.fetch = vi.fn();
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Helper: mock both asset + audit fetch calls
// ---------------------------------------------------------------------------

function mockAssetAndAudit(asset: Asset, auditEntries: AuditLogEntry[] = []) {
  // First fetch = GET /assets/<id>/
  mockFetchResponse({ data: asset });
  // Second fetch = GET /audit/?entity_type=asset&entity_id=<id>
  mockFetchResponse({ data: auditEntries, total: auditEntries.length });
}

// ---------------------------------------------------------------------------
// View mode tests
// ---------------------------------------------------------------------------

describe("AssetDetail — view mode", () => {
  it("renders loading skeleton initially (AC1)", () => {
    mockAssetAndAudit(makeAsset());
    renderAssetDetail();
    // Asset fields not yet visible
    expect(screen.queryByText("LAP-001")).not.toBeInTheDocument();
    // Skeleton pulse elements are present
    const pulseElements = document.querySelectorAll(".animate-pulse");
    expect(pulseElements.length).toBeGreaterThan(0);
  });

  it("renders asset fields after load (AC1)", async () => {
    const asset = makeAsset();
    mockAssetAndAudit(asset);
    renderAssetDetail();

    await waitFor(() =>
      expect(screen.getAllByText("LAP-001").length).toBeGreaterThan(0),
    );
    // description appears in header and in profile section
    expect(
      screen.getAllByText("HP Laptop 14 pulgadas").length,
    ).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Equipos de Cómputo")).toBeInTheDocument();
    expect(screen.getByText("60 meses")).toBeInTheDocument();
    // Date displayed as dd/mm/yyyy
    expect(screen.getByText("01/03/2026")).toBeInTheDocument();
    // Depreciation method label
    expect(screen.getByText("Lineal")).toBeInTheDocument();
  });

  it("renders monetary values (AC1)", async () => {
    mockAssetAndAudit(makeAsset());
    renderAssetDetail();

    await waitFor(() =>
      expect(screen.getAllByText("LAP-001").length).toBeGreaterThan(0),
    );
    expect(screen.getByText("1200.0000")).toBeInTheDocument();
    expect(screen.getByText("120.0000")).toBeInTheDocument();
  });

  it("renders active status badge with correct class (AC1)", async () => {
    mockAssetAndAudit(makeAsset({ status: "active" }));
    renderAssetDetail();

    await waitFor(() => screen.getByText("Activo"));
    const badge = screen.getByText("Activo");
    expect(badge.className).toContain("text-[#98971a]");
  });

  it("renders in_maintenance status badge (AC1)", async () => {
    mockAssetAndAudit(makeAsset({ status: "in_maintenance" }));
    renderAssetDetail();

    await waitFor(() => screen.getByText("En Mantenimiento"));
    const badge = screen.getByText("En Mantenimiento");
    expect(badge.className).toContain("text-[#d79921]");
  });

  it("renders retired status badge (AC1)", async () => {
    mockAssetAndAudit(makeAsset({ status: "retired" }));
    renderAssetDetail();

    await waitFor(() => screen.getByText("Retirado"));
    const badge = screen.getByText("Retirado");
    expect(badge.className).toContain("text-[#7c6f64]");
  });

  it("renders error state with retry button when fetch fails (AC1)", async () => {
    mockFetchError(); // asset fetch fails
    mockFetchError(); // audit fetch also fails (may or may not be called)
    renderAssetDetail();

    await waitFor(() => screen.getByText("Reintentar"));
    expect(screen.getByText(/No se pudo cargar el activo/)).toBeInTheDocument();
  });

  it("back navigation button navigates to /assets (AC1)", async () => {
    mockAssetAndAudit(makeAsset());
    renderAssetDetail();

    await waitFor(() => screen.getAllByText("LAP-001").length > 0);
    const backBtn = screen.getByText("← Activos");
    await userEvent.click(backBtn);

    expect(screen.getByTestId("asset-list")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Audit history tests
// ---------------------------------------------------------------------------

describe("AssetDetail — audit history (AC5)", () => {
  it("renders empty state when no audit entries", async () => {
    mockAssetAndAudit(makeAsset(), []);
    renderAssetDetail();

    await waitFor(() =>
      screen.getByText("Aún no hay cambios registrados para este activo."),
    );
  });

  it("renders audit entries in reverse-chronological order", async () => {
    const entries = [
      makeAuditEntry({
        log_id: 2,
        action: "UPDATE",
        field: "description",
        old_value: "Old",
        new_value: "New",
        timestamp: "2026-03-10T15:00:00Z",
      }),
      makeAuditEntry({
        log_id: 1,
        action: "CREATE",
        timestamp: "2026-03-09T14:00:00Z",
      }),
    ];
    mockAssetAndAudit(makeAsset(), entries);
    renderAssetDetail();

    await waitFor(() => screen.getAllByText("Edición").length > 0);
    const rows = screen.getAllByRole("row");
    // First data row (after header) should be the most recent (UPDATE)
    expect(rows[1]).toHaveTextContent("Edición");
    expect(rows[2]).toHaveTextContent("Creación");
  });

  it("renders field, old_value, new_value in audit entry", async () => {
    const entries = [
      makeAuditEntry({
        log_id: 1,
        action: "UPDATE",
        field: "description",
        old_value: "Viejo valor",
        new_value: "Nuevo valor",
      }),
    ];
    mockAssetAndAudit(makeAsset(), entries);
    renderAssetDetail();

    await waitFor(() => screen.getByText("description"));
    expect(screen.getByText("Viejo valor")).toBeInTheDocument();
    expect(screen.getByText("Nuevo valor")).toBeInTheDocument();
  });

  it("renders — for null field/values in CREATE entry", async () => {
    const entries = [
      makeAuditEntry({
        action: "CREATE",
        field: null,
        old_value: null,
        new_value: null,
      }),
    ];
    mockAssetAndAudit(makeAsset(), entries);
    renderAssetDetail();

    await waitFor(() => screen.getByText("Creación"));
    // Three "—" cells: field, old_value, new_value
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThanOrEqual(3);
  });
});

// ---------------------------------------------------------------------------
// Edit mode tests
// ---------------------------------------------------------------------------

describe("AssetDetail — edit mode (AC2, AC3)", () => {
  it('"Editar" button switches to edit mode with pre-populated values (AC2)', async () => {
    const asset = makeAsset();
    mockAssetAndAudit(asset);
    renderAssetDetail();

    await waitFor(() => screen.getAllByText("LAP-001").length > 0);
    await userEvent.click(screen.getByRole("button", { name: "Editar" }));

    // Edit form is shown
    expect(screen.getByText("Editar Activo")).toBeInTheDocument();
    // Fields pre-populated
    expect(
      (screen.getByLabelText(/^Código \*/i) as HTMLInputElement).value,
    ).toBe("LAP-001");
    expect(
      (screen.getByLabelText(/Descripción/i) as HTMLInputElement).value,
    ).toBe("HP Laptop 14 pulgadas");
  });

  it('"Cancelar" reverts to view mode without saving (AC2)', async () => {
    const asset = makeAsset();
    mockAssetAndAudit(asset);
    renderAssetDetail();

    await waitFor(() => screen.getAllByText("LAP-001").length > 0);
    await userEvent.click(screen.getByRole("button", { name: "Editar" }));
    expect(screen.getByText("Editar Activo")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    // Back to view mode
    expect(screen.queryByText("Editar Activo")).not.toBeInTheDocument();
    expect(screen.getAllByText("LAP-001").length).toBeGreaterThan(0);
  });

  it('"Cancelar" on dirty form shows confirm and stays in edit mode when denied (AC2)', async () => {
    const asset = makeAsset();
    mockAssetAndAudit(asset);
    renderAssetDetail();

    await waitFor(() => screen.getAllByText("LAP-001").length > 0);
    await userEvent.click(screen.getByRole("button", { name: "Editar" }));

    // Dirty the form
    const descInput = screen.getByLabelText(/Descripción/i);
    await userEvent.clear(descInput);
    await userEvent.type(descInput, "Valor modificado");

    // Deny the confirm dialog — should stay in edit mode
    vi.spyOn(window, "confirm").mockReturnValue(false);
    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(window.confirm).toHaveBeenCalledWith(
      "¿Descartar cambios? Los datos ingresados se perderán.",
    );
    expect(screen.getByText("Editar Activo")).toBeInTheDocument();
  });

  it('"Cancelar" on dirty form discards changes when confirm is accepted (AC2)', async () => {
    const asset = makeAsset();
    mockAssetAndAudit(asset);
    renderAssetDetail();

    await waitFor(() => screen.getAllByText("LAP-001").length > 0);
    await userEvent.click(screen.getByRole("button", { name: "Editar" }));

    // Dirty the form
    const descInput = screen.getByLabelText(/Descripción/i);
    await userEvent.clear(descInput);
    await userEvent.type(descInput, "Valor modificado");

    // Accept the confirm dialog — should return to view mode
    vi.spyOn(window, "confirm").mockReturnValue(true);
    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(window.confirm).toHaveBeenCalled();
    expect(screen.queryByText("Editar Activo")).not.toBeInTheDocument();
    expect(screen.getAllByText("LAP-001").length).toBeGreaterThan(0);
  });

  it('"Guardar Cambios" calls PATCH and returns to view mode on success (AC3)', async () => {
    const asset = makeAsset();
    const updatedAsset = makeAsset({ description: "HP Laptop 15 pulgadas" });
    mockAssetAndAudit(asset);
    renderAssetDetail();

    await waitFor(() => screen.getAllByText("LAP-001").length > 0);
    await userEvent.click(screen.getByRole("button", { name: "Editar" }));

    // Change description
    const descInput = screen.getByLabelText(/Descripción/i);
    await userEvent.clear(descInput);
    await userEvent.type(descInput, "HP Laptop 15 pulgadas");

    // Mock PATCH response + refetch responses
    mockFetchResponse({ data: updatedAsset }); // PATCH
    mockFetchResponse({ data: updatedAsset }); // refetch asset
    mockFetchResponse({ data: [], total: 0 }); // refetch audit

    await userEvent.click(
      screen.getByRole("button", { name: "Guardar Cambios" }),
    );

    await waitFor(() =>
      expect(screen.queryByText("Editar Activo")).not.toBeInTheDocument(),
    );
  });

  it("shows validation error when required field is empty (AC2)", async () => {
    const asset = makeAsset();
    mockAssetAndAudit(asset);
    renderAssetDetail();

    await waitFor(() => screen.getAllByText("LAP-001").length > 0);
    await userEvent.click(screen.getByRole("button", { name: "Editar" }));

    // Clear code field and submit
    const codeInput = screen.getByLabelText(/^Código \*/i);
    await userEvent.clear(codeInput);
    await userEvent.click(
      screen.getByRole("button", { name: "Guardar Cambios" }),
    );

    await waitFor(() =>
      screen.getByText("El código del activo es obligatorio"),
    );
  });
});

// ---------------------------------------------------------------------------
// Retire flow tests
// ---------------------------------------------------------------------------

describe("AssetDetail — retire flow (AC1, AC3, AC7)", () => {
  it('"Dar de Baja" button is visible for active asset (AC1)', async () => {
    mockAssetAndAudit(makeAsset({ status: "active" }));
    renderAssetDetail();

    await waitFor(() => screen.getAllByText("LAP-001").length > 0);
    expect(
      screen.getByRole("button", { name: "Dar de Baja" }),
    ).toBeInTheDocument();
  });

  it('"Dar de Baja" button is NOT visible for retired asset (AC3)', async () => {
    mockAssetAndAudit(
      makeAsset({ status: "retired", retirement_date: "2026-03-15" }),
    );
    renderAssetDetail();

    await waitFor(() => screen.getByText("Retirado"));
    expect(
      screen.queryByRole("button", { name: "Dar de Baja" }),
    ).not.toBeInTheDocument();
  });

  it("clicking Dar de Baja shows retire form with date input and action buttons", async () => {
    mockAssetAndAudit(makeAsset({ status: "active" }));
    renderAssetDetail();

    await waitFor(() => screen.getAllByText("LAP-001").length > 0);
    await userEvent.click(screen.getByRole("button", { name: "Dar de Baja" }));

    expect(screen.getByText("Dar de Baja al Activo")).toBeInTheDocument();
    expect(screen.getByLabelText(/Fecha de Baja/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Confirmar Baja" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Cancelar" }),
    ).toBeInTheDocument();
  });

  it('"Cancelar" in retire mode hides form without API call', async () => {
    mockAssetAndAudit(makeAsset({ status: "active" }));
    renderAssetDetail();

    await waitFor(() => screen.getAllByText("LAP-001").length > 0);
    await userEvent.click(screen.getByRole("button", { name: "Dar de Baja" }));
    expect(screen.getByText("Dar de Baja al Activo")).toBeInTheDocument();

    // Clear mock call count tracking
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockClear();

    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(screen.queryByText("Dar de Baja al Activo")).not.toBeInTheDocument();
    // No additional fetch calls made
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('"Confirmar Baja" calls POST retire and shows Retirado badge on success', async () => {
    const asset = makeAsset({ status: "active" });
    const retiredAsset = makeAsset({
      status: "retired",
      retirement_date: "2026-03-15",
    });
    mockAssetAndAudit(asset);
    renderAssetDetail();

    await waitFor(() => screen.getAllByText("LAP-001").length > 0);
    await userEvent.click(screen.getByRole("button", { name: "Dar de Baja" }));

    // Mock POST /retire response + refetch responses
    mockFetchResponse({ data: retiredAsset }); // POST retire
    mockFetchResponse({ data: retiredAsset }); // refetch asset
    mockFetchResponse({ data: [], total: 0 }); // refetch audit

    await userEvent.click(
      screen.getByRole("button", { name: "Confirmar Baja" }),
    );

    await waitFor(() =>
      expect(
        screen.queryByText("Dar de Baja al Activo"),
      ).not.toBeInTheDocument(),
    );
  });

  it("retire 409 error shows retireError message inline", async () => {
    mockAssetAndAudit(makeAsset({ status: "active" }));
    renderAssetDetail();

    await waitFor(() => screen.getAllByText("LAP-001").length > 0);
    await userEvent.click(screen.getByRole("button", { name: "Dar de Baja" }));

    // Mock 409 response
    mockFetchResponse(
      {
        error: "CONFLICT",
        message:
          "El activo tiene un evento de mantenimiento abierto. Ciérralo antes de dar de baja.",
      },
      409,
    );

    await userEvent.click(
      screen.getByRole("button", { name: "Confirmar Baja" }),
    );

    await waitFor(() => screen.getByText(/Ciérralo antes de dar de baja/));
  });

  it('"Fecha de Baja" row shown in Estado section for retired asset (AC7)', async () => {
    mockAssetAndAudit(
      makeAsset({ status: "retired", retirement_date: "2026-03-15" }),
    );
    renderAssetDetail();

    await waitFor(() => screen.getByText("Retirado"));
    expect(screen.getByText("Fecha de baja")).toBeInTheDocument();
    expect(screen.getByText("15/03/2026")).toBeInTheDocument();
  });

  it('"Fecha de Baja" row NOT shown for active asset (AC7)', async () => {
    mockAssetAndAudit(makeAsset({ status: "active", retirement_date: null }));
    renderAssetDetail();

    await waitFor(() => screen.getAllByText("LAP-001").length > 0);
    expect(screen.queryByText("Fecha de baja")).not.toBeInTheDocument();
  });

  it('clicking "Editar" while retire form is open clears retire form (M1 guard)', async () => {
    mockAssetAndAudit(makeAsset({ status: "active" }));
    renderAssetDetail();

    await waitFor(() => screen.getAllByText("LAP-001").length > 0);
    // Open retire form
    await userEvent.click(screen.getByRole("button", { name: "Dar de Baja" }));
    expect(screen.getByText("Dar de Baja al Activo")).toBeInTheDocument();

    // Click Editar — switches to edit mode, retire form disappears
    await userEvent.click(screen.getByRole("button", { name: "Editar" }));
    expect(screen.queryByText("Dar de Baja al Activo")).not.toBeInTheDocument();

    // Cancel edit — returns to view mode; retire form must NOT reappear
    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(screen.queryByText("Dar de Baja al Activo")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Delete flow tests
// ---------------------------------------------------------------------------

describe("AssetDetail — delete flow (AC5, AC6, AC8)", () => {
  it('clicking "Eliminar" shows inline confirmation without making API call', async () => {
    mockAssetAndAudit(makeAsset({ status: "active" }));
    renderAssetDetail();

    await waitFor(() => screen.getAllByText("LAP-001").length > 0);

    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockClear();

    await userEvent.click(screen.getByRole("button", { name: "Eliminar" }));

    expect(
      screen.getByText(
        "¿Confirmas eliminar este activo? Esta acción no se puede deshacer.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Sí, eliminar" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Cancelar" }),
    ).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('"Cancelar" in delete confirm hides confirmation without DELETE call', async () => {
    mockAssetAndAudit(makeAsset({ status: "active" }));
    renderAssetDetail();

    await waitFor(() => screen.getAllByText("LAP-001").length > 0);

    await userEvent.click(screen.getByRole("button", { name: "Eliminar" }));
    expect(
      screen.getByText(
        "¿Confirmas eliminar este activo? Esta acción no se puede deshacer.",
      ),
    ).toBeInTheDocument();

    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockClear();

    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(
      screen.queryByText(
        "¿Confirmas eliminar este activo? Esta acción no se puede deshacer.",
      ),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Eliminar" }),
    ).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('"Sí, eliminar" calls DELETE and navigates to /assets on success', async () => {
    mockAssetAndAudit(makeAsset({ status: "active" }));
    renderAssetDetail();

    await waitFor(() => screen.getAllByText("LAP-001").length > 0);

    await userEvent.click(screen.getByRole("button", { name: "Eliminar" }));

    // Mock 204 response (empty body)
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(null, { status: 204 }),
    );
    mockFetchResponse({ data: [], total: 0 }); // refetch assets list after invalidation

    await userEvent.click(screen.getByRole("button", { name: "Sí, eliminar" }));

    await waitFor(() => screen.getByTestId("asset-list"));
  });

  it("delete 409 error shows deleteError inline in confirm box", async () => {
    mockAssetAndAudit(makeAsset({ status: "active" }));
    renderAssetDetail();

    await waitFor(() => screen.getAllByText("LAP-001").length > 0);

    await userEvent.click(screen.getByRole("button", { name: "Eliminar" }));

    mockFetchResponse(
      {
        error: "CONFLICT",
        message:
          "No se puede eliminar el activo porque tiene historial asociado.",
      },
      409,
    );

    await userEvent.click(screen.getByRole("button", { name: "Sí, eliminar" }));

    await waitFor(() => screen.getByText(/No se puede eliminar el activo/));
  });

  it('"Eliminar" button NOT visible for retired asset', async () => {
    mockAssetAndAudit(
      makeAsset({ status: "retired", retirement_date: "2026-03-15" }),
    );
    renderAssetDetail();

    await waitFor(() => screen.getByText("Retirado"));
    expect(
      screen.queryByRole("button", { name: "Eliminar" }),
    ).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Story 8.5 — Import section view mode tests
// ---------------------------------------------------------------------------

describe("AssetDetail — import section (view mode)", () => {
  it("shows 'Datos de Importación / Contables' toggle button (AC1)", async () => {
    mockAssetAndAudit(makeAsset());
    renderAssetDetail();
    await waitFor(() => screen.getAllByText("LAP-001").length > 0);
    expect(
      screen.getByRole("button", { name: /Datos de Importación \/ Contables/i }),
    ).toBeInTheDocument();
  });

  it("import section expands on click and shows field rows (AC1)", async () => {
    mockAssetAndAudit(makeAsset());
    renderAssetDetail();
    await waitFor(() => screen.getAllByText("LAP-001").length > 0);

    const toggleBtn = screen.getByRole("button", {
      name: /Datos de Importación \/ Contables/i,
    });
    await userEvent.click(toggleBtn);

    expect(screen.getByText("Depreciación Acumulada al Importar")).toBeInTheDocument();
    expect(screen.getByText("Adiciones y Mejoras")).toBeInTheDocument();
    expect(screen.getByText("Código Contable (PUC)")).toBeInTheDocument();
    expect(screen.getByText("Centro de Costo")).toBeInTheDocument();
    expect(screen.getByText("Proveedor")).toBeInTheDocument();
    expect(screen.getByText("Factura")).toBeInTheDocument();
    expect(screen.getByText("Ubicación")).toBeInTheDocument();
    expect(screen.getByText("Características")).toBeInTheDocument();
  });

  it("shows dashes for native asset with no import fields (AC1)", async () => {
    mockAssetAndAudit(makeAsset()); // all import fields null
    renderAssetDetail();
    await waitFor(() => screen.getAllByText("LAP-001").length > 0);

    const toggleBtn = screen.getByRole("button", {
      name: /Datos de Importación \/ Contables/i,
    });
    await userEvent.click(toggleBtn);

    // After expanding, fields with null show "—"
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThanOrEqual(8);
  });

  it("shows import field values for an imported asset (AC1)", async () => {
    mockAssetAndAudit(
      makeAsset({
        imported_accumulated_depreciation: "50000.0000",
        accounting_code: "1524",
        supplier: "Proveedor SA",
      }),
    );
    renderAssetDetail();
    await waitFor(() => screen.getAllByText("LAP-001").length > 0);

    const toggleBtn = screen.getByRole("button", {
      name: /Datos de Importación \/ Contables/i,
    });
    await userEvent.click(toggleBtn);

    expect(screen.getByText("50000.0000")).toBeInTheDocument();
    expect(screen.getByText("1524")).toBeInTheDocument();
    expect(screen.getByText("Proveedor SA")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Story 8.5 — Import section edit mode tests
// ---------------------------------------------------------------------------

describe("AssetDetail — import section (edit mode)", () => {
  it("shows import section heading in edit form (AC2)", async () => {
    mockAssetAndAudit(makeAsset());
    renderAssetDetail();
    await waitFor(() => screen.getAllByText("LAP-001").length > 0);

    await userEvent.click(screen.getByRole("button", { name: "Editar" }));

    expect(
      screen.getByRole("heading", { name: "Datos de Importación / Contables" }),
    ).toBeInTheDocument();
  });

  it("shows impact warning text for imported_accumulated_depreciation (AC3)", async () => {
    mockAssetAndAudit(makeAsset());
    renderAssetDetail();
    await waitFor(() => screen.getAllByText("LAP-001").length > 0);

    await userEvent.click(screen.getByRole("button", { name: "Editar" }));

    expect(
      screen.getByText(/Modificar este valor recalculará el valor en libros/i),
    ).toBeInTheDocument();
  });

  it("shows impact warning text for additions_improvements (AC3)", async () => {
    mockAssetAndAudit(makeAsset());
    renderAssetDetail();
    await waitFor(() => screen.getAllByText("LAP-001").length > 0);

    await userEvent.click(screen.getByRole("button", { name: "Editar" }));

    expect(
      screen.getByText(/Modificar afecta la base depreciable/i),
    ).toBeInTheDocument();
  });

  it("cross-field validation blocks save when IAD > effective_cost (AC5)", async () => {
    mockAssetAndAudit(makeAsset({ historical_cost: "100000.0000" }));
    renderAssetDetail();
    await waitFor(() => screen.getAllByText("LAP-001").length > 0);

    await userEvent.click(screen.getByRole("button", { name: "Editar" }));

    const iadInput = screen.getByLabelText("Depreciación Acumulada al Importar");
    await userEvent.clear(iadInput);
    await userEvent.type(iadInput, "200000");
    // trigger blur to show error
    await userEvent.tab();

    await waitFor(() => {
      expect(
        screen.getByText(/No puede superar el costo efectivo/i),
      ).toBeInTheDocument();
    });
  });

  it("triggers confirm dialog when IAD is changed on submit (AC4)", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    mockAssetAndAudit(makeAsset({ historical_cost: "100000.0000" }));
    renderAssetDetail();
    await waitFor(() => screen.getAllByText("LAP-001").length > 0);

    await userEvent.click(screen.getByRole("button", { name: "Editar" }));

    const iadInput = screen.getByLabelText("Depreciación Acumulada al Importar");
    await userEvent.clear(iadInput);
    await userEvent.type(iadInput, "5000");

    await userEvent.click(
      screen.getByRole("button", { name: "Guardar Cambios" }),
    );

    expect(confirmSpy).toHaveBeenCalledWith(
      expect.stringContaining("afectan los cálculos de depreciación"),
    );
    confirmSpy.mockRestore();
  });

  it("does NOT trigger confirm dialog for text-only import field changes (AC4)", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    const updatedAsset = makeAsset({ accounting_code: "1524" });
    mockAssetAndAudit(makeAsset());
    renderAssetDetail();
    await waitFor(() => screen.getAllByText("LAP-001").length > 0);

    await userEvent.click(screen.getByRole("button", { name: "Editar" }));

    const acInput = screen.getByLabelText("Código Contable (PUC)");
    await userEvent.type(acInput, "1524");

    // Mock PATCH + refetch
    mockFetchResponse({ data: updatedAsset });
    mockFetchResponse({ data: updatedAsset });
    mockFetchResponse({ data: [], total: 0 });

    await userEvent.click(
      screen.getByRole("button", { name: "Guardar Cambios" }),
    );

    // confirm should NOT have been called (text-only field change)
    expect(confirmSpy).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });
});

// ---------------------------------------------------------------------------
// Story 8.5 — TERRENOS (method="none") display tests
// ---------------------------------------------------------------------------

describe("AssetDetail — TERRENOS (method=none)", () => {
  it('shows "Sin Depreciación (Terrenos)" as method label in view mode (AC7)', async () => {
    mockAssetAndAudit(
      makeAsset({
        depreciation_method: "none",
        useful_life_months: 0,
      }),
    );
    renderAssetDetail();
    await waitFor(() => screen.getAllByText("LAP-001").length > 0);

    expect(
      screen.getByText("Sin Depreciación (Terrenos)"),
    ).toBeInTheDocument();
  });

  it("TERRENOS edit form shows 'none' option in method select (AC7)", async () => {
    mockAssetAndAudit(
      makeAsset({ depreciation_method: "none", useful_life_months: 0 }),
    );
    renderAssetDetail();
    await waitFor(() => screen.getAllByText("LAP-001").length > 0);

    await userEvent.click(screen.getByRole("button", { name: "Editar" }));

    const select = screen.getByLabelText(/Método de Depreciación/i);
    expect(select).toHaveValue("none");
    // The 'none' option is available
    const noneOption = screen.getByRole("option", {
      name: "Sin Depreciación (Terrenos)",
    });
    expect(noneOption).toBeInTheDocument();
  });

  it("TERRENOS useful_life_months=0 does not show validation error in edit mode (AC7)", async () => {
    mockAssetAndAudit(
      makeAsset({ depreciation_method: "none", useful_life_months: 0 }),
    );
    renderAssetDetail();
    await waitFor(() => screen.getAllByText("LAP-001").length > 0);

    await userEvent.click(screen.getByRole("button", { name: "Editar" }));

    // Trigger blur on useful_life_months field — no error should appear
    const lifeInput = screen.getByLabelText(/Vida Útil \(meses\)/i);
    expect(lifeInput).toHaveValue(0);
    await userEvent.click(lifeInput);
    await userEvent.tab();

    // No useful_life error message
    expect(
      screen.queryByText(/La vida útil debe ser mayor/i),
    ).not.toBeInTheDocument();
  });
});
