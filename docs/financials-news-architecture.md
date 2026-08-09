# Financials, news and analysis — current state and gaps

Investigation of why the company page shows "Failed to load financials",
"Failed to load analysis" and "No announcements on record", and what it would
take to make those sections real rather than placeholder.

Written 2026-08-09. Everything below was measured, not assumed.

## Summary

Four sections are broken, for three different reasons. Only one is a data
problem; the other two are a permissions wall and a dead source URL.

| Section | Collection | Why it fails |
|---|---|---|
| Financials panel | `financials/{ticker}` | Rules require sign-in; site has none |
| Financial narrative | `financials/{ticker}` | Same, plus the writer has never run |
| Deep analysis | `financials/{ticker}` | Same |
| News / corporate actions | `news/{ticker}/items` | Not in rules at all → default deny |
| Predictions | `companies/{ticker}/snapshots` | Rules require sign-in |
| Fundamentals | `fundamentals/{ticker}` | **No writer exists anywhere** |

## 1. The permissions wall

Measured against the live project, unauthenticated:

```
financials/ABSA            PERMISSION_DENIED
fundamentals/ABSA          PERMISSION_DENIED
news/ABSA/items            PERMISSION_DENIED
companies/ABSA/snapshots   PERMISSION_DENIED
```

`firestore.rules` gates `financials`, `macro`, `snapshots` and `technicals`
behind `request.auth != null`. `fundamentals` and `news` are not mentioned at
all, so they fall through to deny.

The app calls `getAuth()` but never signs anyone in, so every visitor is
anonymous and every gated read fails. This is the single biggest cause: even if
all the data existed, four sections would still show errors.

Worth noting the intent appears to be a public site, so these were probably
gated by accident rather than by design.

## 2. Writers that do not run

| Script | Writes | Scheduled? |
|---|---|---|
| `extract_financials.py` | `financials` | `analyze_financials.yml` — **never executed** |
| `analyze_financials_ai.py` | `financials` | same workflow — never executed |
| `seed_financials.py` | `financials` | not in any workflow |
| `seed_events.py` | `events` | not in any workflow |
| `seed_macro.py` | `macro` | not in any workflow |
| `scrape_news.py` | `news` | `daily_update.yml` — runs nightly |
| — | `fundamentals` | **nothing writes this collection** |

`analyze_financials.yml` has no run history at all, which is why the financials
path has never produced data even though the code exists.

`fundamentals` is read by the frontend (`fetchFundamentals`, and
`FundamentalsDoc` in `types/index.ts`) but has no producer. It is a
placeholder end to end.

## 3. The news source is dead

`scrape_news.py` fetches NSE corporate announcements from:

```
https://www.nse.co.ke/market-statistics/corporate-announcements/   -> HTTP 404
```

The page has moved or been removed, so the primary source yields nothing. The
script also carries per-company investor-relations URLs (Safaricom, KCB, Equity,
Co-op, EABL and others) as a secondary source; those were not individually
verified in this pass and are worth checking before relying on them.

## 4. MarketScreener cannot be scraped

This matters because it is the intended reference.

```
GET marketscreener.com/quote/stock/CARBACID-INVESTMENTS-PLC-20702894/news/
  -> HTTP 403 Access Denied (Akamai edge)
```

The block is at the CDN, not a soft rate limit, and a browser user-agent does
not defeat it. Reading its pages by hand works, which is how the price anchors
were verified, but an automated feed is not available without their commercial
API.

So MarketScreener can serve as a **manual reference for verification** — the
model already used for `price_anchors.json` and `price_floors.json` — but not
as an automated source.

### Sources that do respond

| Source | Status | Carries |
|---|---|---|
| `africanfinancials.com/company/ke-{ticker}/` | 200 | Narrative summaries with real figures — CARB page quotes profit of KSh 1,289m and EPS 3.94 from the 2025 annual report. Document links are JS-rendered, so PDFs are not reachable from the raw HTML. |
| `afx.kwayisi.org/nse/{ticker}.html` | 200 | Quote data, recent prices. Static HTML, already used by the price scraper. |
| Company investor-relations pages | untested | Annual and interim reports as PDFs, per company |
| NSE announcements | 404 | Needs a new URL |

