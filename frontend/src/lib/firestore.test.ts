// Vite's ?raw import gives the module source as a string, which works under
// vitest's jsdom environment where import.meta.url is not a file:// URL.
import SOURCE from "./firestore.ts?raw";

/**
 * Guards the fix for the production outage where the home page rendered
 * "Failed to load market data".
 *
 * fetchMarketOverview / fetchLatestSnapshot / fetchLatestTechnicals each pick
 * the newest date-keyed document. Ordering those by `__name__` descending
 * requires an explicitly deployed Firestore index — and this repo deploys none
 * (firebase.json declares RTDB rules only, and there is no
 * firestore.indexes.json). The query therefore fails at runtime with
 * FAILED_PRECONDITION rather than at build or test time, which is why it
 * reached production unnoticed.
 *
 * Ordering on the real date field works with the automatic single-field index.
 * This is a source-level assertion because the failure mode lives in the query
 * shape, not in anything a Firestore mock would reproduce.
 */
describe("firestore query shapes", () => {
  it("never orders by __name__, which needs an undeployed index", () => {
    const offenders = SOURCE.split("\n")
      .map((line, i) => ({ line: line.trim(), n: i + 1 }))
      .filter(({ line }) => line.includes("orderBy") && line.includes("__name__"));

    expect(offenders).toEqual([]);
  });

  it("orders each date-keyed collection by its own date field", () => {
    expect(SOURCE).toMatch(/orderBy\("run_date", "desc"\)/); // snapshots
    expect(SOURCE).toMatch(/orderBy\("date", "desc"\)/); // technicals + market_overview
  });

  it("bounds every ordered query with a limit", () => {
    const unbounded = SOURCE.split("\n")
      .map((line) => line.trim())
      .filter((line) => line.includes("orderBy(") && !line.includes("limit("));

    expect(unbounded).toEqual([]);
  });
});
