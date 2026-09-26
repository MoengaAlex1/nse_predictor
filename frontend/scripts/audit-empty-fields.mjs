#!/usr/bin/env node
/**
 * audit-empty-fields.mjs
 *
 * Loads the deployed site (or `--base http://localhost:5173`), visits
 * every /company/{TICKER} page, and reports every visible element whose
 * text matches an "empty" pattern (—, N/A, No data, 0 as placeholder …).
 * Also flags non-2xx API calls captured in the network log.
 *
 * Emits CSV to stdout with columns:
 *   page, ticker, section, field_label, displayed_value, api_endpoint, http_status
 *
 * Usage:
 *   npx playwright install chromium         # one-time
 *   node frontend/scripts/audit-empty-fields.mjs > audit.csv
 *   node frontend/scripts/audit-empty-fields.mjs --base https://nse-market-dashboard.pages.dev > audit.csv
 *   node frontend/scripts/audit-empty-fields.mjs --tickers ABSA,SCOM,EQTY
 *
 * The script is a real deliverable for the Phase-0 inventory step of
 * nse-intelligence-fix-prompt.md — the target is "zero rows" on rerun.
 */
import { chromium } from "playwright";
import { writeFileSync } from "node:fs";

const args = new Map();
for (let i = 2; i < process.argv.length; i += 2) {
  const key = process.argv[i]?.replace(/^--/, "");
  const val = process.argv[i + 1];
  if (key) args.set(key, val);
}
const BASE = args.get("base") ?? "https://nse-market-dashboard.pages.dev";
const TICKERS_ARG = args.get("tickers");
const OUT_PATH = args.get("out");

// Empty text patterns to hunt. Trimmed and lowercased for the match.
const EMPTY_PATTERNS = [
  "—", "–", "-", "n/a", "na", "null", "undefined", "nan",
  "no data available", "no data yet", "no buy signals",
  "0 securities tracked", "no estimate", "no analyst",
  "couldn't reach", "failed to load",
];

// A bare "0" is only a failure if it's inside a value cell. Skip legend-y
// contexts. This regex catches integer 0 with optional %/x/× suffix.
const ZERO_RE = /^\s*0(?:\.0+)?\s*[%x×]?\s*$/;

function isEmptyText(t) {
  if (!t) return false;
  const s = t.trim().toLowerCase();
  if (!s) return true;
  for (const p of EMPTY_PATTERNS) if (s === p || s.includes(p)) return true;
  // "0" as placeholder — only flag if it's alone in the cell.
  if (ZERO_RE.test(s)) return true;
  return false;
}

// Best-effort section + field labelling. Walks up ancestors to find a
// heading or aria-label, and pairs the empty value with the closest
// preceding label (definition-list style).
function sectionLabel(el) {
  let cur = el.parentElement;
  for (let depth = 0; depth < 6 && cur; depth += 1) {
    const heading = cur.querySelector?.("h1, h2, h3, [role=heading]");
    if (heading && heading.textContent?.trim()) return heading.textContent.trim().slice(0, 60);
    if (cur.getAttribute?.("aria-label")) return cur.getAttribute("aria-label").slice(0, 60);
    cur = cur.parentElement;
  }
  return "(unknown)";
}

function fieldLabel(el) {
  // Prefer an adjacent sibling label element (dt/label or bare span before
  // the value). Fall back to the value's own aria-label.
  if (el.getAttribute("aria-label")) return el.getAttribute("aria-label").slice(0, 80);
  const prev = el.previousElementSibling;
  if (prev && prev.textContent && prev.textContent.trim().length < 60) {
    return prev.textContent.trim();
  }
  const parent = el.parentElement;
  if (parent?.previousElementSibling?.textContent) {
    const t = parent.previousElementSibling.textContent.trim();
    if (t && t.length < 60) return t;
  }
  return "(unknown field)";
}

