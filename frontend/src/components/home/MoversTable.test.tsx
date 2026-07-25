import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { MoversTable } from "./MoversTable";
import type { MarketOverviewDoc, CompanyDoc } from "../../types";

const mkCompany = (ticker: string, pct: number, signal: "BUY" | "HOLD" | "SELL" = "BUY"): CompanyDoc => ({
  id: `${ticker}.NR`, ticker, short: ticker.toLowerCase(), color: "#fff", icon: "🏢",
  name: `${ticker} Ltd`, sector: "Banking", current_price: 10, change_pct_today: pct,
  signal, price_history: [], price_preview: [], price_date: null, last_updated: null, csv: "",
});

const mockMarket: MarketOverviewDoc = {
  date: "2026-07-25",
  nse20_value: null, nse20_change_pct: null,
  signal_distribution: { BUY: 10, HOLD: 10, SELL: 10 },
  sector_performance: {},
  top_gainers: [
    { ticker: "AAAA", change_pct: 5 },
    { ticker: "BBBB", change_pct: 4 },
  ],
  top_losers: [{ ticker: "CCCC", change_pct: -3 }],
};

const mockCompanies: CompanyDoc[] = [
  mkCompany("AAAA", 5),
  mkCompany("BBBB", 4),
  mkCompany("CCCC", -3),
  mkCompany("DDDD", 2),
  mkCompany("EEEE", 1),
];

const wrap = (ui: React.ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>);

describe("MoversTable — gainers", () => {
  it("renders the header label", () => {
    wrap(<MoversTable type="gainers" market={mockMarket} companies={mockCompanies} />);
    expect(screen.getByText("Top Gainers")).toBeInTheDocument();
  });

  it("shows joined company names for top_gainers", () => {
    wrap(<MoversTable type="gainers" market={mockMarket} companies={mockCompanies} />);
    expect(screen.getByText("aaaa")).toBeInTheDocument();
    expect(screen.getByText("bbbb")).toBeInTheDocument();
  });
});

describe("MoversTable — active", () => {
  it("renders Most Active header", () => {
    wrap(<MoversTable type="active" market={mockMarket} companies={mockCompanies} />);
    expect(screen.getByText("Most Active")).toBeInTheDocument();
  });

  it("shows company rows sorted by absolute change", () => {
    wrap(<MoversTable type="active" market={mockMarket} companies={mockCompanies} />);
    const links = screen.getAllByRole("link");
    expect(links[0]).toHaveAttribute("href", "/company/AAAA");
  });
});

describe("MoversTable — empty", () => {
  it("shows empty message when no rows", () => {
    const emptyMarket = { ...mockMarket, top_gainers: [] };
    wrap(<MoversTable type="gainers" market={emptyMarket} companies={[]} />);
    expect(screen.getByText("No data available")).toBeInTheDocument();
  });
});