## 5. What the frontend expects

Shapes are already defined in `frontend/src/types/index.ts`, so the contract
exists even where the data does not:

- `FinancialsDoc` — `annual[]`, `dividends[]`, `corporate_actions[]`,
  `announcements[]`
- `FinancialResult` — period, period_end, period_type, announcement_date,
  revenue_kes_mn, net_income_kes_mn, eps, bvps
- `DividendEvent` — announcement/ex/payment dates, amount, type
- `NewsItem` — date, title, category, body, url, source
- `FundamentalsDoc` — shares outstanding, enterprise value, employees,
  estimates[]

Building to these shapes means the panels light up without frontend changes.

## 6. The NSE WordPress API is the answer

The NSE runs on WordPress and exposes its media library over the REST API. That
library is where every listed-company filing is uploaded.

```
GET https://www.nse.co.ke/wp-json/wp/v2/media?per_page=100&media_type=application&page=N
    Referer: https://www.nse.co.ke/listed-company-announcements/

X-WP-Total: 4027        X-WP-TotalPages: 41
```

Sampling 1,199 of those documents:

| | Count |
|---|---|
| Financial statements, results, audited/unaudited, annual reports | **472** |
| Corporate actions — dividends, book closure, AGM, registrar changes | **80** |
| NSE internal noise — tenders, job adverts, training calendars | 209 |
| **Listed companies matched by name in titles** | **58 of 61** |

Titles are structured enough to parse company and document type:

```
Centum Investment Company Plc – Audited Financial Results for the Year Ended 31 Mar 2026
BAT Kenya Plc – Unaudited Results for the Six Months Ended 30 June 2026
Eaagads Limited – Audited financial statements for the period ended 31 March 2026
Nairobi Business Ventures Plc – Financial Statements for the Year Ended 31-Mar-2026
```

This is official, centralised, machine-readable, historical and covers almost
the whole universe. `scrape_nse_wp_api.py` already targets this endpoint, so the
groundwork exists.

### Why per-company IR scraping is the weaker path

Tested nine of the twelve IR URLs currently in `scrape_news.py`:

| Result | Companies |
|---|---|
| 404 — URL stale | SCOM, KCB, EABL |
| Connection failed | ABSA |
| 200 but a JS shell, 212 bytes | EQTY |
| 200 with PDFs | COOP, NMG, BRIT, NCBA |

And of the four that returned PDFs, only NMG's were actually reports. NCBA
returned "Key Facts Document — Asset Finance", COOP a tariff guide and school
codes, BRIT a board charter and quality policy. Generic link scraping picks up
marketing collateral, not filings.

Only 12 of 61 companies have an IR URL at all, each site has its own layout,
and those layouts change — which is why three of the twelve are already dead.
That is 61 bespoke scrapers to build and maintain, against one API that already
covers 58 companies.

The sensible split: NSE API as the primary source for everything, with
per-company IR pages considered later only for companies the NSE library
misses.

1. **Open the rules.** Make `financials`, `fundamentals`, `news`, `snapshots`
   and `technicals` publicly readable, matching the stated intent of a public
   site. Cheapest change, and it unblocks four sections at once. Note the live
   rules may have drifted from this file — `firebase.json` does not deploy
   `firestore.rules`, so the console copy is authoritative.
2. **Harvest the NSE media library.** Walk all 41 pages, keep the filings and
   drop the tenders and job adverts, and parse company plus document type from
   the title. That produces the announcements feed and the document index
   together.
3. **Populate `news` from the harvest**, replacing the dead
   corporate-announcements URL in `scrape_news.py`. Corporate actions —
   dividends, book closures, AGMs — come from the same source.
4. **Extract figures from the filing PDFs** to populate `financials`. The
   repo already has OCR machinery for NSE PDFs in the price pipeline, so the
   hard part is table extraction rather than fetching.
5. **Either build or remove `fundamentals`.** It is currently a promise the
   backend does not keep.

## Open questions

- Should the site require sign-in for any of this, or is it fully public?
- Is a manually maintained financials dataset acceptable, as with the price
  archive, or must it be automated?
- Is a MarketScreener subscription with API access on the table? It would
  remove most of the sourcing difficulty.
