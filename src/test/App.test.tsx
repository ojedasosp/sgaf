import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { QueryClient } from "@tanstack/react-query";
import App from "../App";
import Dashboard from "../screens/Dashboard";
import { useAppStore } from "../store/appStore";

// Mock Tauri event listener — simulates backend-ready and backend-error events
const mockListeners: Record<string, ((event: { payload: unknown }) => void)[]> = {};

vi.mock("@tauri-apps/api/event", () => ({
  listen: vi.fn((event: string, handler: (e: { payload: unknown }) => void) => {
    if (!mockListeners[event]) {
      mockListeners[event] = [];
    }
    mockListeners[event].push(handler);
    return Promise.resolve(() => {
      mockListeners[event] = mockListeners[event].filter((h) => h !== handler);
    });
  }),
}));

// Mock Tauri core (used by SetupWizard for convertFileSrc)
vi.mock("@tauri-apps/api/core", () => ({
  convertFileSrc: vi.fn((path: string) => `asset://${path}`),
  invoke: vi.fn(() => Promise.resolve({ Loading: null })),
}));

// Mock globalThis.fetch — apiFetch uses fetch internally
globalThis.fetch = vi.fn();

function mockFetchResponse(body: unknown, status = 200) {
  (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    })
  );
}

function emit(event: string, payload: unknown) {
  mockListeners[event]?.forEach((handler) => handler({ payload }));
}

function renderApp() {
  const testQueryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={testQueryClient}>
      <MemoryRouter>
        <App />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("App — backend lifecycle gating", () => {
  beforeEach(() => {
    Object.keys(mockListeners).forEach((k) => delete mockListeners[k]);
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockReset();
  });

  it("shows LoadingSpinner while waiting for backend", () => {
    renderApp();
    expect(screen.getByRole("status", { name: /loading/i })).toBeInTheDocument();
    expect(screen.getByText(/iniciando sgaf/i)).toBeInTheDocument();
  });

  it("navigates to login when setup is complete after backend-ready", async () => {
    mockFetchResponse({ data: { setup_complete: true } });

    renderApp();
    expect(screen.getByRole("status", { name: /loading/i })).toBeInTheDocument();

    await act(async () => {
      emit("backend-ready", 5000);
    });

    // Should navigate to /login (Login screen with password form)
    expect(screen.queryByRole("status", { name: /loading/i })).not.toBeInTheDocument();
    expect(screen.getByText("SGAF")).toBeInTheDocument();
    expect(screen.getByLabelText(/contraseña/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /ingresar/i })).toBeInTheDocument();
  });

  it("navigates to wizard when setup is incomplete after backend-ready", async () => {
    mockFetchResponse({ data: { setup_complete: false } });

    renderApp();

    await act(async () => {
      emit("backend-ready", 5000);
    });

    // Should navigate to /wizard (SetupWizard)
    expect(screen.queryByRole("status", { name: /loading/i })).not.toBeInTheDocument();
    expect(screen.getByText(/company information/i)).toBeInTheDocument();
    expect(screen.getByText(/step 1 of 2/i)).toBeInTheDocument();
  });

  it("navigates to wizard on setup-status fetch failure (safe fallback)", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error("Network error")
    );

    renderApp();

    await act(async () => {
      emit("backend-ready", 5000);
    });

    // Should fall back to /wizard
    expect(screen.queryByRole("status", { name: /loading/i })).not.toBeInTheDocument();
    expect(screen.getByText(/company information/i)).toBeInTheDocument();
  });

  it("shows ErrorMessage after backend-error event fires", async () => {
    renderApp();

    await act(async () => {
      emit("backend-error", "Backend failed to start within 30 seconds");
    });

    // Error message visible — never a blank screen
    expect(screen.queryByRole("status", { name: /loading/i })).not.toBeInTheDocument();
    expect(screen.getByText(/error al iniciar sgaf/i)).toBeInTheDocument();
    expect(screen.getByText(/backend failed to start/i)).toBeInTheDocument();
  });
});

describe("App — PrivateRoute and Dashboard routing", () => {
  beforeEach(() => {
    Object.keys(mockListeners).forEach((k) => delete mockListeners[k]);
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockReset();
    useAppStore.getState().clearToken();
  });

  it("redirects /dashboard to /login when no token is present", async () => {
    const testQueryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={testQueryClient}>
        <MemoryRouter initialEntries={["/dashboard"]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>
    );

    // App starts in loading state; trigger backend-ready so routing resolves
    mockFetchResponse({ data: { setup_complete: true } });
    await act(async () => {
      emit("backend-ready", 5000);
    });

    // No token → redirected to /login
    expect(screen.getByLabelText(/contraseña/i)).toBeInTheDocument();
    expect(screen.queryByText(/dashboard/i)).not.toBeInTheDocument();
  });

  it("Dashboard component renders its placeholder content", () => {
    // The full token → /dashboard navigation flow is covered by Login.test.tsx.
    // This test verifies the Dashboard component itself renders correctly.
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    );
    expect(screen.getByText("SGAF")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /nuevo activo/i })).toBeInTheDocument();
  });
});
