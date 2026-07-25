import { render, screen } from "@testing-library/react";
import { SentimentDonut } from "./SentimentDonut";
import type { MarketOverviewDoc } from "../../types";

const mkMarket = (BUY: number, HOLD: number, SELL: number): MarketOverviewDoc => ({
  date: "2026-07-25", nse20_value: null, nse20_change_pct: null,
  top_gainers: [], top_losers: [],
  signal_distribution: { BUY, HOLD, SELL },
  sector_performance: {},
});

describe("SentimentDonut", () => {
  it("renders the Market Sentiment header", () => {
    render(<SentimentDonut market={mkMarket(42, 51, 24)} />);
    expect(screen.getByText("Market Sentiment")).toBeInTheDocument();
  });

  it("shows BUY / HOLD / SELL labels", () => {
    render(<SentimentDonut market={mkMarket(42, 51, 24)} />);
    expect(screen.getAllByText("BUY").length).toBeGreaterThan(0);
    expect(screen.getAllByText("HOLD").length).toBeGreaterThan(0);
    expect(screen.getAllByText("SELL").length).toBeGreaterThan(0);
  });

  it("shows count values", () => {
    render(<SentimentDonut market={mkMarket(42, 51, 24)} />);
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("51")).toBeInTheDocument();
    expect(screen.getByText("24")).toBeInTheDocument();
  });
});
