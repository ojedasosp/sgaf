/**
 * Tests for Sidebar component — Story 3.5 (AC4, AC5).
 */

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Sidebar from "./Sidebar";

describe("Sidebar", () => {
  it("renders all 7 navigation items", () => {
    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Sidebar />
      </MemoryRouter>,
    );

    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Activos")).toBeInTheDocument();
    expect(screen.getByText("Depreciación")).toBeInTheDocument();
    expect(screen.getByText("Reportes PDF")).toBeInTheDocument();
    expect(screen.getByText("Exportar ZEUS")).toBeInTheDocument();
    expect(screen.getByText("Mantenimientos")).toBeInTheDocument();
    expect(screen.getByText("Configuración")).toBeInTheDocument();
  });

  it("applies active styles to Dashboard when on /dashboard", () => {
    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Sidebar />
      </MemoryRouter>,
    );

    const dashboardButton = screen.getByText("Dashboard").closest("button");
    expect(dashboardButton).toHaveClass("border-l-[3px]");
    expect(dashboardButton).toHaveClass("border-[#458588]");
    expect(dashboardButton).toHaveClass("bg-[#d5c4a1]");

    const activosButton = screen.getByText("Activos").closest("button");
    expect(activosButton).toHaveClass("border-transparent");
    expect(activosButton).not.toHaveClass("bg-[#d5c4a1]");
  });

  it("applies active styles to Activos when on /assets", () => {
    render(
      <MemoryRouter initialEntries={["/assets"]}>
        <Sidebar />
      </MemoryRouter>,
    );

    const activosButton = screen.getByText("Activos").closest("button");
    expect(activosButton).toHaveClass("border-l-[3px]");
    expect(activosButton).toHaveClass("border-[#458588]");
    expect(activosButton).toHaveClass("bg-[#d5c4a1]");

    const dashboardButton = screen.getByText("Dashboard").closest("button");
    expect(dashboardButton).toHaveClass("border-transparent");
  });
});
