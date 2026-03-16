/**
 * Tests for AppLayout component — Story 3.5 (AC4, AC6).
 */

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import AppLayout from "./AppLayout";

describe("AppLayout", () => {
  it("renders sidebar and children", () => {
    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <AppLayout>
          <div data-testid="child">Content</div>
        </AppLayout>
      </MemoryRouter>,
    );

    // Sidebar branding
    expect(screen.getByText("SGAF")).toBeInTheDocument();
    // Children rendered
    expect(screen.getByTestId("child")).toBeInTheDocument();
  });
});
