/**
 * Tests for AssetForm — new fixed asset registration form (Story 2.1).
 *
 * Covers:
 *  - Renders both sections with all required fields
 *  - Inline validation on blur for required fields
 *  - Successful submission calls API and redirects to /assets/:id
 *  - API error (409 duplicate code) shows error without losing form data
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, act, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AssetForm from "../features/assets/AssetForm";
import { useAppStore } from "../store/appStore";

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

globalThis.fetch = vi.fn();

function mockFetchResponse(body: unknown, status = 200) {
  (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    })
  );
}

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function renderAssetForm() {
  const queryClient = makeQueryClient();
  // Set a token so the hook picks it up
  useAppStore.getState().setToken("test-token");

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/assets/new"]}>
        <Routes>
          <Route path="/assets/new" element={<AssetForm />} />
          <Route path="/assets/:id" element={<div>Asset Detail Page</div>} />
          <Route path="/dashboard" element={<div>Dashboard Page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// ---------------------------------------------------------------------------
// Valid form data helper
// ---------------------------------------------------------------------------

async function fillValidForm(user: ReturnType<typeof userEvent.setup>) {
  await user.clear(screen.getByLabelText(/código/i));
  await user.type(screen.getByLabelText(/código/i), "LAP-001");

  await user.clear(screen.getByLabelText(/descripción/i));
  await user.type(screen.getByLabelText(/descripción/i), "HP Laptop 14 pulgadas");

  await user.clear(screen.getByLabelText(/categoría/i));
  await user.type(screen.getByLabelText(/categoría/i), "Equipos de Cómputo");

  await user.clear(screen.getByLabelText(/costo histórico/i));
  await user.type(screen.getByLabelText(/costo histórico/i), "1200.00");

  await user.clear(screen.getByLabelText(/valor residual/i));
  await user.type(screen.getByLabelText(/valor residual/i), "120.00");

  await user.clear(screen.getByLabelText(/vida útil/i));
  await user.type(screen.getByLabelText(/vida útil/i), "60");

  // Date input type="date" — set via fireEvent or direct value
  const dateInput = screen.getByLabelText(/fecha de adquisición/i);
  await user.clear(dateInput);
  await user.type(dateInput, "2026-03-01");
}

// ---------------------------------------------------------------------------
// Section rendering tests
// ---------------------------------------------------------------------------

describe("AssetForm — rendering", () => {
  beforeEach(() => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockReset();
    useAppStore.getState().clearToken();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the Identificación section heading", () => {
    renderAssetForm();
    expect(screen.getByText(/identificación/i)).toBeInTheDocument();
  });

  it("renders the Valorización section heading", () => {
    renderAssetForm();
    expect(screen.getByText(/valorización/i)).toBeInTheDocument();
  });

  it("renders the Código field", () => {
    renderAssetForm();
    expect(screen.getByLabelText(/código/i)).toBeInTheDocument();
  });

  it("renders the Descripción field", () => {
    renderAssetForm();
    expect(screen.getByLabelText(/descripción/i)).toBeInTheDocument();
  });

  it("renders the Categoría field", () => {
    renderAssetForm();
    expect(screen.getByLabelText(/categoría/i)).toBeInTheDocument();
  });

  it("renders the Costo Histórico field", () => {
    renderAssetForm();
    expect(screen.getByLabelText(/costo histórico/i)).toBeInTheDocument();
  });

  it("renders the Valor Residual field", () => {
    renderAssetForm();
    expect(screen.getByLabelText(/valor residual/i)).toBeInTheDocument();
  });

  it("renders the Vida Útil field", () => {
    renderAssetForm();
    expect(screen.getByLabelText(/vida útil/i)).toBeInTheDocument();
  });

  it("renders the Fecha de Adquisición field", () => {
    renderAssetForm();
    expect(screen.getByLabelText(/fecha de adquisición/i)).toBeInTheDocument();
  });

  it("renders the Método de Depreciación select", () => {
    renderAssetForm();
    expect(screen.getByLabelText(/método de depreciación/i)).toBeInTheDocument();
  });

  it("depreciation select has all three options (AC5)", () => {
    renderAssetForm();
    expect(screen.getByText("Lineal")).toBeInTheDocument();
    expect(screen.getByText("Suma de Dígitos")).toBeInTheDocument();
    expect(screen.getByText("Saldo Decreciente")).toBeInTheDocument();
  });

  it("renders the submit button", () => {
    renderAssetForm();
    expect(
      screen.getByRole("button", { name: /registrar activo/i })
    ).toBeInTheDocument();
  });

  it("all required fields are marked with *", () => {
    renderAssetForm();
    // There should be at least 8 asterisks (one per required field)
    const asterisks = screen.getAllByText("*");
    expect(asterisks.length).toBeGreaterThanOrEqual(8);
  });
});

// ---------------------------------------------------------------------------
// Inline validation tests
// ---------------------------------------------------------------------------

describe("AssetForm — inline validation on blur (AC2)", () => {
  beforeEach(() => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockReset();
    useAppStore.getState().clearToken();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows error for empty Código after blur", async () => {
    const user = userEvent.setup();
    renderAssetForm();

    const codeInput = screen.getByLabelText(/código/i);
    await user.click(codeInput);
    await user.tab(); // trigger blur

    expect(await screen.findByText(/código del activo es obligatorio/i)).toBeInTheDocument();
  });

  it("shows error for empty Descripción after blur", async () => {
    const user = userEvent.setup();
    renderAssetForm();

    await user.click(screen.getByLabelText(/descripción/i));
    await user.tab();

    expect(await screen.findByText(/descripción es obligatoria/i)).toBeInTheDocument();
  });

  it("shows error for historical_cost = 0 after blur", async () => {
    const user = userEvent.setup();
    renderAssetForm();

    const costInput = screen.getByLabelText(/costo histórico/i);
    await user.type(costInput, "0");
    await user.tab();

    expect(
      await screen.findByText(/costo histórico debe ser mayor a 0/i)
    ).toBeInTheDocument();
  });

  it("shows error for salvage_value >= historical_cost", async () => {
    const user = userEvent.setup();
    renderAssetForm();

    await user.type(screen.getByLabelText(/costo histórico/i), "100");
    await user.tab();

    await user.type(screen.getByLabelText(/valor residual/i), "200");
    await user.tab();

    expect(
      await screen.findByText(/valor residual debe ser menor al costo histórico/i)
    ).toBeInTheDocument();
  });

  it("shows error for negative salvage_value", async () => {
    const user = userEvent.setup();
    renderAssetForm();

    await user.type(screen.getByLabelText(/valor residual/i), "-10");
    await user.tab();

    expect(
      await screen.findByText(/valor residual debe ser cero o mayor/i)
    ).toBeInTheDocument();
  });

  it("shows error for useful_life_months = 0 after blur", async () => {
    const user = userEvent.setup();
    renderAssetForm();

    const lifeInput = screen.getByLabelText(/vida útil/i);
    await user.type(lifeInput, "0");
    await user.tab();

    expect(
      await screen.findByText(/vida útil debe ser mayor a 0/i)
    ).toBeInTheDocument();
  });

  it("data is preserved in fields after showing validation errors (AC2)", async () => {
    const user = userEvent.setup();
    renderAssetForm();

    // Type something in code field
    const codeInput = screen.getByLabelText(/código/i);
    await user.type(codeInput, "MY-CODE");

    // Submit with empty other required fields (triggers validation errors)
    await user.click(screen.getByRole("button", { name: /registrar activo/i }));

    // Code field should STILL have its value
    expect(codeInput).toHaveValue("MY-CODE");
  });
});

// ---------------------------------------------------------------------------
// Successful submission
// ---------------------------------------------------------------------------

describe("AssetForm — successful submission (AC3)", () => {
  beforeEach(() => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockReset();
    useAppStore.getState().setToken("test-token");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("calls POST /api/v1/assets/ with correct payload on submit", async () => {
    mockFetchResponse({
      data: {
        asset_id: 42,
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
      },
    });

    const user = userEvent.setup();
    renderAssetForm();
    await fillValidForm(user);

    await act(async () => {
      await user.click(screen.getByRole("button", { name: /registrar activo/i }));
    });

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalled();
    });

    const fetchCall = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(fetchCall[0]).toContain("/assets/");
    expect(fetchCall[1].method).toBe("POST");
    const body = JSON.parse(fetchCall[1].body as string);
    expect(body.code).toBe("LAP-001");
    expect(body.historical_cost).toBe("1200.00");
    expect(body.depreciation_method).toBe("straight_line");
  });

  it("navigates to /assets/:id after successful creation (AC3)", async () => {
    mockFetchResponse({
      data: {
        asset_id: 42,
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
      },
    });

    const user = userEvent.setup();
    renderAssetForm();
    await fillValidForm(user);

    await act(async () => {
      await user.click(screen.getByRole("button", { name: /registrar activo/i }));
    });

    expect(await screen.findByText("Asset Detail Page")).toBeInTheDocument();
  });

  it("sends Authorization header with Bearer token", async () => {
    mockFetchResponse({
      data: {
        asset_id: 1,
        code: "LAP-001",
        description: "Test",
        historical_cost: "1000.0000",
        salvage_value: "100.0000",
        useful_life_months: 12,
        acquisition_date: "2026-01-01",
        category: "Test",
        depreciation_method: "straight_line",
        status: "active",
        retirement_date: null,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    });

    const user = userEvent.setup();
    renderAssetForm();
    await fillValidForm(user);

    await act(async () => {
      await user.click(screen.getByRole("button", { name: /registrar activo/i }));
    });

    await waitFor(() => {
      expect(globalThis.fetch).toHaveBeenCalled();
    });

    const fetchCall = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(fetchCall[1].headers["Authorization"]).toBe("Bearer test-token");
  });
});

// ---------------------------------------------------------------------------
// API error handling
// ---------------------------------------------------------------------------

describe("AssetForm — API error handling", () => {
  beforeEach(() => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockReset();
    useAppStore.getState().setToken("test-token");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows error message on 409 duplicate code without losing form data", async () => {
    mockFetchResponse(
      { error: "CONFLICT", message: "Asset code 'LAP-001' already exists", field: "code" },
      409
    );

    const user = userEvent.setup();
    renderAssetForm();
    await fillValidForm(user);

    await act(async () => {
      await user.click(screen.getByRole("button", { name: /registrar activo/i }));
    });

    // Error message displayed INLINE on the code field (H1 fix — Subtask 9.8)
    expect(
      await screen.findByRole("alert")
    ).toBeInTheDocument();
    expect(screen.getByText(/already exists/i)).toBeInTheDocument();

    // Form data preserved (code field still has value)
    expect(screen.getByLabelText(/código/i)).toHaveValue("LAP-001");

    // Did NOT navigate away
    expect(screen.queryByText("Asset Detail Page")).not.toBeInTheDocument();
  });

  it("does not navigate on API error", async () => {
    mockFetchResponse(
      { error: "CONFLICT", message: "Already exists" },
      409
    );

    const user = userEvent.setup();
    renderAssetForm();
    await fillValidForm(user);

    await act(async () => {
      await user.click(screen.getByRole("button", { name: /registrar activo/i }));
    });

    await waitFor(() => {
      expect(screen.queryByText("Asset Detail Page")).not.toBeInTheDocument();
    });
  });

  it("shows generic submit error when backend error has no field", async () => {
    mockFetchResponse(
      { error: "INTERNAL_ERROR", message: "Something went wrong" },
      500
    );

    const user = userEvent.setup();
    renderAssetForm();
    await fillValidForm(user);

    await act(async () => {
      await user.click(screen.getByRole("button", { name: /registrar activo/i }));
    });

    // Generic error shown (no field to map to)
    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument();
  });

  it("button is re-enabled after API error", async () => {
    mockFetchResponse({ error: "CONFLICT", message: "Duplicate" }, 409);

    const user = userEvent.setup();
    renderAssetForm();
    await fillValidForm(user);

    await act(async () => {
      await user.click(screen.getByRole("button", { name: /registrar activo/i }));
    });

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /registrar activo/i })
      ).not.toBeDisabled();
    });
  });
});
