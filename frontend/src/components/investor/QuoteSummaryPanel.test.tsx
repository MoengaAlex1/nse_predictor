import { render, screen } from "@testing-library/react";
import { QuoteSummaryPanel } from "./QuoteSummaryPanel";
import type { CompanyDoc, TechnicalsDoc, FinancialsDoc, SnapshotDoc } from "../../types";

vi.mock("../../lib/firebase", () => ({ app: {}, db: {}, auth: {} }));

const baseCompany: CompanyDoc = {
  id: "COOP_NR",
  ticker: "COOP.NR",
  name: "Co-operative Bank",
  short: "COOP",
  sector: "Banking",
  color: "#34d399",
  icon: "🏦",
  csv: "COOP_NR_raw.csv",
  current_price: 13.5,
  change_pct_today: 1.2,
  signal: "BUY",
  price_history: [
    { date: "2025-08-01", price: 10.8 },
    { date: "2026-01-15", price: 14.2 },
    { date: "2026-07-24", price: 13.5 },
  ],
  price_preview: [],
  price_date: "2026-07-24",
  last_updated: "2026-07-24",
  price_status: null, price_status_date: null,
};

const baseTechnicals: TechnicalsDoc = {
  date: "2026-07-24",
  rsi_14: 52,
  macd: 0.1,
  macd_signal: 0.08,
  macd_hist: 0.02,
  bb_upper: 14.5,
  bb_mid: 13.5,
  bb_lower: 12.5,
  sma_20: 13.2,
  sma_50: 13.0,
  sma_200: 12.5,
  ema_12: 13.4,
  ema_26: 13.1,
  volume: 2410000,
  avg_volume_30d: 1830000,
  daily_return: 1.2,
  volatility_30d: 0.8,
  monthly_heatmap: {},
};

describe("QuoteSummaryPanel", () => {
  it("renders volume", () => {
    render(
      <QuoteSummaryPanel
        company={baseCompany}
        technicals={baseTechnicals}
        financials={null}
        snapshot={null}
      />,
    );
    expect(screen.getByText(/2\.41M|2,410,000/i)).toBeInTheDocument();
  });

  it("renders 52W high derived from price history", () => {
    render(
      <QuoteSummaryPanel
        company={baseCompany}
        technicals={baseTechnicals}
        financials={null}
        snapshot={null}
      />,
    );
    expect(screen.getByText(/14\.20/)).toBeInTheDocument();
  });

  it("renders 52W low derived from price history", () => {
    render(
      <QuoteSummaryPanel
        company={baseCompany}
        technicals={baseTechnicals}
        financials={null}
        snapshot={null}
      />,
    );
    expect(screen.getByText(/10\.80/)).toBeInTheDocument();
  });

  it("renders P/E when EPS available", () => {
    const financials: FinancialsDoc = {
      annual: [
        {
          period: "FY2024",
          period_end: "2024-12-31",
          period_type: "annual",
          announcement_date: "2025-03-15",
          revenue_kes_mn: 48000,
          net_income_kes_mn: 9600,
          eps: 1.63,
          bvps: 12.85,
        },
      ],
      dividends: [],
      corporate_actions: [],
      announcements: [],
    };
    render(
      <QuoteSummaryPanel
        company={baseCompany}
        technicals={baseTechnicals}
        financials={financials}
        snapshot={null}
      />,
    );
    // P/E = 13.50 / 1.63 ≈ 8.3×
    expect(screen.getByText(/8\.[0-9]+×/)).toBeInTheDocument();
  });

  it("renders ML consensus bar when snapshot model_breakdown provided", () => {
    const snapshot = {
      model_breakdown: {
        LSTM: { price: 14.8, signal: "BUY", pct: 9.6 },
        XGBoost: { price: 14.6, signal: "BUY", pct: 8.1 },
        ARIMA: { price: 13.8, signal: "HOLD", pct: 2.2 },
      },
    } as unknown as SnapshotDoc;
    render(
      <QuoteSummaryPanel
        company={baseCompany}
        technicals={baseTechnicals}
        financials={null}
        snapshot={snapshot}
      />,
    );
    expect(screen.getByText(/BUY 2/i)).toBeInTheDocument();
    expect(screen.getByText(/HOLD 1/i)).toBeInTheDocument();
  });

  it("does not render when current_price is null", () => {
    const { container } = render(
      <QuoteSummaryPanel
        company={{ ...baseCompany, current_price: null }}
        technicals={baseTechnicals}
        financials={null}
        snapshot={null}
      />,
    );
    expect(container.firstChild).toBeNull();
  });
});
