# NSE Intelligence — Audit response notes

Companion to `nse-intelligence-audit-and-build-prompt.md` (audit dated
26 Sept 2026, build `index-BMBEYUmb.js`, commit `ffbe3c4`). This file
tracks which of the 28 issues have been closed, which are partial, and
which are deferred with the reason. Update the status column and the
closing commit as work proceeds.

## Bundle-name mapping (audit terms → source)

The audit refers to minified bundle names; the source equivalents are:

| Audit ref | Source location |
|---|---|
| `pA` (companies list) | `hooks/useCompanies.ts` → `fetchCompanies` |
| `dA` (RTDB prices_latest) | `hooks/useHistoricalPrices.ts` (RTDB `prices_latest/{t}`) |
| `gA` (single company) | `hooks/useCompany.ts` → `fetchCompany` |
| `_A` (snapshots latest) | `hooks/useCompany.ts` → `useLatestSnapshot` |
| `vA` (technicals) | `hooks/useCompany.ts` → `useLatestTechnicals` |
| `CA` (intraday) | `hooks/useCompany.ts` → `useIntradayDay` + `company.intraday_today` |
| `bA` (events) | `hooks/useCompany.ts` → `useCorporateEvents` → `lib/firestore.ts` `fetchCorporateEvents` (uses `events/{BASE}_NR`) |
| `xA` (market_overview) | `hooks/useMarket.ts` → `useMarketOverview` |
| `SA` (macro/kenya) | `hooks/useCompany.ts` → `useMacro` |
| `EA` (news items) | `hooks/useCompany.ts` → `useNews` (reads `news/{t}/items`) |
| `jge` (financials periods) | `hooks/useFinancials.ts` (reads `financials/{t}/periods/*`) |
| `zge` (financials analysis) | `hooks/useFinancialAnalysis.ts` (reads `financials/{t}/analysis/*`) |
| `b9` (watchlist reader) | `hooks/useWatchlist.ts` |
| `s9`/`c9` (icon/toolbar buttons) | `components/investor/TradingWorkstation.tsx` → `IconBtn` / `TextBtn` |
| `wge` (drawing tools) | `components/investor/TradingWorkstation.tsx` → `DRAWING_TOOLS` + `LeftDrawingRail` |

## Issue status

