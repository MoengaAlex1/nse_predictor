#!/usr/bin/env node
/**
 * Phase 0 task 6 — data and wiring validator.
 *
 * Two independent halves:
 *   A. STATIC  — no network. Fails if any component reads a price directly
 *      instead of going through services/quotes.ts. This is the check that
 *      keeps "one price accessor" true over time.
 *   B. DATA    — reads the public RTDB price tree and reports stale series,
 *      faulty bars and price sources in use.
 *
 * Exit code 1 if any ERROR-level finding is present, so CI fails the build.
 * Run:  node scripts/validate-data.mjs [--json]
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const RTDB = process.env.VITE_FIREBASE_DATABASE_URL
  ?? "https://nse-market-dashboard-default-rtdb.firebaseio.com";
const SRC = new URL("../src", import.meta.url).pathname;
const STALE_AFTER_DAYS = 3;
const MAX_SESSION_MOVE = 0.35;
/** An indicator further than this multiple from the last close is suspect. */
const INDICATOR_SANITY_MULTIPLE = 3;

const errors = [];
const warnings = [];
const err  = (check, detail) => errors.push({ level: "ERROR", check, ...detail });
const warn = (check, detail) => warnings.push({ level: "WARN", check, ...detail });

// ── A. Static wiring guard ────────────────────────────────────────────────

/** Reading these outside the service layer reintroduces the split-truth bug. */
const FORBIDDEN = [
  { re: /\bcurrent_price\b/,            what: "companies.current_price (null for all 61 tickers)" },
  { re: /\blast_known_price\b/,         what: "companies.last_known_price (VWAP dated 2023-09-30)" },
  { re: /shares_outstanding_mn\s*\*/,   what: "an inline market-cap computation" },
];
/**
 * Exempt: the service layer itself, the type declarations, the tests, and
 * lib/firestore.ts — whose `current_price` mention is the DTO passthrough in
 * normalizeCompany, not a display read.
 */
const EXEMPT = [/^services\//, /^hooks\/useQuotes\.ts$/, /^types\//, /\.test\.tsx?$/,
                /^lib\/firestore\.ts$/];

/**
 * Blank out comment spans so prose about these fields is not reported as a
 * read. Block comments span lines (JSX `{/* ... *\/}` especially), so a
 * per-line "starts with //" test is not enough. Newlines are preserved so
 * line numbers stay correct.
 */
function stripComments(src) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " "))
    .replace(/\/\/[^\n]*/g, (m) => " ".repeat(m.length));
}

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.tsx?$/.test(p)) out.push(p);
  }
  return out;
}

function staticGuard() {
  for (const file of walk(SRC)) {
    const rel = relative(SRC, file);
    if (EXEMPT.some((re) => re.test(rel))) continue;
    const lines = stripComments(readFileSync(file, "utf8")).split("\n");
    lines.forEach((line, i) => {
      for (const { re, what } of FORBIDDEN) {
        if (re.test(line)) {
          err("static/price-access", {
            file: `src/${rel}`, line: i + 1, detail: `reads ${what}`,
            fix: "use services/quotes.ts (getQuote/useQuote) or services/valuation.ts",
          });
        }
      }
    });
  }
}

// ── B. Live data checks ───────────────────────────────────────────────────

const isoToday = () => new Date().toISOString().slice(0, 10);

function tradingDaysBetween(fromIso, toIso) {
  const from = new Date(`${fromIso}T00:00:00Z`), to = new Date(`${toIso}T00:00:00Z`);
  if (Number.isNaN(+from) || Number.isNaN(+to) || to <= from) return 0;
  let n = 0; const cur = new Date(from); cur.setUTCDate(cur.getUTCDate() + 1);
  while (cur <= to) { const d = cur.getUTCDay(); if (d !== 0 && d !== 6) n++; cur.setUTCDate(cur.getUTCDate() + 1); }
  return n;
}

async function json(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${url}`);
  return res.json();
}

function classify(bar) {
  if (bar.c != null && bar.v != null && bar.v > 0) return "trade";
  if (bar.c == null && bar.vv != null) return "vwap";
  if (bar.c != null) return "carry-forward";
  return "none";
}

async function dataChecks() {
  const tickers = Object.keys(await json(`${RTDB}/prices.json?shallow=true`)).sort();
  const today = isoToday();
  const sources = {};
  const rows = [];

  for (const t of tickers) {
    const bars = await json(`${RTDB}/prices/${t}.json?orderBy=%22%24key%22&limitToLast=20`);
    if (!bars || Object.keys(bars).length === 0) {
      err("data/no-series", { ticker: t, detail: "no price bars at all" });
      continue;
    }
    const dates = Object.keys(bars).sort();
    const lastDate = dates[dates.length - 1];
    const last = bars[lastDate];
    const source = classify(last);
    sources[source] = (sources[source] ?? 0) + 1;

    const staleDays = tradingDaysBetween(lastDate, today);
    if (staleDays > STALE_AFTER_DAYS) {
      warn("data/stale", { ticker: t, detail: `newest bar ${lastDate}, ${staleDays} trading days old` });
    }
    if (source === "none") {
      err("data/unusable-bar", { ticker: t, detail: `newest bar ${lastDate} has neither close nor vwap` });
    }

    for (const d of dates) {
      const b = bars[d];
      if (b?.c == null || b?.pc == null || b.pc <= 0) continue;
      if (Math.abs(b.c - b.pc) > MAX_SESSION_MOVE * b.pc) {
        err("data/faulty-bar", {
          ticker: t, detail: `${d}: close ${b.c} vs prevClose ${b.pc} ` +
            `(${(((b.c / b.pc) - 1) * 100).toFixed(1)}%) with no corporate action`,
        });
      }
      // A low above the high, or a high/low miles from the close, is a bad tick.
      if (b.h != null && b.l != null && b.l > b.h) {
        err("data/ohlc-inverted", { ticker: t, detail: `${d}: low ${b.l} above high ${b.h}` });
      }
      if (b.c > 0 && b.l != null && b.l > 0 && b.c / b.l > INDICATOR_SANITY_MULTIPLE) {
        warn("data/suspect-low", { ticker: t, detail: `${d}: low ${b.l} vs close ${b.c}` });
      }
    }
    rows.push({ ticker: t, lastDate, close: last.c, source, staleDays });
  }
  return { rows, sources, tickerCount: tickers.length };
}

// ── Report ────────────────────────────────────────────────────────────────

const asJson = process.argv.includes("--json");

staticGuard();
let data = { rows: [], sources: {}, tickerCount: 0 };
try {
  data = await dataChecks();
} catch (e) {
  err("data/unreachable", { detail: `RTDB read failed: ${e.message}` });
}

if (asJson) {
  console.log(JSON.stringify({ errors, warnings, summary: data }, null, 2));
} else {
  console.log(`\nvalidate-data — ${data.tickerCount} price series, sources:`,
    Object.entries(data.sources).map(([k, v]) => `${k}=${v}`).join("  ") || "n/a");
  const show = (list) => list.forEach((f) => console.log(
    `  ${f.level.padEnd(5)} ${f.check.padEnd(22)} ${f.ticker ?? f.file ?? ""}${f.line ? ":" + f.line : ""}  ${f.detail}`));
  if (warnings.length) { console.log(`\n${warnings.length} warning(s):`); show(warnings); }
  if (errors.length)   { console.log(`\n${errors.length} error(s):`);   show(errors); }
  if (!errors.length && !warnings.length) console.log("\n  all checks passed");
  console.log();
}

process.exit(errors.length > 0 ? 1 : 0);
