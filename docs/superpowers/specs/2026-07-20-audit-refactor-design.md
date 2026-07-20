# NSE Predictor — Full Audit & Refactor Design

**Date:** 2026-07-20  
**Scope:** Python pipeline, React/TS frontend, CI/CD workflows, Docker, Firebase config  
**Approach:** Option A — Priority tiers (Critical → Medium → Low)

---

## Tier 1 — Critical (10 fixes)

### T1-1: Remove all hardcoded Windows paths
**Files:** `app.py:158,2205`, `pipeline/src/data/nse_loader.py:32`, `generate_nse_template.py:41`, `scripts/bake_corrections.py:18`, `scripts/diagnose_outliers.py:6`, `scripts/scrape_nse.py:23`

Replace every `Path(r"C:\Users\moeng\Downloads\archive")` with an env-var-driven value:
```python
NSE_ARCHIVE_DIR = Path(os.environ.get("NSE_ARCHIVE_DIR", Path.home() / "Downloads" / "archive"))
```
The `Path.home()` fallback is cross-platform (Windows, Linux, macOS).

Remove the **duplicate** `_ARCHIVE_DIR` definition at `app.py:2205` — it silently shadows the env-var version at line 158.

### T1-2: Fix `/tmp` hardcoded path in run_inference.py
**File:** `pipeline/scripts/run_inference.py:65`

```python
# Before
MODELS_TMP = Path("/tmp/nse_models")
CSVS_TMP  = Path("/tmp/nse_csvs")

# After
import tempfile
_TMP = Path(tempfile.gettempdir())
MODELS_TMP = _TMP / "nse_models"
CSVS_TMP   = _TMP / "nse_csvs"
```

### T1-3: Docker security — add non-root user and .dockerignore
**File:** `Dockerfile`

Add at bottom before CMD:
```dockerfile
RUN useradd -m appuser
USER appuser
```

Create `.dockerignore`:
```
.git
frontend/node_modules
reports
*.log
*.txt
stdout.txt
stderr.txt
data/raw
data/features
models/saved
```

### T1-4: Admin password rate-limiting
**File:** `app.py` — admin unlock callback

Add in-memory attempt counter with 30-second lockout after 5 failed attempts.

### T1-5: Validate ticker before passing to subprocess
**File:** `app.py:2106`

Add regex validation before `subprocess.Popen`:
```python
import re
if not re.match(r'^[A-Z0-9]{1,6}(?:\.[A-Z]{1,3})?$', ticker):
    raise ValueError(f"Invalid ticker format: {ticker}")
```

### T1-6: Remove .env.production from git / add to .gitignore
**File:** `frontend/.env.production`, `.gitignore`

Add `frontend/.env.production` and `frontend/.env.local` to `.gitignore`. These were already ignored in a `chore` commit but need verification. Do NOT delete the file — just ensure it is never committed again.

### T1-7: Fix broken auth routes — 404 on SignInPrompt links
**File:** `frontend/src/components/company/SignInPrompt.tsx`

Either:
- Restore `/login` and `/register` routes in `App.tsx`, OR
- Replace the `<Link>` buttons in `SignInPrompt` with a static message ("Authentication coming soon") until auth is re-enabled.

Decision: Replace with static message (auth is currently disabled globally).

### T1-8: Fix duplicate _ARCHIVE_DIR shadow in app.py
Already covered in T1-1 — remove the second definition at line 2205 entirely.

### T1-9: Fix config.py conflicts
**Files:** `config.py` (root), `pipeline/config.py`

Root `config.py` is outdated; it uses `BASE_DIR = Path(__file__).parent` which gives wrong paths when imported from `pipeline/`. Solution: Delete root `config.py` and replace all imports with `from pipeline.config import ...`. Add `sys.path` guard at top of `app.py` to ensure `pipeline/` is on the path before root.

### T1-10: Validate env vars at startup
**Files:** `app.py`, `firebase_service.py`, `pipeline/scripts/run_inference.py`, `pipeline/scripts/run_daily_update.py`

Add a `_check_required_env()` function called at startup:
```python
REQUIRED = ["FIREBASE_SERVICE_ACCOUNT_JSON", "FIREBASE_STORAGE_BUCKET"]
missing = [k for k in REQUIRED if not os.environ.get(k)]
if missing:
    raise RuntimeError(f"Missing required env vars: {missing}")
```

---

## Tier 2 — Medium (13 fixes)

### T2-1: Extract shared `build_technicals()` utility
**Source:** `run_inference.py:229-280` & `run_daily_update.py:122-173`

Create `pipeline/src/analysis/technicals.py::build_technicals_result(df, ticker, date_str)`. Both scripts import from there.

### T2-2: Extract shared `aggregate_market_overview()` utility
**Source:** `run_inference.py:454-478` & `run_daily_update.py:436-460`