| # | Pri | Status | Closing commit / note |
|---|---|---|---|
| 1 | P0 | fixed | `9f64d58` — outer div `overflow-hidden` → `overflow-visible`; toolbar row `overflow-x-auto md:overflow-visible`; added `components/ui/PortalMenu.tsx` for future dropdowns whose parents can't relax overflow |
| 2 | P0 | partial | `13c6219` — Firestore init switched to `experimentalAutoDetectLongPolling` + `persistentLocalCache` (fixes the WebChannel retry storm). Home load-time backend (`market_summary/latest`) deferred: requires a new Cloud Function + Firestore rule; frontend still reads full `companies` collection |
| 3 | P0 | fixed | `13c6219` — `src/lib/ticker.ts` (`toBase`, `toEventsId`, `toDisplay`); App.tsx `CanonicalTicker` route wrapper redirects `.NR`/`_NR` URLs to base form; `fetchCorporateEvents` uses `toEventsId` so ABSA now loads its events |
| 4 | P0 | fixed | `435942d` — hooks catch `FirestoreError`, log the code, collapse `permission-denied`/`not-found` to null. FinancialsPanel / DeepAnalysisPanel render clean empty states with a Retry link on real failures |
| 5 | P0 | deferred | AI signal consistency — needs a single computed target propagated through header, "Why this signal", ML consensus card, AIInsights, and clamping outliers. Multi-file, needs care around the ensemble math. Follow-up: also add horizon label + XGBoost sanity bound in the ML job (out-of-repo) |
| 6 | P1 | fixed | `cf0313d` — TradingWorkstation prefers `company.intraday_today`, falls back to `useIntradayDay(short, today)`; 1D chart plots multi-point time-axis instead of a single dot |
| 7 | P1 | deferred | Candles + OHLC on /chart — requires porting the OHLC series + candle renderer from `components/investor/TradingViewChart.tsx` (or the company-page candles). Also rename "Columns" (currently `stepAfter`) to "Step line". Both need a chart-type extension and Recharts custom shape. |
| 8 | P1 | partial (prior rounds) | Drawing tool activeTool state + one-click ReferenceLine anchors shipped in `f759762` (round-1) and refined in `b15550a` (round-3). Two-point tools (trendline slope, fib, channel), drag-to-move, and undo/redo command stack over drawings are deferred |
| 9 | P1 | partial | `a8e7a2d` — overlays now compute on full price history and slice to visible, so SMA 200 fills the whole 1Y view. Oscillator lower pane (RSI/MACD/Stoch) deferred: needs a second Recharts pane with an independent 0-100 scale |
| 10 | P1 | fixed | `bdc0a0a` — TOOLTIP_LABELS map + every series printed via fmtPrice + KES prefix. No more `bb_lower : 26.75347033187166` |
| 11 | P1 | partial | `bdc0a0a` — volume axis capped at p98 with hatch on capped bars. Side-panel Volume "—" fix and median-based AVG VOL 30D deferred: side panel is `RightSidebarConnected` — needs to read today's volume from `latest.v` |
| 12 | P1 | partial (prior rounds) | Most workstation dead buttons wired in `f759762` / `aa5f267` (Menu, Add-symbol, Save, Templates, Layout, Trade, Publish). Sidebar tabs (Watchlist/Clock/Layers) + watchlist Add/More + symbol-card Detail/Edit/More still stubs |
| 13 | P1 | deferred | Auth + watchlist write path — needs Firebase Auth enablement, sign-in UI, Firestore rules for `users/{uid}`, and localStorage → Firestore migration. Firebase Auth SDK is bundled but sign-in is disabled |
| 14 | P1 | deferred | Alerts that fire — needs a Cloud Function on RTDB `prices_latest/{ticker}` writes, FCM push, email via Trigger Email extension. Frontend UI (draggable alert lines, list/edit/pause/delete) can ship independently once storage moves to `users/{uid}/alerts/` |
| 15 | P1 | deferred | Templates + Save load UI — currently write-only via `window.prompt`/`window.alert`. Needs `<Modal>`, toast system (sonner), and a list-with-Apply/Rename/Delete dropdown |
| 16 | P1 | deferred | Replay + Publish — Replay needs a temporal engine (play/pause/step/speed, indicator recompute to cursor). Publish + Trade should stay behind a feature flag until a real backend exists. Prior rounds already made them honest ("coming soon" tooltips) |
| 17 | P1 | deferred | News + Calendar pages — needs `news_feed/{id}` and `calendar/{yyyy-mm}` Cloud Function-maintained collections + Firestore rules. Nav items become real Links after the pages exist |
| 18 | P1 | partial (prior rounds) | Add-symbol "+" now opens a jump-to-ticker picker (`aa5f267`). Compare-overlay mode + removing the 8-result cap deferred — needs a `compareSymbols[]` state and a second Recharts Line series per compared ticker |
| 19 | P2 | deferred | Market status — one `useMarketStatus()` hook (NSE 09:30-15:00 EAT Mon-Fri minus `nse-holidays.json`) applied to every "Market open"/"Live" badge. Straightforward, no data-side dependency |
| 20 | P2 | deferred | Signal counts consistency — Home/Markets/Board/Screener should compute from one source; "No signal" bucket surfaces the 4 companies without a scored snapshot |
| 21 | P2 | deferred | Screener Div Yield / EPS / P/E — needs ingest-side unit handling (UMME reports UGX; some tickers use cents vs shillings). Frontend can add a "check" badge for P/E outliers today |
| 22 | P2 | deferred | Filings dedup + publish-date field — needs `useFilings(ticker)` hook merging announcements/actions/dividends with dedup by normalized title + period. Ingest should also start storing publish_date separately from ingest_date |
| 23 | P2 | deferred | Company financials labelling (FY vs H1 vs Q3), PAT/EPS unit scaling, MA "vs price" column. Ingest + Valuation table wiring |
| 24 | P2 | deferred | Company page Candles ignores selected range; multi-year axis labels missing year. Needs the same range-respecting slice + year-in-tick logic already applied to workstation (`dc135cb`) |
| 25 | P2 | deferred | ABSA mid-Nov to late-Dec 2025 forward-fill gap. Data-quality script + backfill from NSE daily bulletin ingest |
| 26 | P2 | deferred | Home heatmap tile text WCAG contrast |
| 27 | P2 | deferred | Chart axis price/alert labels — need a filled background pill so white text is readable in light theme |
| 28 | P2 | deferred | Duplicate layouts — `/dashboard/:ticker` vs `/company/:ticker`. Pick one, merge, retire the other |

## Deferred rationale by theme

**Backend-blocked** (need Cloud Function / Firestore rules deploy / Firebase Auth enablement / RTDB trigger): 2 (Home summary), 13 (auth), 14 (alerts trigger), 17 (news feed + calendar), 21 (ingest units), 22 (publish-date field), 23 (unit scaling ingest), 25 (data backfill).

**Multi-file frontend refactors** (need their own commits): 5 (AI signal SoT — CompanyDeepDive + AIInsights + ModelTarget + AI banner), 7 (candles/OHLC — port renderer from TradingViewChart), 8 (real drawing engine), 9 (oscillator pane), 15 (templates load UI + Modal + toast), 18 (compare-overlay).

**Straightforward frontend, next up**: 11 side-panel Volume + AVG VOL median (30-min job), 12 sidebar tabs/watchlist (small — need a real watchlist store), 19 useMarketStatus (30 min), 20 signal-count consistency (aligned with 2 backend), 24 company chart range/labels (reuse workstation fixes), 26/27 visual (styling), 28 layout dedup (product decision).

## Verification checklist (from Phase 5 of the prompt)

- [ ] Playwright: each toolbar menu visible and clickable at 1280×950 and 390×844
- [ ] Playwright: timeframe switch changes the x-axis range
- [ ] Playwright: 1D shows >10 points
- [ ] Playwright: candles render
- [ ] Playwright: trendline persists after reload
- [ ] Playwright: alert create/list/delete
- [ ] Playwright: `/company/ABSA.NR` redirect
- [ ] Playwright: News + Calendar load
- [ ] Playwright: Home first contentful data <3s
- [ ] Playwright: no enabled `<button>` on chart page without a handler
- [ ] Playwright: no "Failed to load" text on ABSA/SCOM/KCB/EQTY company pages
- [ ] Emulator: security rules + alerts function
