# Portfolio Builder — Roadmap

Live as of 2026-09-27 (commit series `feat(planner): ...`).

## Shipped (Phases 0-4)

| Phase | Item | Location |
|---|---|---|
| 0 | 60-day cross-stock correlation matrix | `pipeline/scripts/write_correlation_matrix.py` + `.github/workflows/write_correlation_matrix.yml` |
| 0 | Correlation matrix stored in Firestore | `market_overview/correlation_60d` |
| 1 | Deterministic optimiser + metrics | `frontend/src/lib/portfolio.ts` |
| 1 | Unit tests (9/9 pass) | `frontend/src/lib/portfolio.test.ts` |
| 1 | Universe reader hook | `frontend/src/hooks/usePortfolioUniverse.ts` |
| 2 | Investment inputs, recommendation, projection, risk, why | `frontend/src/pages/Planner.tsx` |
| 3 | Customize panel with live recalc | `frontend/src/components/planner/CustomizePanel.tsx` |
| 3 | Recommended vs custom side-by-side | `frontend/src/components/planner/RecommendedVsCustom.tsx` |
| 4 | Persistence (`users/{uid}/portfolios/{id}`) | `frontend/src/hooks/useUserPortfolios.ts` + `firestore.rules` |
| 4 | Saved portfolios drawer | `frontend/src/components/planner/SavedPortfoliosDrawer.tsx` |
| 4 | Save modal + Load flow | inline in `Planner.tsx` |

## Phase 5 — Extensibility (scaffolded, not built)

Everything below is deliberately **out of scope** for the initial ship but the code is
shaped so each item is an additive change, not a rewrite.

### More investment periods

Add a new key to `HorizonKey`, a matching entry in `HORIZONS`, and a corresponding
`horizon_predictions.{new}` produced by `pipeline/scripts/train_multi_horizon.py`. Then
extend `pipeline/src/models/multi_horizon_gbm.py::HORIZONS` and retrain.

Non-standard example: `2Y` (504 trading days). ARIMA already forecasts 252 days; going
past that needs `LONG_HORIZON_STEPS` bumped in `run_inference.py`.

### More asset classes

`AssetClass` in `frontend/src/lib/portfolio.ts` already covers `"equity" | "etf" | "bond" | "mmf"`.
Existing callers default to `"equity"` (matching current behaviour).

Per class, we need:

| Asset class | Return source | Volatility source | Universe read |
|---|---|---|---|
| ETF | Fund NAV history + declared distributions | 30d NAV stdev × 100 | Firestore `funds/{id}` + weekly job |
| Bond | Yield to maturity + optional roll-down | Duration-weighted rate σ | Firestore `bonds/{isin}` (needs CBK bond curve) |
| MMF | Rate history (rolling 30d avg) | ~0 (money market) | Firestore `mmf/{provider}` |

Add each source to the universe hook, tag with `assetClass`, and the optimiser handles
the rest — score/weight caps are asset-class agnostic. Suggest introducing
`portfolio.ts::returnForHorizon(u, horizon)` as a switch on `u.assetClass` when we go
beyond one class.

### Recurring investments

New route `/planner/recurring`. Inputs:
- Base amount + contribution amount + contribution cadence (monthly/weekly)
- Horizon (5Y, 10Y, 20Y)
- Auto-rebalance cadence (annual / semi-annual / off)

Math: dollar-cost-averaging simulation over `horizon_days` using the same per-horizon
predictions. Store simulation output alongside the plan so we can chart it.

### Goal-based investing

Inverse workflow: user enters *goal amount* and *deadline*. Solve for the required
monthly contribution given the recommendation's expected return, then flag whether
the goal is realistic (with the current risk band's σ) — surface as a probability of
hitting the target.

Requires no new data — just a new math helper `lib/portfolio.ts::solveForContribution`.

### Portfolio tracking (actual vs projected)

On save, snapshot the recommendation's expected trajectory (from LightGBM + ARIMA long
forecast). Compute actual portfolio value daily from live prices + share counts. Show
the delta over time.

New collection: `users/{uid}/portfolios/{id}/tracking/{date}` (server-side write via
Cloud Function triggered by daily inference).

### Portfolio rebalancing

Given a portfolio and today's holdings, suggest trades to bring weights back within
5pp of the plan. Uses the same `enforceCap` + weight-normalisation helpers.

### Actual vs projected performance

Extends tracking above. Chart `plan.expected_value_trajectory` vs
`realised_value_by_date`. Same-plot dual-line. Reuse `PredictionChart`.

### User investment history

Aggregate all saved portfolios per user with cumulative deltas. Sits on the profile
page, once we build a profile page.

## Non-goals for now

- **Automatic trading** — nothing in this codebase places orders. We are a research /
  planning tool, not a broker integration.
- **Advisor licensing** — the "not investment advice" disclaimer stays visible on every
  planner render.
- **Continuous re-optimisation** — recommendations are point-in-time. Users can rebuild
  by re-submitting the form; we don't auto-rebalance without an explicit action.

## When to invalidate the correlation matrix

Weekly cron writes `market_overview/correlation_60d`. If a listing / delisting shifts
the universe significantly, run the workflow manually (workflow_dispatch on the same
YAML) — no schema change needed.
