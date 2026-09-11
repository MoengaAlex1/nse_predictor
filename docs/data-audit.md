# Phase 0 · Task 1 — Price & market-cap data audit

**Date:** 2026-09-06 · **Branch:** `phase0/data-audit` · **Base:** `cfb5dcc`
**Status:** inventory only — no code changed.

---

## Headline

The premise in the build plan was that different components *compute* prices differently.
They do — but that is the second-order problem. The first-order problem is:

> **Every one of the 61 `companies/*` documents in Firestore has `current_price = null`,
> `change_pct_today = null` and `signal = null`. The correct prices are in RTDB and are
> current. The Firestore mirror is dead, and the pipeline that fills it reports success.**

Verified live against `projects/nse-market-dashboard` on 2026-09-06:

| Check | Result |
|---|---|
| `companies/*` docs total | 61 |
| `current_price IS NULL` | **61 / 61** |
| `change_pct_today IS NULL` | **61 / 61** |
| `signal IS NULL` | **61 / 61** |
| `last_known_price_as_of` older than 2025 | **50 / 61** |
| `companies/EQTY.last_known_price` | **37.60**, as-of **2023-09-30** |
| RTDB `prices/EQTY` latest bar (2026-09-04) | **c 106.00**, pc 105.00, +0.95%, vol 4,294,031 |

So the 37.60 on `/screener` is a **three-year-old VWAP fallback**, and the 106.00 on
`/company/EQTY` is RTDB. Both routes are "working as written"; they just read different
tiers of the same broken ladder.

This one fact also explains defects the plan assigns to later phases:

- Home page "TOP GAINERS 0 of 61 / TOP LOSERS 0 of 61" — `change_pct_today` is null for all 61,
  so movers cannot rank. (Plan assigns this to Phase 6 as an "aggregation bug"; it is not.)
- "TOP BUY SIGNALS 0 picks" — `signal` is null for all 61.
- The sentiment donut still showing 15 BUY / 1 HOLD / 40 SELL — it reads `market_overview`,
  written by an older run, so it is stale rather than wrong-by-computation. That is the
  reconciliation mismatch Phase 6 describes.

---

## Why the mirror is null while CI is green

`pipeline/scripts/run_daily_update.py` builds a correct payload
(`public_update.current_price` at line 431) and logs `"Written to Firestore"` at line 546.

But the per-ticker handler ends with:

```python
except Exception as exc:
    log.error("FAILED %s: %s", ticker, exc, exc_info=True)
    return None
```

A ticker that throws is logged and dropped. Nothing re-raises, and the process exit code is
unaffected. If every ticker throws, `results` is empty, zero documents are written, and the
workflow still reports **success**.

That matches observation: `daily_update.yml`, `daily_price_update.yml` and `price_update.yml`
are all green on their last 4 scheduled runs, while all 61 documents hold nulls.

**Not yet established:** *which* exception each ticker hits. That needs the run logs and is
the first thing to pin down before writing `quotes.ts`.

---

## Inventory — every price / market-cap read site

Fallback ladders are the thing to read here. There are **six different ones** for the same number.

