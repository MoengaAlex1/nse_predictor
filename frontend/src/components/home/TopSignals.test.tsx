import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { TopSignals } from "./TopSignals";
import type { CompanyDoc } from "../../types";
import type { Quote } from "../../services/quotes";

const mkCompany = (ticker: string, signal: "BUY" | "HOLD" | "SELL", pct: number, price = 10): CompanyDoc => ({
  id: `${ticker}.NR`, ticker, short: ticker.toLowerCase(), color: "#fff", icon: "🏢",
  name: `${ticker} Ltd`, sector: "Banking", current_price: price, change_pct_today: pct,
  signal, price_history: [], price_preview: [], price_date: null, last_updated: null, csv: "",
});


// Price and change now come from the quotes service, so the fixtures supply a
// matching quote per company rather than relying on company.current_price.
const mkQuotes = (companies: CompanyDoc[]): Map<string, Quote> =>
  new Map(companies.map((c) => [c.id, {
    ticker: c.id, date: "2026-09-04",
    open: null, high: null, low: null,
    close: c.current_price, prevClose: null,
    change: null, changePct: c.change_pct_today,
    volume: null, vwap: null,
    isStale: false, staleDays: 0, source: "trade" as const,
  }]));

const wrap = (ui: React.ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>);

describe("TopSignals", () => {
  it("renders the header", () => {
    wrap(<TopSignals companies={[mkCompany("SCOM", "BUY", 3.2)]} quotes={mkQuotes([mkCompany("SCOM", "BUY", 3.2)])} />);
    expect(screen.getByText("Top BUY Signals")).toBeInTheDocument();
  });

  it("only shows BUY signal companies", () => {
    const companies = [
      mkCompany("SCOM", "BUY", 3.2),
      mkCompany("EABL", "HOLD", -1.0),
      mkCompany("KCB", "SELL", -2.0),
    ];
    wrap(<TopSignals companies={companies} quotes={mkQuotes(companies)} />);
    expect(screen.getByText("scom")).toBeInTheDocument();
    expect(screen.queryByText("eabl")).not.toBeInTheDocument();
    expect(screen.queryByText("kcb")).not.toBeInTheDocument();
  });

  it("links each row to the investor chart", () => {
    wrap(<TopSignals companies={[mkCompany("SCOM", "BUY", 3.2)]} quotes={mkQuotes([mkCompany("SCOM", "BUY", 3.2)])} />);
    expect(screen.getByRole("link")).toHaveAttribute("href", "/chart/SCOM");
  });

  it("limits to 5 picks", () => {
    const companies = Array.from({ length: 8 }, (_, i) =>
      mkCompany(`CO${i}`, "BUY", i * 0.5)
    );
    wrap(<TopSignals companies={companies} quotes={mkQuotes(companies)} />);
    expect(screen.getAllByRole("link")).toHaveLength(5);
  });

  it("shows empty message when no BUY signals", () => {
    wrap(<TopSignals companies={[mkCompany("EABL", "HOLD", -1.0)]} quotes={mkQuotes([mkCompany("EABL", "HOLD", -1.0)])} />);
    expect(screen.getByText("No BUY signals")).toBeInTheDocument();
  });
});
