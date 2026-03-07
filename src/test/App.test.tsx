import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { QueryClient } from "@tanstack/react-query";
import App from "../App";

// Mock Tauri event listener — simulates backend-ready and backend-error events
const mockListeners: Record<string, ((event: { payload: unknown }) => void)[]> = {};

vi.mock("@tauri-apps/api/event", () => ({
  listen: vi.fn((event: string, handler: (e: { payload: unknown }) => void) => {
    if (!mockListeners[event]) {
      mockListeners[event] = [];
    }
    mockListeners[event].push(handler);
    // Return an unlisten function
    return Promise.resolve(() => {
      mockListeners[event] = mockListeners[event].filter((h) => h !== handler);
    });
  }),
}));

// Mock api module to avoid actual fetch calls
vi.mock("../lib/api", () => ({
  setApiPort: vi.fn(),
  getBaseUrl: vi.fn(() => "http://127.0.0.1:5000/api/v1"),
  apiFetch: vi.fn(),
}));

function emit(event: string, payload: unknown) {
  mockListeners[event]?.forEach((handler) => handler({ payload }));
}

function renderApp() {
  const testQueryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={testQueryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  );
}

describe("App — backend lifecycle gating (AC2, AC3)", () => {
  beforeEach(() => {
    // Clear all listeners between tests
    Object.keys(mockListeners).forEach((k) => delete mockListeners[k]);
  });

  it("shows LoadingSpinner while waiting for backend (AC2)", () => {
    renderApp();
    // Before any event fires, loading state
    expect(screen.getByRole("status", { name: /loading/i })).toBeInTheDocument();
    expect(screen.getByText(/iniciando sgaf/i)).toBeInTheDocument();
  });

  it("shows app shell after backend-ready event fires (AC2)", async () => {
    renderApp();
    // Spinner visible initially
    expect(screen.getByRole("status", { name: /loading/i })).toBeInTheDocument();

    // Simulate backend-ready with port
    await act(async () => {
      emit("backend-ready", 5000);
    });

    // Spinner gone, app shell visible
    expect(screen.queryByRole("status", { name: /loading/i })).not.toBeInTheDocument();
    expect(screen.getByText("SGAF")).toBeInTheDocument();
    expect(screen.getByText(/backend activo/i)).toBeInTheDocument();
  });

  it("shows ErrorMessage after backend-error event fires (AC3)", async () => {
    renderApp();

    await act(async () => {
      emit("backend-error", "Backend failed to start within 30 seconds");
    });

    // Error message visible — never a blank screen (NFR15)
    expect(screen.queryByRole("status", { name: /loading/i })).not.toBeInTheDocument();
    expect(screen.getByText(/error al iniciar sgaf/i)).toBeInTheDocument();
    expect(screen.getByText(/backend failed to start/i)).toBeInTheDocument();
  });
});
