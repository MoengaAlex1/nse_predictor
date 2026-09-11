import { describe, it, expect } from "vitest";
import { rangeOverDays, fiftyTwoWeekRange, positionInRange, returnOverDays } from "./series";
import { sharesOutstandingDated, missingReason } from "./valuation";
import type { Bar } from "./quotes";

const bar = (date: string, close: number | null): Bar => ({
  date, open: close, high: close, low: close, close, prevClose: close,
  change: null, changePct: null, volume: 1000, vwap: null,
});

const TODAY = "2026-09-06";

describe("fiftyTwoWeekRange", () => {
  const bars = [bar("2025-09-10", 53.75), bar("2026-06-03", 76.25), bar("2026-09-04", 106)];

  it("takes the high and low from the adjusted closes", () => {
    const r = fiftyTwoWeekRange(bars, TODAY);
    expect(r).toMatchObject({ high: 106, low: 53.75, observations: 3 });
  });

  it("does not reproduce the price_history decimal fault", () => {
    // companies.price_history stores 7,625.00 for 2026-06-03; RTDB has 76.25.
    // Reading the adjusted series means the bad value is simply never seen.
    expect(fiftyTwoWeekRange(bars, TODAY)!.high).toBe(106);
    expect(fiftyTwoWeekRange(bars, TODAY)!.high).not.toBe(7625);
  });

  it("excludes bars older than the window", () => {
    const r = fiftyTwoWeekRange([bar("2024-01-01", 5), ...bars], TODAY);
    expect(r!.low).toBe(53.75);
  });

  it("ignores bars with no close", () => {
    const r = fiftyTwoWeekRange([...bars, bar("2026-09-05", null)], TODAY);
    expect(r!.observations).toBe(3);
  });

  it("returns null on an empty window rather than a zero range", () => {
    expect(fiftyTwoWeekRange([], TODAY)).toBeNull();
    expect(fiftyTwoWeekRange([bar("2020-01-01", 10)], TODAY)).toBeNull();
  });
});

describe("rangeOverDays", () => {
  it("honours an arbitrary window", () => {
    const bars = [bar("2026-08-01", 90), bar("2026-09-04", 106)];
    expect(rangeOverDays(bars, 10, TODAY)!.observations).toBe(1);
    expect(rangeOverDays(bars, 60, TODAY)!.observations).toBe(2);
  });
});

describe("positionInRange", () => {
  it("places a price as a percentage of the range", () => {
    expect(positionInRange(75, { high: 100, low: 50, from: "a", to: "b", observations: 2 })).toBe(50);
  });
  it("returns null for a degenerate range or a null price", () => {
    expect(positionInRange(75, { high: 50, low: 50, from: "a", to: "b", observations: 1 })).toBeNull();
    expect(positionInRange(null, { high: 100, low: 50, from: "a", to: "b", observations: 2 })).toBeNull();
  });
});

describe("returnOverDays", () => {
  it("anchors on the last close at or before the cutoff", () => {
    const bars = [bar("2025-09-01", 100), bar("2026-06-01", 150), bar("2026-09-04", 200)];
    // 365d cutoff is 2025-09-06; the anchor is the 2025-09-01 bar.
    expect(returnOverDays(bars, 365, TODAY)).toBeCloseTo(100, 6);
  });
  it("returns null when there is not enough history", () => {
    expect(returnOverDays([bar("2026-09-04", 106)], 365, TODAY)).toBeNull();
    expect(returnOverDays([], 365, TODAY)).toBeNull();
  });
});

describe("sharesOutstandingDated", () => {
  it("carries the as-of date and source", () => {
    expect(sharesOutstandingDated({ shares_outstanding_mn: 3774, updated_at: "2026-08-01" }, "EQTY"))
      .toEqual({ value: 3_774_000_000, asOf: "2026-08-01", fiscalPeriod: null, source: "fundamentals/EQTY" });
  });
  it("returns null when the count is missing or non-positive", () => {
    expect(sharesOutstandingDated({ shares_outstanding_mn: null, updated_at: "x" })).toBeNull();
    expect(sharesOutstandingDated({ shares_outstanding_mn: 0, updated_at: "x" })).toBeNull();
    expect(sharesOutstandingDated(null)).toBeNull();
  });
});

describe("missingReason", () => {
  it("names the actual cause", () => {
    expect(missingReason(null, 10, "EPS")).toMatch(/No price/i);
    expect(missingReason(106, null, "EPS")).toMatch(/No EPS reported/i);
    expect(missingReason(106, -1, "EPS")).toMatch(/not positive/i);
  });
});
