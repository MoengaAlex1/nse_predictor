import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const defaultMarket = {
  date: "2026-07-25",
  nse20_value: 1842.5,
  nse20_change_pct: 0.35,
  top_gainers: [{ ticker: "SCOM.NR", change_pct: 3.2 }],
  top_losers: [{ ticker: "EABL.NR", change_pct: -1.8 }],
  signal_distribution: { BUY: 40, HOLD: 50, SELL: 27 },
  sector_performance: {},
};

const defaultCompanies = [
  {
    id: "SCOM.NR", ticker: "SCOM.NR", short: "Safaricom", color: "#22c55e",
    icon: "📱", name: "Safaricom PLC", sector: "Telecom",
    current_price: 14.5, change_pct_today: 3.2, signal: "BUY",
    price_history: [], price_preview: [], price_date: null, last_updated: null, csv: "",
  },
];

const { useMarketOverviewMock, useCompaniesMock } = vi.hoisted(() => ({
  useMarketOverviewMock: vi.fn(),
  useCompaniesMock: vi.fn(),
}));

vi.mock("../../hooks/useMarket", () => ({
  useMarketOverview: useMarketOverviewMock,
}));

vi.mock("../../hooks/useCompanies", () => ({
  useCompanies: useCompaniesMock,
}));

import { TickerTape } from "./TickerTape";

describe("TickerTape", () => {
  beforeEach(() => {
    useMarketOverviewMock.mockReturnValue({ data: defaultMarket });
    useCompaniesMock.mockReturnValue({ data: defaultCompanies });
  });

  afterEach(() => {
    useMarketOverviewMock.mockClear();
    useCompaniesMock.mockClear();
  });

  it("shows NSE 20 label", () => {
    render(<MemoryRouter><TickerTape /></MemoryRouter>);
    expect(screen.getAllByText("NSE 20").length).toBeGreaterThan(0);
  });

  it("shows a gainer ticker linked to the investor chart", () => {
    render(<MemoryRouter><TickerTape /></MemoryRouter>);
    expect(screen.getAllByText("SCOM.NR").length).toBeGreaterThan(0);
    const links = screen.getAllByRole("link", { name: /SCOM/i });
    expect(links[0]).toHaveAttribute("href", "/chart/SCOM.NR");
  });

  it("shows a loser ticker linked to the company page", () => {
    render(<MemoryRouter><TickerTape /></MemoryRouter>);
    expect(screen.getAllByText("EABL.NR").length).toBeGreaterThan(0);
  });

  it("renders nothing when market is null", () => {
    useMarketOverviewMock.mockReturnValueOnce({ data: null });
    const { container } = render(<MemoryRouter><TickerTape /></MemoryRouter>);
    expect(container.firstChild).toBeNull();
  });
});
