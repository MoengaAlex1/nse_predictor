import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../lib/firebase", () => ({ app: {}, db: {}, auth: {} }));
vi.mock("../lib/rtdb", () => ({ rtdb: {} }));
vi.mock("../hooks/useCompanies", () => ({ useCompanies: () => ({ data: [], isLoading: false }) }));
vi.mock("../hooks/useMarket", () => ({ useMarketOverview: () => ({ data: null }) }));
vi.mock("../hooks/useQuotes", () => ({
  useQuote: () => ({ data: null }),
  useQuotesFor: () => ({ data: new Map() }),
}));
vi.mock("../hooks/useWatchlist", () => ({
  useWatchlist: () => ({ tickers: [], isAuthenticated: false, has: () => false, add: vi.fn(), remove: vi.fn(), isPending: false }),
}));

import { TerminalShell } from "./TerminalShell";

/** Every nav item the shell offers, and where it must point. */
const NAV = [
  ["Markets", "/companies"],
  ["Screener", "/screener"],
  ["Charts", "/chart/EQTY"],
  ["Portfolios", "/portfolios"],
  ["Sectors", "/sectors"],
  ["News", "/news"],
  ["Calendar", "/calendar"],
];

const wrap = (ui: React.ReactElement, path = "/") =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="*" element={<TerminalShell>{ui}</TerminalShell>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );

beforeEach(() => window.localStorage.clear());

describe("TerminalShell", () => {
  it("renders every nav item with a real destination", () => {
    wrap(<div>panel</div>);
    for (const [label, href] of NAV) {
      const link = screen.getByRole("link", { name: label });
      expect(link).toHaveAttribute("href", href);
    }
  });

  it("renders no disabled dead-end nav items", () => {
    wrap(<div>panel</div>);
    // The retired shell rendered Portfolios/Sectors as inert spans.
    for (const [label] of NAV) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    }
  });

  it("shows the market status pill", () => {
    wrap(<div>panel</div>);
    expect(screen.getByText(/^(Open|Closed)$/)).toBeInTheDocument();
  });

  it("persists the rail collapsed state", async () => {
    const user = userEvent.setup();
    wrap(<div>panel</div>);
    await user.click(screen.getByTitle("Collapse watchlist"));
    expect(window.localStorage.getItem("nse.rail_collapsed")).toBe("1");
    await user.click(screen.getByTitle("Expand watchlist"));
    expect(window.localStorage.getItem("nse.rail_collapsed")).toBe("0");
  });

  it("restores the collapsed rail on mount", () => {
    window.localStorage.setItem("nse.rail_collapsed", "1");
    wrap(<div>panel</div>);
    expect(screen.getByTitle("Expand watchlist")).toBeInTheDocument();
  });

  it("opens the shortcuts overlay on ?", async () => {
    const user = userEvent.setup();
    wrap(<div>panel</div>);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await user.keyboard("?");
    expect(screen.getByRole("dialog", { name: /keyboard shortcuts/i })).toBeInTheDocument();
  });

  it("renders the same chrome regardless of route", () => {
    const { unmount } = wrap(<div>panel</div>, "/screener");
    const first = screen.getAllByRole("link").map((a) => a.getAttribute("href"));
    unmount();
    wrap(<div>panel</div>, "/chart/EQTY");
    const second = screen.getAllByRole("link").map((a) => a.getAttribute("href"));
    expect(second).toEqual(first);
  });
});
