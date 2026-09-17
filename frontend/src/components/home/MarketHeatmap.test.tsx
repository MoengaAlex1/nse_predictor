import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { MarketHeatmap } from "./MarketHeatmap";
import type { CompanyDoc, IndexReading, MarketOverviewDoc } from "../../types";

const mkCompany = (short: string, pct: number | null, price: number | null = 10): CompanyDoc => ({
  id: short, ticker: `${short}.NR`, short, name: `${short} Ltd`,
  sector: "Banking", color: "#fff", icon: "🏢",
  current_price: price, change_pct_today: pct,
  signal: "HOLD", price_history: [], price_preview: [],
  price_date: null, last_updated: null, csv: "",
});

const mkIndex = (
  key: string, label: string, value: number, changePoints: number,
): IndexReading => {
  const prev = value - changePoints;
  return {
    key, label, value, change_points: changePoints,
    change_pct: prev !== 0 ? (changePoints / prev) * 100 : 0,
  };
};

const FULL_INDICES: Record<string, IndexReading> = {
  NASI:   mkIndex("NASI",   "NASI",   245.91,   0.49),
  NSE20:  mkIndex("NSE20",  "NSE 20", 4301.86, -17.96),
  NSE10:  mkIndex("NSE10",  "NSE 10", 2703.13,  -7.18),
  NSE25:  mkIndex("NSE25",  "NSE 25", 6927.01, -21.17),
  NSEBSI: mkIndex("NSEBSI", "NSE BSI", 286.20, -2.32),
  MCAP:   mkIndex("MCAP",   "M.CAP",  4126.85,  8.21),
};

const mkMarket = (over: Partial<MarketOverviewDoc> = {}): MarketOverviewDoc => ({
  date: "2026-09-17",
  nse20_value: 4301.86,
  nse20_change_pct: -0.4158,
  signal_distribution: { BUY: 0, HOLD: 0, SELL: 0 },
  sector_performance: {},
  top_gainers: [],
  top_losers: [],
  indices: FULL_INDICES,
  ...over,
});

const wrap = (ui: React.ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>);

describe("MarketHeatmap", () => {
  it("renders the header + as-of date", () => {
    wrap(<MarketHeatmap market={mkMarket({ indices_updated_at: undefined })} companies={[mkCompany("ABSA", 5.3)]} />);
    expect(screen.getByText(/NSE Market Heatmap/i)).toBeInTheDocument();
    expect(screen.getByText(/as at 2026-09-17/)).toBeInTheDocument();
  });

  it("counts gainers, losers, unchanged and no-data buckets", () => {
    const companies = [
      mkCompany("A", 5), mkCompany("B", 2), mkCompany("C", -1),
      mkCompany("D", -6), mkCompany("E", 0), mkCompany("F", null),
    ];
    wrap(<MarketHeatmap market={mkMarket()} companies={companies} />);
    expect(screen.getByText("Gainers").nextSibling?.textContent).toBe("2");
    expect(screen.getByText("Losers").nextSibling?.textContent).toBe("2");
    expect(screen.getByText("Unchanged").nextSibling?.textContent).toBe("1");
    expect(screen.getByText(/No Data 1/)).toBeInTheDocument();
  });

  it("sorts tiles alphabetically by short", () => {
    const companies = [mkCompany("ZED", 1), mkCompany("ALP", 2), mkCompany("MID", 0)];
    wrap(<MarketHeatmap market={mkMarket()} companies={companies} />);
    const shorts = screen.getAllByRole("link").map(a => a.getAttribute("title"));
    expect(shorts[0]).toMatch(/^ALP/);
    expect(shorts[1]).toMatch(/^MID/);
    expect(shorts[2]).toMatch(/^ZED/);
  });

  it("tiles link to the chart route", () => {
    wrap(<MarketHeatmap market={mkMarket()} companies={[mkCompany("KCB", 1.5)]} />);
    expect(screen.getByRole("link", { name: /KCB/ })).toHaveAttribute("href", "/chart/KCB.NR");
  });

  it("renders all six official NSE indices with real values", () => {
    wrap(<MarketHeatmap market={mkMarket()} companies={[mkCompany("KCB", 0)]} />);
    // Labels — all six in the canonical NSE order.
    expect(screen.getByText("NASI")).toBeInTheDocument();
    expect(screen.getByText("NSE 20")).toBeInTheDocument();
    expect(screen.getByText("NSE 10")).toBeInTheDocument();
    expect(screen.getByText("NSE 25")).toBeInTheDocument();
    expect(screen.getByText("NSE BSI")).toBeInTheDocument();
    expect(screen.getByText("M.CAP")).toBeInTheDocument();
    // Values rendered via toLocaleString('en-KE') — comma-thousands, 2dp.
    expect(screen.getByText("4,301.86")).toBeInTheDocument();
    expect(screen.getByText("245.91")).toBeInTheDocument();
    expect(screen.getByText("2,703.13")).toBeInTheDocument();
    // Footer count includes real indices.
    expect(screen.getByText(/1 equities · 6 indices/)).toBeInTheDocument();
  });

  it("omits the indices row entirely when market.indices is absent (legacy doc)", () => {
    wrap(<MarketHeatmap market={mkMarket({ indices: undefined })} companies={[mkCompany("KCB", 0)]} />);
    expect(screen.queryByText(/NSE Share Indices/)).not.toBeInTheDocument();
    expect(screen.getByText(/1 equities · 0 indices/)).toBeInTheDocument();
  });

  it("renders only the indices actually present in the doc — no placeholders", () => {
    wrap(<MarketHeatmap market={mkMarket({ indices: { NASI: FULL_INDICES.NASI } })} companies={[mkCompany("KCB", 0)]} />);
    expect(screen.getByText("NASI")).toBeInTheDocument();
    expect(screen.queryByText("NSE 20")).not.toBeInTheDocument();
    expect(screen.queryByText("M.CAP")).not.toBeInTheDocument();
  });

  it("renders Flat label for zero change and ▲/▼ for signed moves", () => {
    const companies = [mkCompany("UP", 3.4), mkCompany("DN", -1.2), mkCompany("EQ", 0)];
    wrap(<MarketHeatmap market={mkMarket()} companies={companies} />);
    expect(screen.getByText(/▲\s+3\.40%/)).toBeInTheDocument();
    expect(screen.getByText(/▼\s+1\.20%/)).toBeInTheDocument();
    expect(screen.getAllByText(/^Flat$/).length).toBeGreaterThan(0);
  });
});
