import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import Login from "../screens/Login";
import { useAppStore } from "../store/appStore";

// Mock Tauri core (imported transitively through modules)
vi.mock("@tauri-apps/api/core", () => ({
  convertFileSrc: vi.fn((path: string) => `asset://${path}`),
  invoke: vi.fn(),
}));

// Mock Tauri event (imported transitively)
vi.mock("@tauri-apps/api/event", () => ({
  listen: vi.fn(() => Promise.resolve(() => {})),
}));

// globalThis.fetch is the real network layer behind apiFetch
// Per Story 1.3 debug log: mock fetch directly — do NOT mock the apiFetch module
globalThis.fetch = vi.fn();

function mockFetchResponse(body: unknown, status = 200) {
  (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

function mockFetchError(message: string) {
  (globalThis.fetch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
    new Error(message),
  );
}

/** Render Login inside a MemoryRouter; a /dashboard route acts as post-login destination. */
function renderLogin() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/dashboard" element={<div>Dashboard Page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Login screen — form rendering", () => {
  beforeEach(() => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockReset();
    useAppStore.getState().clearToken();
  });

  it("renders password field", () => {
    renderLogin();
    expect(screen.getByLabelText(/contraseña/i)).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText(/ingresa tu contraseña/i),
    ).toBeInTheDocument();
  });

  it("renders Ingresar button", () => {
    renderLogin();
    expect(
      screen.getByRole("button", { name: /ingresar/i }),
    ).toBeInTheDocument();
  });

  it("renders SGAF title", () => {
    renderLogin();
    expect(screen.getByText("SGAF")).toBeInTheDocument();
  });

  it("password input is type=password (masked)", () => {
    renderLogin();
    const input = screen.getByLabelText(/contraseña/i);
    expect(input).toHaveAttribute("type", "password");
  });

  it("password input has required attribute", () => {
    renderLogin();
    const input = screen.getByLabelText(/contraseña/i);
    expect(input).toBeRequired();
  });

  it("shows no application data content — only the login form", () => {
    renderLogin();
    // No navigation sidebar, no asset tables, no dashboard content
    expect(screen.queryByText("Dashboard Page")).not.toBeInTheDocument();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

describe("Login screen — successful login", () => {
  beforeEach(() => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockReset();
    useAppStore.getState().clearToken();
  });

  it("stores JWT in Zustand and navigates to /dashboard on success", async () => {
    mockFetchResponse({ data: { token: "header.payload.signature" } });

    renderLogin();

    await act(async () => {
      await userEvent.type(
        screen.getByLabelText(/contraseña/i),
        "correctpassword",
      );
      await userEvent.click(screen.getByRole("button", { name: /ingresar/i }));
    });

    // Token stored in Zustand
    expect(useAppStore.getState().token).toBe("header.payload.signature");
    // Navigated to dashboard
    expect(screen.getByText("Dashboard Page")).toBeInTheDocument();
  });

  it("calls POST /api/v1/auth/login with the password in body", async () => {
    mockFetchResponse({ data: { token: "test.token" } });

    renderLogin();

    await act(async () => {
      await userEvent.type(screen.getByLabelText(/contraseña/i), "mysecret");
      await userEvent.click(screen.getByRole("button", { name: /ingresar/i }));
    });

    const fetchCall = (globalThis.fetch as ReturnType<typeof vi.fn>).mock
      .calls[0];
    expect(fetchCall[0]).toContain("/auth/login");
    const requestBody = JSON.parse(fetchCall[1].body as string);
    expect(requestBody.password).toBe("mysecret");
    expect(fetchCall[1].method).toBe("POST");
  });

  it("shows loading state while request is in flight", async () => {
    let resolvePromise!: (value: Response) => void;
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockReturnValueOnce(
      new Promise<Response>((resolve) => {
        resolvePromise = resolve;
      }),
    );

    renderLogin();

    // Start submit — don't await so we can check intermediate state
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/contraseña/i), "pass");
    act(() => {
      user.click(screen.getByRole("button", { name: /ingresar/i }));
    });

    // Button should show loading text
    expect(
      await screen.findByRole("button", { name: /verificando/i }),
    ).toBeInTheDocument();

    // Resolve the fetch
    await act(async () => {
      resolvePromise(
        new Response(JSON.stringify({ data: { token: "tok" } }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    });
  });
});

describe("Login screen — failed login", () => {
  beforeEach(() => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockReset();
    useAppStore.getState().clearToken();
  });

  it("shows inline error on wrong password (401)", async () => {
    mockFetchResponse(
      { error: "UNAUTHORIZED", message: "Invalid credentials" },
      401,
    );

    renderLogin();

    await act(async () => {
      await userEvent.type(screen.getByLabelText(/contraseña/i), "wrongpass");
      await userEvent.click(screen.getByRole("button", { name: /ingresar/i }));
    });

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/invalid credentials/i);
    // No navigation
    expect(screen.queryByText("Dashboard Page")).not.toBeInTheDocument();
    // Token not stored
    expect(useAppStore.getState().token).toBeNull();
  });

  it("shows error on network failure", async () => {
    mockFetchError("Network error");

    renderLogin();

    await act(async () => {
      await userEvent.type(screen.getByLabelText(/contraseña/i), "pass");
      await userEvent.click(screen.getByRole("button", { name: /ingresar/i }));
    });

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText("Dashboard Page")).not.toBeInTheDocument();
  });

  it("does not navigate on error", async () => {
    mockFetchResponse(
      { error: "UNAUTHORIZED", message: "Invalid credentials" },
      401,
    );

    renderLogin();

    await act(async () => {
      await userEvent.type(screen.getByLabelText(/contraseña/i), "bad");
      await userEvent.click(screen.getByRole("button", { name: /ingresar/i }));
    });

    // Still on login page
    expect(
      screen.getByRole("button", { name: /ingresar/i }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Dashboard Page")).not.toBeInTheDocument();
  });

  it("button is re-enabled after failed login", async () => {
    mockFetchResponse(
      { error: "UNAUTHORIZED", message: "Invalid credentials" },
      401,
    );

    renderLogin();

    await act(async () => {
      await userEvent.type(screen.getByLabelText(/contraseña/i), "bad");
      await userEvent.click(screen.getByRole("button", { name: /ingresar/i }));
    });

    expect(
      screen.getByRole("button", { name: /ingresar/i }),
    ).not.toBeDisabled();
  });

  it("clears previous error on new submit attempt", async () => {
    // First attempt: wrong password
    mockFetchResponse(
      { error: "UNAUTHORIZED", message: "Invalid credentials" },
      401,
    );
    renderLogin();

    await act(async () => {
      await userEvent.type(screen.getByLabelText(/contraseña/i), "wrong");
      await userEvent.click(screen.getByRole("button", { name: /ingresar/i }));
    });
    expect(screen.getByRole("alert")).toBeInTheDocument();

    // Second attempt: correct password
    mockFetchResponse({ data: { token: "new.token" } });
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: /ingresar/i }));
    });

    // Error cleared (navigated away or error gone)
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
