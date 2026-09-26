import { describe, it, expect } from "vitest";

// Consistency invariants required by nse-intelligence-fix-prompt.md
// Phase 2 items 2 and 3. Kept in a small pure-math file so any future
// component that renders a target price OR a price range can import
// these helpers and share the contract.

// ---- Target math (Phase 2 #2) ------------------------------------------
// Exactly one relationship holds between (currentPrice, target, pct):
//   pct = (target / currentPrice - 1) * 100
// The prompt was explicit: "The percentage must equal (target / last price
// − 1). Add a unit test for this." — so the UI must not carry a
// pre-computed pct string that drifts from the arithmetic.
export function targetPct(currentPrice: number, target: number): number {
  if (currentPrice <= 0) throw new Error("currentPrice must be > 0");
  return (target / currentPrice - 1) * 100;
}

describe("targetPct", () => {
  it("matches (target/current - 1) * 100 exactly", () => {
    expect(targetPct(100, 110)).toBeCloseTo(10, 8);
    expect(targetPct(100, 90)).toBeCloseTo(-10, 8);
    expect(targetPct(33.4, 28.42)).toBeCloseTo(-14.910, 3);
  });

  it("throws on non-positive currentPrice (division-by-zero guard)", () => {
    expect(() => targetPct(0, 100)).toThrow();
    expect(() => targetPct(-5, 100)).toThrow();
  });
});

// ---- Range order (Phase 2 #3) ------------------------------------------
// Every rendered range must satisfy:
//   dayLow >= 52wLow
//   dayHigh <= 52wHigh
//   3M high <= 52w high
//   3M low  >= 52w low
// A ticker whose 3M window straddles the 52w extremes is a data bug in
// upstream ingest; the UI must not paper over it. checkRangeInvariants
// returns the list of violated invariants for a ticker.
export type RangeSnapshot = {
  ticker: string;
  dayLow: number;
  dayHigh: number;
  threeMLow: number;
  threeMHigh: number;
  weekLow52: number;
  weekHigh52: number;
};

export function checkRangeInvariants(r: RangeSnapshot): string[] {
  const bad: string[] = [];
  if (r.dayLow < r.weekLow52) bad.push("dayLow < weekLow52");
  if (r.dayHigh > r.weekHigh52) bad.push("dayHigh > weekHigh52");
  if (r.threeMHigh > r.weekHigh52) bad.push("threeMHigh > weekHigh52");
  if (r.threeMLow < r.weekLow52) bad.push("threeMLow < weekLow52");
  if (r.dayLow > r.dayHigh) bad.push("dayLow > dayHigh");
  if (r.threeMLow > r.threeMHigh) bad.push("threeMLow > threeMHigh");
  if (r.weekLow52 > r.weekHigh52) bad.push("weekLow52 > weekHigh52");
  return bad;
}

describe("checkRangeInvariants", () => {
  const base: RangeSnapshot = {
    ticker: "SCOM",
    dayLow: 12.0, dayHigh: 12.5,
    threeMLow: 11.5, threeMHigh: 13.0,
    weekLow52: 11.0, weekHigh52: 15.0,
  };

  it("returns no violations on a self-consistent snapshot", () => {
    expect(checkRangeInvariants(base)).toEqual([]);
  });

  it("catches dayLow below 52w low", () => {
    expect(checkRangeInvariants({ ...base, dayLow: 10.9 })).toContain("dayLow < weekLow52");
  });

  it("catches dayHigh above 52w high", () => {
    expect(checkRangeInvariants({ ...base, dayHigh: 15.1 })).toContain("dayHigh > weekHigh52");
  });

  it("catches 3M high above 52w high", () => {
    expect(checkRangeInvariants({ ...base, threeMHigh: 15.1 })).toContain("threeMHigh > weekHigh52");
  });

  it("catches inverted single-range pairs", () => {
    expect(checkRangeInvariants({ ...base, dayLow: 12.6 })).toContain("dayLow > dayHigh");
  });
});
