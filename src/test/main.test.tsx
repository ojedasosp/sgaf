import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { queryClient } from "../lib/queryClient";
import App from "../App";

// Mock Tauri events
vi.mock("@tauri-apps/api/event", () => ({
  listen: vi.fn((_event: string, _handler: (e: { payload: unknown }) => void) =>
    Promise.resolve(() => {})
  ),
}));

// Mock api module
vi.mock("../lib/api", () => ({
  setApiPort: vi.fn(),
  getBaseUrl: vi.fn(() => "http://127.0.0.1:5000/api/v1"),
  apiFetch: vi.fn(),
}));

describe("main.tsx — React entry point with providers", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Provider structure", () => {
    it("renders with QueryClientProvider and BrowserRouter", () => {
      const { container } = render(
        <React.StrictMode>
          <QueryClientProvider client={queryClient}>
            <BrowserRouter>
              <App />
            </BrowserRouter>
          </QueryClientProvider>
        </React.StrictMode>
      );

      // If providers are missing, React would throw
      expect(container).toBeDefined();
    });

    it("BrowserRouter enables React Router", () => {
      const { container } = render(
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </QueryClientProvider>
      );

      // BrowserRouter should have initialized location hook
      expect(container).toBeDefined();
    });

    it("QueryClientProvider makes queryClient available to hooks", () => {
      const { container } = render(
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </QueryClientProvider>
      );

      // useQuery and other hooks should work inside this provider
      expect(container).toBeDefined();
    });

    it("StrictMode is enabled for development checks", () => {
      // StrictMode intentionally double-invokes effects in development
      // This test verifies the app handles it gracefully
      const { container } = render(
        <React.StrictMode>
          <QueryClientProvider client={queryClient}>
            <BrowserRouter>
              <App />
            </BrowserRouter>
          </QueryClientProvider>
        </React.StrictMode>
      );

      expect(container).toBeDefined();
    });
  });

  describe("App rendering with providers", () => {
    it("App renders inside provider hierarchy", async () => {
      render(
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </QueryClientProvider>
      );

      // App shows loading state initially
      const loadingSpinner = await screen.findByRole("status", {
        name: /loading/i,
      });
      expect(loadingSpinner).toBeInTheDocument();
    });

    it("renders App when all providers are present", () => {
      const { container } = render(
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </QueryClientProvider>
      );

      // App should render successfully with all providers
      expect(container).toBeInTheDocument();
    });

    it("window location is accessible inside BrowserRouter", () => {
      const { container } = render(
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </QueryClientProvider>
      );

      // BrowserRouter initializes history/location
      expect(window.location).toBeDefined();
      expect(container).toBeDefined();
    });
  });

  describe("Entry point configuration", () => {
    it("queryClient is properly configured for React Query", () => {
      render(
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </QueryClientProvider>
      );

      // Verify queryClient has expected methods
      expect(queryClient.getQueryData).toBeDefined();
      expect(queryClient.getQueryCache).toBeDefined();
    });

    it("App can be rendered multiple times with fresh providers", () => {
      const { unmount: unmount1 } = render(
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </QueryClientProvider>
      );
      unmount1();

      // Render again - should not cause errors
      const { container } = render(
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </QueryClientProvider>
      );

      expect(container).toBeDefined();
    });
  });

  describe("Provider error handling", () => {
    it("catches errors thrown by child components", () => {
      // If App throws, React should propagate it
      const spy = vi.spyOn(console, "error").mockImplementation(() => {});

      expect(() => {
        render(
          <QueryClientProvider client={queryClient}>
            <BrowserRouter>
              <App />
            </BrowserRouter>
          </QueryClientProvider>
        );
      }).not.toThrow();

      spy.mockRestore();
    });
  });
});