| # | File : line | Reads | Ladder / transform | What it renders today for EQTY |
|---|---|---|---|---|
| 1 | `pages/Screener.tsx:43` | `current_price`, `last_known_price` | `current_price ?? last_known_price` | **37.60** (2023 VWAP) |
| 2 | `pages/CompanyDeepDive.tsx:1305` | `current_price`, RTDB latest | `current_price ?? rtdbLatest.c` | **106.00** (correct) |
| 3 | `pages/CompanyDeepDive.tsx:1357` | `current_price` | none — `!== null` guard | em dash |
| 4 | `pages/InvestorChart.tsx:136` | `current_price`, RTDB latest | `current_price ?? latestRow.c` | 106.00 |
| 5 | `pages/InvestorDashboard.tsx:88` | `current_price`, RTDB latest | `current_price ?? latestRow.c` | 106.00 |
| 6 | `components/investor/ValuationPanel.tsx:49` | `current_price` | **`current_price ?? 0`** | **0** → drives `0.0×` P/E |
| 7 | `components/investor/PriceRangeCard.tsx:33` | `current_price`, `price_history`, `last_known_price` | 3-tier ladder | last history point |
| 8 | `components/layout/RightStatsRail.tsx:73` | `current_price` | none | em dash |
| 9 | `components/investor/QuoteSummaryPanel.tsx:44` | `current_price` | early-returns `null` | panel hidden |
| 10 | `components/home/TopSignals.tsx:9` | `current_price`, `signal` | filters `signal === "BUY" && price != null` | **0 rows** |
| 11 | `components/home/MoversTable.tsx:99` | `current_price` | null guard | blank |
| 12 | `components/layout/LeftWatchlistRail.tsx:54` | `current_price` | null guard → em dash | em dash |
| 13 | `pages/Companies.tsx:206` | `current_price` | `typeof === "number"` guard | hidden |
| 14 | `components/ui/PeerChip.tsx:27` | `current_price` | null guard → em dash | em dash |
| 15 | `lib/firestore.ts:33` | `current_price` | `?? null` in `normalizeCompany` | null |

### Market cap — two independent formulas

| File : line | Formula | Price tier used |
|---|---|---|
| `pages/Screener.tsx:49` | `price * shares_outstanding_mn * 1e6` | `current_price ?? last_known_price` |
| `components/layout/RightStatsRail.tsx:78` | `currentPrice * shares_outstanding_mn * 1e6` | `current_price` only |

Same multiplier, different price tier — which is exactly why one route shows KES 141.98B
(37.60 × 3.78B) and the other shows an em dash. Neither is wrong in isolation.

### The `0.0×` ratios

`ValuationPanel.tsx:49` — `const price = company.current_price ?? 0` — is the direct cause.
A null price becomes `0`, and `0 / eps` renders as `0.0×`. Phase 0 task 5 (return `null`,
render an em dash) fixes this, but only once the price itself is real.

### Read-path asymmetry

| Route | Accessor | Shape |
|---|---|---|
| `/screener`, `/`, watchlist | `fetchAllCompanies()` (`lib/firestore.ts:41`) | `getDocs(collection)` — whole-collection scan |
| `/company/:ticker` | `fetchCompany(id)` (`lib/firestore.ts:64`) | `getDoc(doc)` — single document |
| chart / history | `useHistoricalPrices` | RTDB `prices/{ticker}`, keyed by date |

Both Firestore paths run through `normalizeCompany`, so id handling is consistent. The
divergence is purely in the per-component fallback ladders above, plus the RTDB tier that
only three call sites know about.

---

## Collections in use

`companies` · `financials` · `fundamentals` · `market_overview` · `events` · `macro` · `users`
RTDB: `prices/{ticker}/{YYYY-MM-DD}` → `{o,h,l,c,pc,ch,pch,v}`

---

## What this means for the rest of Phase 0

The task list says to build `src/services/quotes.ts` as the only price accessor. That is
still right, but the source it reads matters:

- **Building `quotes.ts` over `companies.current_price` would return null for all 61 tickers.**
  RTDB `prices/{ticker}` is the only tier that currently holds correct, current data, and it
  already carries `o/h/l/c/pc/ch/pch/v` — everything `getQuote()` is specified to return.
- So `quotes.ts` should read RTDB as the price source of truth, **or** the pipeline write must
  be repaired first. These are different amounts of work and I'd like your call on which.
- The `> 0.35` move rejection and the corporate-actions adjustment (tasks 2–3) should be
  applied to the RTDB series, since that is what the indicators already consume.
- Task 6's cross-route mismatch check would currently fail on all 61 tickers, which is the
  correct behaviour — it should stay failing until the pipeline is fixed.

## Claims from the plan I could not verify

Stated in the plan but **not** confirmed in this pass — they need the `technicals` collection,
which I did not query:

- EQTY 52-week high rendering as KES 7,625.00
- EQTY SMA200 of KES 187.66
- Screener P/E of 2.7× (the screener's own formula needs a non-null price, so this may be
  from a cached or older deploy)

These should be checked before task 2 hard-codes a `0.35` outlier threshold around them.
