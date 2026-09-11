import { describe, it, expect, vi, beforeEach } from "vitest";

const mockGet = vi.fn();

// The real module initialises a Firebase app from import.meta.env, which is
// empty under vitest. Stub the handle; only `get` behaviour matters here.
vi.mock("../lib/rtdb", () => ({ rtdb: {} }));
vi.mock("firebase/database", () => ({
  ref: (_db: unknown, path: string) => path,
  query: (path: string) => path,
  orderByKey: () => "orderByKey",
  startAt: (v: string) => v,
  endAt: (v: string) => v,
  limitToLast: (n: number) => n,
  get: (...args: unknown[]) => mockGet(...args),
}));

import {
  getQuote, getQuotes, getHistory, isFaultyBar, tradingDaysBetween,
  MAX_SESSION_MOVE, STALE_AFTER_DAYS,
} from "./quotes";

const snap = (val: unknown) => ({ exists: () => val != null, val: () => val });
// Raw RTDB bar shape — what the mocked `get` returns.
const bar = (o: Partial<Record<string, number | null>>) => ({
  o: null, h: null, l: null, c: null, v: null, pc: null, ch: null, pch: null, vv: null, ...o,
});
// Normalised Bar shape — what isFaultyBar actually consumes.
const mkBar = (date: string, close: number | null, prevClose: number | null) => ({
  date, open: null, high: null, low: null, close, prevClose,
  change: null, changePct: null, volume: null, vwap: null,
});

beforeEach(() => mockGet.mockReset());

describe("tradingDaysBetween", () => {
  it("counts weekdays only", () => {
    // Fri 2026-09-04 -> Mon 2026-09-07 is one trading day, not three.
    expect(tradingDaysBetween("2026-09-04", "2026-09-07")).toBe(1);
  });
  it("is zero for the same day and for reversed ranges", () => {
    expect(tradingDaysBetween("2026-09-04", "2026-09-04")).toBe(0);
    expect(tradingDaysBetween("2026-09-07", "2026-09-04")).toBe(0);
  });
});

describe("isFaultyBar", () => {
  it("rejects a move beyond the threshold with no corporate action", () => {
    // The EQTY 7,625-against-106 class of bad tick.
    expect(isFaultyBar(mkBar("2026-09-04", 7625, 106))).toBe(true);
  });
  it("keeps the same move when a corporate action is recorded that day", () => {
    const b = mkBar("2026-09-04", 53, 106);   // -50%, a 1:2 split shape
    expect(isFaultyBar(b)).toBe(true);
    expect(isFaultyBar(b, new Set(["2026-09-04"]))).toBe(false);
  });
  it("keeps an ordinary move", () => {
    expect(isFaultyBar(mkBar("2026-09-04", 106, 105))).toBe(false);
  });
  it("keeps a move exactly at the threshold", () => {
    expect(isFaultyBar(mkBar("2026-09-04", 135, 100))).toBe(false);   // +35%
    expect(isFaultyBar(mkBar("2026-09-04", 135.5, 100))).toBe(true);  // +35.5%
  });
  it("does not reject when prevClose is missing or non-positive", () => {
    expect(isFaultyBar(mkBar("d", 106, null))).toBe(false);
    expect(isFaultyBar(mkBar("d", 106, 0))).toBe(false);
  });
  it("does not reject when close is missing", () => {
    expect(isFaultyBar(mkBar("d", null, 106))).toBe(false);
  });
  it("threshold is 35%", () => expect(MAX_SESSION_MOVE).toBe(0.35));
});

