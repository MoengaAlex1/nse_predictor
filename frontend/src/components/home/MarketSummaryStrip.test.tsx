import { render, screen } from "@testing-library/react";
import { MarketSummaryStrip } from "./MarketSummaryStrip";
import type { MarketOverviewDoc, CompanyDoc } from "../../types";

const mockMarket: MarketOverviewDoc = {
  date: "2026-07-25",
  nse20_value: 1842.5,
  nse20_change_pct: 0.35,
  top_gainers: [],
  top_losers: [],
  signal_distribution: { BUY: 42, HOLD: 51, SELL: 24 },
  sector_performance: {},
};

const mockCompanies: CompanyDoc[] = Array.from({ length: 117 }, (_, i) => ({
  id: `CO${i}.NR`, ticker: `CO${i}.NR`, short: `Co${i}`, color: "#fff", icon: "🏢",
  name: `Company ${i}`, sector: "Banking", current_price: 10, change_pct_today: 0,
  signal: "HOLD" as const, price_history: [], price_preview: [],
  price_date: null, last_updated: null, csv: "",
}));

describe("MarketSummaryStrip", () => {
  it("shows NSE 20 value", () => {
    render(<MarketSummaryStrip market={mockMarket} companies={mockCompanies} />);
    expect(screen.getByText("1842.50")).toBeInTheDocument();
  });

  it("shows BUY/HOLD/SELL counts", () => {
    render(<MarketSummaryStrip market={mockMarket} companies={mockCompanies} />);
    expect(screen.getByText("42 BUY")).toBeInTheDocument();
    expect(screen.getByText("51 HOLD")).toBeInTheDocument();
    expect(screen.getByText("24 SELL")).toBeInTheDocument();
  });

  it("shows securities count from companies array length", () => {
    render(<MarketSummaryStrip market={mockMarket} companies={mockCompanies} />);
    expect(screen.getByText("117 securities tracked")).toBeInTheDocument();
  });

  it("shows the date", () => {
    render(<MarketSummaryStrip market={mockMarket} companies={mockCompanies} />);
    expect(screen.getByText("as of 2026-07-25")).toBeInTheDocument();
  });
});
