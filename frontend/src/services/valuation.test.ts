import { describe, it, expect } from "vitest";
import {
  marketCap, sharesOutstanding, priceEarnings, priceToBook,
  latestAnnualEps, dividendYieldTtm,
} from "./valuation";
import { adjustmentFactor, adjustPrices, actionDateIndex } from "./corporateActions";
import type { FinancialsDoc } from "../types";

const bar = (date: string, close: number, volume: number | null = 100) => ({
  date, open: close, high: close, low: close, close, prevClose: close,
  change: null, changePct: null, volume, vwap: null,
});

describe("marketCap", () => {
  it("computes EQTY's real market cap from the RTDB close", () => {
    // 106.00 x 3,774mn shares ~ KES 400B, the TradingView figure.
    const mc = marketCap(106, 3774);
    expect(mc).toBeCloseTo(400_044_000_000, -6);
  });
  it("returns null — never zero — when either input is missing", () => {
    expect(marketCap(null, 3774)).toBeNull();
    expect(marketCap(106, null)).toBeNull();
  });
  it("returns null for non-positive inputs", () => {
    expect(marketCap(0, 3774)).toBeNull();
    expect(marketCap(106, 0)).toBeNull();
    expect(marketCap(-1, 3774)).toBeNull();
  });
  it("does not reproduce the stale-VWAP market cap", () => {
    // The 37.60 fallback produced 141.98B. With a null price we must get null.
    expect(marketCap(null, 3774)).not.toBe(141_982_400_000);
  });
});

describe("sharesOutstanding", () => {
  it("scales millions to an absolute count", () => {
    expect(sharesOutstanding(3774)).toBe(3_774_000_000);
  });
  it("returns null for missing or non-positive", () => {
    expect(sharesOutstanding(null)).toBeNull();
    expect(sharesOutstanding(0)).toBeNull();
  });
});

describe("ratios never render as 0.0x", () => {
  it("P/E is null when price is null — the ValuationPanel `?? 0` bug", () => {
    expect(priceEarnings(null, 5)).toBeNull();
    expect(priceEarnings(0, 5)).toBeNull();
  });
  it("P/E is null for a non-positive EPS rather than a negative multiple", () => {
    expect(priceEarnings(106, 0)).toBeNull();
    expect(priceEarnings(106, -2)).toBeNull();
  });
  it("computes a real P/E", () => {
    expect(priceEarnings(106, 10.6)).toBeCloseTo(10, 6);
  });
  it("P/B follows the same rules", () => {
    expect(priceToBook(106, null)).toBeNull();
    expect(priceToBook(106, 0)).toBeNull();
    expect(priceToBook(106, 53)).toBeCloseTo(2, 6);
  });
});

describe("latestAnnualEps", () => {
  const fin = {
    annual: [
      { period: "FY2024", period_end: "2024-12-31", eps: 10, bvps: 50 },
      { period: "FY2025", period_end: "2025-12-31", eps: 12, bvps: 60 },
      { period: "FY2026", period_end: "2026-12-31", eps: null, bvps: null },
    ],
    dividends: [], corporate_actions: [],
  } as unknown as FinancialsDoc;

  it("picks the newest period with a usable EPS and labels it", () => {
    expect(latestAnnualEps(fin)).toEqual({ value: 12, asOf: "2025-12-31", fiscalPeriod: "FY2025" });
  });
  it("returns null when no period has one", () => {
    expect(latestAnnualEps({ annual: [], dividends: [], corporate_actions: [] } as unknown as FinancialsDoc)).toBeNull();
  });
});

describe("dividendYieldTtm", () => {
  const fin = {
    annual: [], corporate_actions: [],
    dividends: [
      { announcement_date: "2026-06-01", type: "final", amount_kes: 5 },
      { announcement_date: "2019-06-01", type: "final", amount_kes: 99 }, // outside TTM
    ],
  } as unknown as FinancialsDoc;

  it("sums only the trailing twelve months", () => {
    const y = dividendYieldTtm(fin, 100, new Date("2026-09-06T00:00:00Z"));
    expect(y).toBeCloseTo(5, 6);
  });
  it("returns null on a null price instead of dividing by zero", () => {
    expect(dividendYieldTtm(fin, null, new Date("2026-09-06T00:00:00Z"))).toBeNull();
  });
  it("returns null when nothing was paid in the window", () => {
    expect(dividendYieldTtm(fin, 100, new Date("2021-01-01T00:00:00Z"))).toBeNull();
  });
});

describe("adjustmentFactor", () => {
  it("splits use old/new", () => {
    // 5 new for 1 old -> price basis one fifth.
    expect(adjustmentFactor({ date: "d", type: "split", ratio_new: 5, ratio_old: 1 } as never)).toBeCloseTo(0.2, 9);
  });
  it("bonuses use old/(old+new)", () => {
    // 1 for 5 held -> 6 shares per 5 -> 5/6.
    expect(adjustmentFactor({ date: "d", type: "bonus", ratio_new: 1, ratio_old: 5 } as never)).toBeCloseTo(5 / 6, 9);
  });
  it("ignores actions that do not move the price basis", () => {
    expect(adjustmentFactor({ date: "d", type: "dividend", ratio_new: 1, ratio_old: 5 } as never)).toBeNull();
    expect(adjustmentFactor({ date: "d", type: "agm" } as never)).toBeNull();
  });
  it("returns null on an unusable ratio rather than guessing", () => {
    expect(adjustmentFactor({ date: "d", type: "split", ratio_new: 0, ratio_old: 1 } as never)).toBeNull();
    expect(adjustmentFactor({ date: "d", type: "split", ratio_new: null, ratio_old: 1 } as never)).toBeNull();
  });
});

describe("adjustPrices", () => {
  const actions = [{ date: "2026-06-01", ex_date: "2026-06-01", type: "split", ratio_new: 2, ratio_old: 1 }] as never;

  it("scales bars before the ex-date and leaves later bars alone", () => {
    const out = adjustPrices([bar("2026-05-30", 200), bar("2026-06-01", 100)], actions);
    expect(out[0].close).toBeCloseTo(100, 9);  // 200 x 1/2
    expect(out[1].close).toBeCloseTo(100, 9);  // on/after ex-date, untouched
  });
  it("scales volume inversely so traded value is preserved", () => {
    const out = adjustPrices([bar("2026-05-30", 200, 50)], actions);
    expect(out[0].volume).toBeCloseTo(100, 9);
    expect(out[0].close! * out[0].volume!).toBeCloseTo(200 * 50, 6);
  });
  it("compounds multiple actions", () => {
    const two = [
      { date: "2026-06-01", ex_date: "2026-06-01", type: "split", ratio_new: 2, ratio_old: 1 },
      { date: "2026-03-01", ex_date: "2026-03-01", type: "split", ratio_new: 2, ratio_old: 1 },
    ] as never;
    const out = adjustPrices([bar("2026-01-01", 400)], two);
    expect(out[0].close).toBeCloseTo(100, 9);
  });
  it("is a no-op with no qualifying actions", () => {
    const bars = [bar("2026-05-30", 200)];
    expect(adjustPrices(bars, [])).toBe(bars);
    expect(adjustPrices(bars, [{ date: "2026-06-01", type: "agm" }] as never)).toBe(bars);
  });
});

describe("actionDateIndex", () => {
  it("prefers ex_date and falls back to date", () => {
    const idx = actionDateIndex([
      { date: "2026-01-01", ex_date: "2026-02-01", type: "split" },
      { date: "2026-03-01", type: "bonus" },
    ] as never);
    expect([...idx].sort()).toEqual(["2026-02-01", "2026-03-01"]);
  });
});