describe("getQuote", () => {
  it("tags a traded bar as 'trade' and reads the real EQTY close", async () => {
    mockGet.mockResolvedValue(snap({
      "2026-09-03": bar({ c: 105, pc: 100, v: 5240438, ch: 5, pch: 5 }),
      "2026-09-04": bar({ c: 106, pc: 105, v: 4294031, ch: 1, pch: 0.9524, o: 106, h: 108, l: 105 }),
    }));
    const q = await getQuote("EQTY", { today: "2026-09-04" });
    expect(q).toMatchObject({
      ticker: "EQTY", date: "2026-09-04", close: 106, prevClose: 105,
      volume: 4294031, source: "trade", isStale: false, staleDays: 0,
    });
    expect(q!.changePct).toBeCloseTo(0.9524, 4);
  });

  it("tags a zero-volume bar as 'carry-forward'", async () => {
    mockGet.mockResolvedValue(snap({
      "2026-09-04": bar({ c: 106, pc: 106, v: 0 }),
    }));
    const q = await getQuote("EQTY", { today: "2026-09-04" });
    expect(q!.source).toBe("carry-forward");
    expect(q!.close).toBe(106);
  });

  it("tags a closeless bar carrying a VWAP as 'vwap'", async () => {
    mockGet.mockResolvedValue(snap({ "2026-09-04": bar({ c: null, vv: 99.5 }) }));
    const q = await getQuote("EQTY", { today: "2026-09-04" });
    expect(q!.source).toBe("vwap");
    expect(q!.close).toBe(99.5);
  });

  it("marks a quote stale past the trading-day threshold", async () => {
    mockGet.mockResolvedValue(snap({ "2026-08-20": bar({ c: 100, pc: 99, v: 10 }) }));
    const q = await getQuote("EQTY", { today: "2026-09-04" });
    expect(q!.staleDays).toBeGreaterThan(STALE_AFTER_DAYS);
    expect(q!.isStale).toBe(true);
  });

  it("skips a faulty bar and falls back to the last clean one", async () => {
    mockGet.mockResolvedValue(snap({
      "2026-09-03": bar({ c: 106, pc: 105, v: 4294031 }),
      "2026-09-04": bar({ c: 7625, pc: 106, v: 100 }),  // bad tick
    }));
    const q = await getQuote("EQTY", { today: "2026-09-04" });
    expect(q!.close).toBe(106);
    expect(q!.date).toBe("2026-09-03");
  });

  it("returns null rather than a zero when nothing is usable", async () => {
    mockGet.mockResolvedValue(snap(null));
    expect(await getQuote("EQTY", { today: "2026-09-04" })).toBeNull();
  });

  it("accepts a display ticker and canonicalises it", async () => {
    mockGet.mockResolvedValue(snap({ "2026-09-04": bar({ c: 106, pc: 105, v: 10 }) }));
    const q = await getQuote("EQTY.NR", { today: "2026-09-04" });
    expect(q!.ticker).toBe("EQTY");
  });

  it("never reads the stale Firestore VWAP tier", async () => {
    // Only RTDB is consulted; the 37.60 / 2023-09-30 fallback cannot appear.
    mockGet.mockResolvedValue(snap(null));
    expect(await getQuote("EQTY", { today: "2026-09-04" })).toBeNull();
    expect(mockGet).toHaveBeenCalledTimes(1);
  });
});

describe("getQuotes", () => {
  it("batches, dedupes and keys by canonical ticker", async () => {
    mockGet.mockResolvedValue(snap({ "2026-09-04": bar({ c: 10, pc: 9, v: 5 }) }));
    const m = await getQuotes(["EQTY", "EQTY.NR", "KCB"], { today: "2026-09-04" });
    expect([...m.keys()].sort()).toEqual(["EQTY", "KCB"]);
    expect(mockGet).toHaveBeenCalledTimes(2);
  });

  it("one failing ticker does not sink the batch", async () => {
    mockGet
      .mockRejectedValueOnce(new Error("permission denied"))
      .mockResolvedValueOnce(snap({ "2026-09-04": bar({ c: 10, pc: 9, v: 5 }) }));
    const m = await getQuotes(["AAAA", "KCB"], { today: "2026-09-04" });
    expect(m.has("KCB")).toBe(true);
    expect(m.has("AAAA")).toBe(false);
  });
});

describe("getHistory", () => {
  it("returns a sorted series with faulty bars removed", async () => {
    mockGet.mockResolvedValue(snap({
      "2026-09-04": bar({ c: 7625, pc: 106 }),
      "2026-09-02": bar({ c: 100, pc: 96.25 }),
      "2026-09-03": bar({ c: 105, pc: 100 }),
    }));
    const h = await getHistory("EQTY", { from: "2026-09-01", to: "2026-09-04" });
    expect(h.map((b) => b.date)).toEqual(["2026-09-02", "2026-09-03"]);
  });

  it("keeps the faulty bar when a corporate action explains it", async () => {
    mockGet.mockResolvedValue(snap({ "2026-09-04": bar({ c: 53, pc: 106 }) }));
    const h = await getHistory("EQTY", { from: "2026-09-01", to: "2026-09-04" },
      { actions: new Set(["2026-09-04"]) });
    expect(h).toHaveLength(1);
  });
});
