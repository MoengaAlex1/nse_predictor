import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("../../context/ThemeContext", () => ({
  useTheme: () => ({ theme: "dark", setTheme: vi.fn(), resolvedTheme: "dark" }),
}));
vi.mock("../../hooks/useCompanies", () => ({
  useCompanies: () => ({ data: [], isLoading: false }),
}));
vi.mock("../../hooks/useMarket", () => ({
  useMarketOverview: () => ({ data: null }),
}));

import { AppShell } from "./AppShell";

describe("AppShell", () => {
  it("renders children inside main", () => {
    render(
      <MemoryRouter>
        <AppShell><p>Page content</p></AppShell>
      </MemoryRouter>,
    );
    expect(screen.getByText("Page content")).toBeInTheDocument();
  });

  it("renders the NSE logo", () => {
    render(
      <MemoryRouter>
        <AppShell><p>x</p></AppShell>
      </MemoryRouter>,
    );
    expect(screen.getByText("NSE")).toBeInTheDocument();
  });

  it("renders desktop nav links", () => {
    render(
      <MemoryRouter>
        <AppShell><p>x</p></AppShell>
      </MemoryRouter>,
    );
    expect(screen.getAllByText("Markets").length).toBeGreaterThan(0);
  });
});