async function collectEmpties(page) {
  return page.evaluate(({ EMPTY_PATTERNS, ZERO_SRC }) => {
    const ZERO_RE = new RegExp(ZERO_SRC);
    const empty = (t) => {
      if (!t) return true;
      const s = t.trim().toLowerCase();
      if (!s) return true;
      for (const p of EMPTY_PATTERNS) if (s === p || s.includes(p)) return true;
      return ZERO_RE.test(s);
    };
    const results = [];
    // Leaf text nodes only — a parent whose text bubbles up from a child
    // shouldn't double-count. Limit to obvious value elements to keep the
    // noise down (span, dd, td, output).
    const candidates = document.querySelectorAll("span, dd, td, output, p, li");
    for (const el of candidates) {
      // Skip elements whose children have their own text — we only want
      // pure text leaves.
      if (el.children.length > 0) continue;
      const txt = el.textContent ?? "";
      if (!empty(txt)) continue;
      // Section: walk up to find a heading.
      let section = "(unknown)";
      let cur = el.parentElement;
      for (let d = 0; d < 6 && cur; d += 1) {
        const h = cur.querySelector("h1, h2, h3, [role=heading]");
        if (h && h.textContent?.trim()) { section = h.textContent.trim().slice(0, 60); break; }
        if (cur.getAttribute && cur.getAttribute("aria-label")) {
          section = cur.getAttribute("aria-label").slice(0, 60); break;
        }
        cur = cur.parentElement;
      }
      // Field label: adjacent sibling or aria-label.
      let field = el.getAttribute("aria-label") || "";
      if (!field && el.previousElementSibling) {
        const t = el.previousElementSibling.textContent?.trim();
        if (t && t.length < 60) field = t;
      }
      if (!field && el.parentElement?.previousElementSibling?.textContent) {
        const t = el.parentElement.previousElementSibling.textContent.trim();
        if (t && t.length < 60) field = t;
      }
      if (!field) field = "(unknown field)";
      results.push({ section, field, value: txt.trim().slice(0, 40) });
    }
    return results;
  }, { EMPTY_PATTERNS, ZERO_SRC: ZERO_RE.source });
}

function csvEscape(v) {
  const s = String(v ?? "");
  if (s.includes(",") || s.includes('"') || s.includes("\n")) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

async function main() {
  const rows = [];
  rows.push(["page", "ticker", "section", "field_label", "displayed_value", "api_endpoint", "http_status"].join(","));

  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1280, height: 950 } });
  const page = await context.newPage();

  // Discover tickers unless --tickers was provided.
  let tickers = TICKERS_ARG ? TICKERS_ARG.split(",").map(t => t.trim().toUpperCase()) : null;
  if (!tickers) {
    console.error(`Discovering tickers via ${BASE}/companies …`);
    await page.goto(`${BASE}/companies`, { waitUntil: "networkidle" });
    tickers = await page.evaluate(() =>
      Array.from(document.querySelectorAll("a[href^='/company/']"))
        .map(a => a.getAttribute("href").split("/").pop())
        .filter(Boolean)
    );
    tickers = Array.from(new Set(tickers)).sort();
    console.error(`Discovered ${tickers.length} tickers`);
  }

  const routes = [
    ["/", "-"],
    ["/screener", "-"],
    ...tickers.map(t => [`/company/${t}`, t]),
  ];

  for (const [route, ticker] of routes) {
    console.error(`Auditing ${route} …`);
    const apiFailures = [];
    const onResp = (resp) => {
      const url = resp.url();
      if (!url.includes("firestore") && !url.includes("firebaseio")) return;
      const status = resp.status();
      if (status >= 400) apiFailures.push({ url, status });
    };
    page.on("response", onResp);
    try {
      await page.goto(`${BASE}${route}`, { waitUntil: "networkidle", timeout: 30_000 });
      await page.waitForTimeout(1500);
      const empties = await collectEmpties(page);
      for (const e of empties) {
        rows.push([
          route,
          ticker,
          e.section,
          e.field,
          e.value,
          "",
          "",
        ].map(csvEscape).join(","));
      }
      for (const f of apiFailures) {
        rows.push([
          route,
          ticker,
          "network",
          "(api call)",
          "",
          f.url.replace(/^https?:\/\/[^/]+/, ""),
          f.status,
        ].map(csvEscape).join(","));
      }
    } catch (e) {
      console.error(`  route ${route} failed: ${e.message}`);
      rows.push([route, ticker, "route", "load", "", "", e.message.slice(0, 80)].map(csvEscape).join(","));
    } finally {
      page.off("response", onResp);
    }
  }

  await browser.close();

  const csv = rows.join("\n") + "\n";
  if (OUT_PATH) {
    writeFileSync(OUT_PATH, csv);
    console.error(`Wrote ${rows.length - 1} rows to ${OUT_PATH}`);
  } else {
    process.stdout.write(csv);
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