Add to `pipeline/src/analysis/market.py::aggregate_market_overview(results)`.

### T2-3: Centralise `_ARTIFACT_SUFFIXES` constant
**Source:** 3 separate definitions in `run_inference.py`, `run_daily_update.py`, `run_training.py`

Move to `pipeline/config.py::ARTIFACT_SUFFIXES` and import everywhere.

### T2-4: Fix all bare `except Exception: pass` handlers
**Files:** `app.py:198,239,1167,2185,2250,2293,2305`, `run_training.py:138`

Replace with `log.exception("Context message")` and re-raise if the error is non-recoverable.

### T2-5: Fix unclosed file handles
**Files:** `firebase_service.py:27`, `push_to_firestore.py:11`

```python
# Before
sa_dict = json.loads(open(sa_raw).read())

# After
with open(sa_raw, encoding="utf-8") as fh:
    sa_dict = json.load(fh)
```

### T2-6: Add `encoding="utf-8"` to all file opens
**File:** `run_inference.py:144` and any other opens without encoding.

### T2-7: Replace `print()` with `logging` in ML model files
**Files:** `pipeline/src/features/engineer.py`, `pipeline/src/models/xgboost_model.py`, `pipeline/src/models/arima_model.py`, `pipeline/src/models/lstm_model.py`

Add `log = logging.getLogger(__name__)` and replace all `print(...)` calls with `log.info(...)`.

### T2-8: Delete superseded `daily_inference.yml`
**File:** `.github/workflows/daily_inference.yml`

Already marked "SUPERSEDED by daily_update.yml". Delete it.

### T2-9: Extract frontend date/trading-day utilities
**Target:** `frontend/src/lib/dateUtils.ts` (new file)

Move these shared functions there and import in all three consumers:
- `fmtDate(iso: string | null): string`
- `fmtShort(dateStr: string): string`
- `tradingDaysFrom(base: Date, offset: number): string`

### T2-10: Add React ErrorBoundary
**File:** `frontend/src/main.tsx` or `App.tsx`

Wrap the app in `<ErrorBoundary>` using `react-error-boundary` (or hand-rolled class component). Catch Firestore errors at the page level.

### T2-11: Fix feature-column dimension mismatch on model predict
**File:** `run_inference.py:317`

After rebuilding features, verify `len(rebuilt_cols) == len(model_expected_cols)` before calling `model.predict()`. Log a warning and skip inference for that ticker if they differ.

### T2-12: Parallelise model downloads
**File:** `run_inference.py:500-516`

Replace sequential loop with `ThreadPoolExecutor` (already used at line 519 for inference). Pre-download all models in parallel before the inference pool starts.

### T2-13: Remove unused `import math` in run_inference.py
**File:** `run_inference.py:366`

---

## Tier 3 — Low (hygiene)

### T3-1: Delete dead auth components
**Files:** `frontend/src/pages/Login.tsx`, `frontend/src/pages/Register.tsx`, `frontend/src/components/layout/AuthGuard.tsx`, `frontend/src/store/useAuthStore.ts` (remove `setLoading`)

Remove components that are never imported or routed to.

### T3-2: Add named constants for magic numbers
**Files:** `app.py`, `pipeline/src/models/ensemble.py`, `pipeline/src/models/lstm_model.py`

```python
RSI_WINDOW = 14
SIGNAL_THRESHOLD_PCT = 2.0
LSTM_DEFAULT_EPOCHS = 50
THREAD_WORKERS = 4
```

Move to `pipeline/config.py`.

### T3-3: Untrack committed debug log files
**Files:** `stdout.txt`, `stderr.txt`, `eqty_test.txt`, `eabl_rerun.txt`, `run_all_output.txt`, `dash_err.txt`, `dash_out.txt`

```bash
git rm --cached stdout.txt stderr.txt eqty_test.txt eabl_rerun.txt run_all_output.txt dash_err.txt dash_out.txt
```
These are already in `.gitignore`; just need to untrack them.

### T3-4: Align requirements.txt files
**Files:** `requirements.txt` (root), `pipeline/requirements.txt`

Root `requirements.txt` drives Render deployment. Ensure it includes all packages both `app.py` and `pipeline/` need. `pipeline/requirements.txt` is for CI/CD pipeline only.

---

## Success Criteria

- No hardcoded `C:\Users\moeng` paths remain in any Python file
- Docker image runs as non-root, excludes `.git` and `node_modules`
- SignInPrompt no longer links to 404 routes
- All duplicate technicals/aggregation/suffix code removed
- All bare `except: pass` replaced with `log.exception()`
- No `print()` in ML model files
- Frontend date utilities consolidated in `lib/dateUtils.ts`
- `daily_inference.yml` deleted
- Debug log files untracked from git
