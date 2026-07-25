import { render, screen } from "@testing-library/react";
import { SectorPerformance } from "./SectorPerformance";
import type { MarketOverviewDoc } from "../../types";

const mkMarket = (sectors: Record<string, number>): MarketOverviewDoc => ({
  date: "2026-07-25", nse20_value: null, nse20_change_pct: null,
  top_gainers: [], top_losers: [],
  signal_distribution: { BUY: 0, HOLD: 0, SELL: 0 },
  sector_performance: sectors,
});

describe("SectorPerformance", () => {
  it("renders the header", () => {
    render(<SectorPerformance market={mkMarket({ Banking: 1.2 })} />);
    expect(screen.getByText(/Sector Performance/i)).toBeInTheDocument();
  });

  it("shows sector names", () => {
    render(<SectorPerformance market={mkMarket({ Banking: 1.2, Insurance: -0.5 })} />);
    expect(screen.getByText("Banking")).toBeInTheDocument();
    expect(screen.getByText("Insurance")).toBeInTheDocument();
  });

  it("shows performance values with sign", () => {
    render(<SectorPerformance market={mkMarket({ Banking: 1.2, Insurance: -0.5 })} />);
    expect(screen.getByText("+1.2%")).toBeInTheDocument();
    expect(screen.getByText("-0.5%")).toBeInTheDocument();
  });

  it("renders nothing when sector_performance is empty", () => {
    const { container } = render(<SectorPerformance market={mkMarket({})} />);
    expect(container.firstChild).toBeNull();
  });
});
