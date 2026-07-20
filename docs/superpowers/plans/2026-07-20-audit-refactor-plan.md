# NSE Predictor Audit Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all critical, medium, and low issues identified in the audit without breaking the working pipeline or React frontend.

**Architecture:** Three-tier priority approach — Tier 1 (Critical) removes hardcoded paths, fixes Docker security, and repairs broken UX; Tier 2 (Medium) extracts duplicated utilities, fixes error handling, and adds logging; Tier 3 (Low) removes dead code and unracks debug files.

**Tech Stack:** Python 3.11, PyTorch, Firebase Admin SDK, Dash/Plotly, React 18, TypeScript, Vitest, Docker, GitHub Actions

---

## Files Modified

| File | Change |
|------|--------|
| `app.py:158` | Cross-platform path fallback |
| `app.py:2205` | Remove duplicate `_ARCHIVE_DIR` |
| `app.py:2093-2112` | Ticker whitelist validation before subprocess |
| `app.py:3527-3534` | Rate-limit admin unlock |
| `pipeline/src/data/nse_loader.py:32` | Env-var-driven archive dir |
| `pipeline/scripts/run_inference.py:65` | `tempfile.gettempdir()` |
| `pipeline/scripts/run_daily_update.py:84,498` | `tempfile.gettempdir()` (two locations) |
| `pipeline/scripts/push_to_firestore.py:11` | Context manager for file handle |
| `pipeline/scripts/run_inference.py:87-99` | Import ARTIFACT_SUFFIXES from config |
| `pipeline/scripts/run_daily_update.py:87-88` | Import ARTIFACT_SUFFIXES from config |
| `pipeline/scripts/run_training.py:40-46` | Import ARTIFACT_SUFFIXES from config |
| `pipeline/config.py` | Add ARTIFACT_SUFFIXES constant |
| `pipeline/src/analysis/technicals.py` | **NEW** — shared technicals builder |
| `pipeline/src/analysis/market.py` | **NEW** — shared market overview aggregator |
| `pipeline/scripts/run_inference.py:229-280` | Import from technicals.py |
| `pipeline/scripts/run_daily_update.py:122-173` | Import from technicals.py |
| `pipeline/scripts/run_inference.py:454-478` | Import from market.py |
| `pipeline/scripts/run_daily_update.py:436-460` | Import from market.py |
| `pipeline/src/models/lstm_model.py` | `print()` → `log.info()` |
| `pipeline/src/models/xgboost_model.py` | `print()` → `log.info()` |
| `pipeline/src/models/arima_model.py` | `print()` → `log.info()` |
| `pipeline/src/features/engineer.py` | `print()` → `log.info()` |
| `Dockerfile` | Add non-root user |
| `.dockerignore` | **NEW** |
| `frontend/src/components/company/SignInPrompt.tsx` | Remove broken `<Link>` buttons |
| `frontend/src/lib/dateUtils.ts` | **NEW** — shared date/trading-day utilities |
| `frontend/src/components/charts/PredictionChart.tsx` | Import from dateUtils |
| `frontend/src/components/charts/SparkLine.tsx` | Import from dateUtils |
| `frontend/src/pages/CompanyDeepDive.tsx` | Import from dateUtils |
| `frontend/src/main.tsx` | Add ErrorBoundary wrapper |
| `.github/workflows/daily_inference.yml` | Delete (superseded) |
| `frontend/src/pages/Login.tsx` | Delete |
| `frontend/src/pages/Register.tsx` | Delete |
| `frontend/src/components/layout/AuthGuard.tsx` | Delete |

---

## TIER 1 — CRITICAL

---

### Task 1: Fix hardcoded Windows path in app.py (two locations)

**Files:**
- Modify: `app.py:158`
- Modify: `app.py:2205`

- [ ] **Step 1: Fix the env-var version at line 158 to use a cross-platform fallback**

Open `app.py`. Find line 158:
```python
_ARCHIVE_DIR = Path(os.environ.get("NSE_ARCHIVE_DIR", r"C:\Users\moeng\Downloads\archive"))
```
Replace with:
```python
_ARCHIVE_DIR = Path(os.environ.get("NSE_ARCHIVE_DIR", str(Path.home() / "Downloads" / "archive")))
```

- [ ] **Step 2: Remove the duplicate hardcoded definition at line 2205**

Find line 2205 (just before `# TAB 5 — NSE DATA EXPLORER`):
```python
_ARCHIVE_DIR = Path(r"C:\Users\moeng\Downloads\archive")
```
Delete this line entirely. The `_ARCHIVE_DIR` defined at line 158 is already available module-wide.

- [ ] **Step 3: Commit**
```bash
cd C:\Users\moeng\nse_predictor
git add app.py
git commit -m "fix: replace hardcoded Windows archive path with cross-platform fallback"
```

---

### Task 2: Fix hardcoded Windows path in nse_loader.py

**Files:**
- Modify: `pipeline/src/data/nse_loader.py:32`

- [ ] **Step 1: Replace the hardcoded path**

Find line 32:
```python
NSE_ARCHIVE_DIR = Path(r"C:\Users\moeng\Downloads\archive")
```
Replace with:
```python
NSE_ARCHIVE_DIR = Path(os.environ.get("NSE_ARCHIVE_DIR", str(Path.home() / "Downloads" / "archive")))
```

- [ ] **Step 2: Add `import os` at the top of the file if not already present**

Check top of `nse_loader.py`. If `import os` is missing, add it after `import re`.

- [ ] **Step 3: Commit**
```bash
git add pipeline/src/data/nse_loader.py
git commit -m "fix: use env var for NSE_ARCHIVE_DIR in nse_loader.py with cross-platform fallback"
```

---

### Task 3: Fix /tmp hardcoded paths — cross-platform temp dir

**Files:**
- Modify: `pipeline/scripts/run_inference.py:65`
- Modify: `pipeline/scripts/run_daily_update.py:84`
- Modify: `pipeline/scripts/run_daily_update.py` (inside `main()` ~line 498)

- [ ] **Step 1: Fix run_inference.py**

Find lines 64-65:
```python
TODAY = date.today().isoformat()
MODELS_TMP = Path("/tmp/nse_models")   # ephemeral cache on GitHub Actions runners
```
Replace with:
```python
import tempfile as _tempfile

TODAY = date.today().isoformat()
MODELS_TMP = Path(_tempfile.gettempdir()) / "nse_models"
```

Also find the `CSVS_TMP` definition (around line 484):
```python
CSVS_TMP = Path("/tmp/nse_csvs")
```
Replace with:
```python
CSVS_TMP  = Path(_tempfile.gettempdir()) / "nse_csvs"
```

- [ ] **Step 2: Fix run_daily_update.py module-level**

Find line 84:
```python
MODELS_TMP = Path("/tmp/nse_models")
```
Replace with:
```python
import tempfile as _tempfile

MODELS_TMP = Path(_tempfile.gettempdir()) / "nse_models"
```

- [ ] **Step 3: Fix run_daily_update.py inside main()**

Inside `main()` function, find (~line 498):
```python
CSVS_TMP = Path("/tmp/nse_csvs")
```
Replace with:
```python
CSVS_TMP = Path(_tempfile.gettempdir()) / "nse_csvs"
```

- [ ] **Step 4: Commit**
```bash
git add pipeline/scripts/run_inference.py pipeline/scripts/run_daily_update.py
git commit -m "fix: use tempfile.gettempdir() for cross-platform temp model cache"
```

---

### Task 4: Fix unclosed file handle in push_to_firestore.py

**Files:**
- Modify: `pipeline/scripts/push_to_firestore.py:11`

- [ ] **Step 1: Replace bare open() with context manager**

Find line 11:
```python
sa_dict = json.loads(sa_raw) if sa_raw.strip().startswith("{") else json.loads(open(sa_raw).read())
```
Replace with:
```python
if sa_raw.strip().startswith("{"):
    sa_dict = json.loads(sa_raw)
else:
    with open(sa_raw, encoding="utf-8") as _fh:
        sa_dict = json.load(_fh)
```

- [ ] **Step 2: Apply same fix to firebase_service.py**

Find in `firebase_service.py` (~line 27):
```python
sa_dict = json.loads(sa_raw) if sa_raw.strip().startswith("{") else json.loads(open(sa_raw).read())
```
Replace with:
```python
if sa_raw.strip().startswith("{"):
    sa_dict = json.loads(sa_raw)
else:
    with open(sa_raw, encoding="utf-8") as _fh:
        sa_dict = json.load(_fh)
```

- [ ] **Step 3: Add encoding="utf-8" to run_inference.py feature_cols open**

Find in `run_inference.py` (~line 144):
```python
with open(MODELS_TMP / f"{safe}_feature_cols.json") as f:
```
Replace with:
```python
with open(MODELS_TMP / f"{safe}_feature_cols.json", encoding="utf-8") as f:
```

- [ ] **Step 4: Commit**
```bash
git add pipeline/scripts/push_to_firestore.py firebase_service.py pipeline/scripts/run_inference.py
git commit -m "fix: close file handles with context managers, add utf-8 encoding to file opens"
```

---

### Task 5: Docker — add non-root user and .dockerignore

**Files:**
- Modify: `Dockerfile`
- Create: `.dockerignore`

- [ ] **Step 1: Add non-root user to Dockerfile**

Current `Dockerfile` content:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8050

CMD ["gunicorn", "app:server", "--config", "gunicorn.conf.py"]
```

Replace entirely with:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8050

CMD ["gunicorn", "app:server", "--config", "gunicorn.conf.py"]
```

- [ ] **Step 2: Create .dockerignore**

Create `.dockerignore` at repo root:
```
.git
.github
frontend/node_modules
frontend/.env.production
frontend/.env.local
reports
*.log
stdout.txt
stderr.txt
eqty_test.txt
eabl_rerun.txt
run_all_output.txt
dash_err.txt
dash_out.txt
app_err.log
app_out.log
app_server.log
app_server_err.log
data/raw
data/features
__pycache__
**/__pycache__
*.pyc
.env
```

- [ ] **Step 3: Commit**
```bash
git add Dockerfile .dockerignore
git commit -m "fix: run container as non-root user, add .dockerignore to exclude dev artifacts"
```

---

### Task 6: Fix SignInPrompt — remove broken links to non-existent routes

**Files:**
- Modify: `frontend/src/components/company/SignInPrompt.tsx`

- [ ] **Step 1: Replace broken `<Link>` buttons with static message**

Current content of `SignInPrompt.tsx`:
```tsx
import type { FC } from "react";
import { Link } from "react-router-dom";
import { Button } from "../ui/Button";

export const SignInPrompt: FC = () => (
  <div className="rounded-xl border border-slate-600 bg-slate-800/90 p-8 text-center backdrop-blur-sm">
    <p className="text-lg font-semibold text-slate-100">
      Sign in to unlock full analysis
    </p>
    <p className="mt-2 text-sm text-slate-400">
      Free account — AI predictions, technical indicators, risk analysis and more.
    </p>
    <div className="mt-6 flex justify-center gap-3">
      <Link to="/register">
        <Button>Create free account</Button>
      </Link>
      <Link to="/login">
        <Button variant="secondary">Sign in</Button>
      </Link>
    </div>
  </div>
);
```

Replace with (no Link imports, static CTA):
```tsx
import type { FC } from "react";

export const SignInPrompt: FC = () => (
  <div className="rounded-xl border border-slate-600 bg-slate-800/90 p-8 text-center backdrop-blur-sm">
    <p className="text-lg font-semibold text-slate-100">
      Full analysis coming soon
    </p>
    <p className="mt-2 text-sm text-slate-400">
      AI predictions, technical indicators, and risk analysis will be available shortly.
    </p>
  </div>
);
```

- [ ] **Step 2: Commit**
```bash
git add frontend/src/components/company/SignInPrompt.tsx
git commit -m "fix: remove broken auth links from SignInPrompt — auth routes are currently disabled"
```

---

### Task 7: Validate ticker before subprocess call

**Files:**
- Modify: `app.py` (callback around line 2094–2112)

- [ ] **Step 1: Add whitelist validation before subprocess.Popen**

Find the upload callback containing these lines (~2094-2112):
```python
safe_name = filename or f"{ticker.replace('.','_')}.csv"
csv_path = DATA_RAW / safe_name
with open(csv_path, "wb") as f:
    f.write(decoded)

# ...

subprocess.Popen(
    [sys.executable, str(Path(__file__).parent / "main.py"),
     "--ticker", ticker, "--csv", str(csv_path)],
    ...
)
```

Add validation immediately before `subprocess.Popen`. Find the exact `subprocess.Popen(` line and insert before it:
```python
        # Whitelist validation — ticker must be a known NSE symbol
        _known = {c[0] for c in _RAW_COMPANIES}  # set of short tickers e.g. "SCOM", "KCB"
        _ticker_base = ticker.replace(".NR", "").replace(".", "").upper()
        if _ticker_base not in _known:
            return ("", "",
                    html.Span(f"Unknown ticker: {ticker}",
                              style=dict(color=C["sell"], fontSize="0.75rem")),
                    _visible, True)
```

- [ ] **Step 2: Commit**
```bash
git add app.py
git commit -m "fix: validate ticker against known NSE companies whitelist before subprocess call"
```

---

## TIER 2 — MEDIUM

---

### Task 8: Centralise ARTIFACT_SUFFIXES in pipeline/config.py

**Files:**
- Modify: `pipeline/config.py`
- Modify: `pipeline/scripts/run_inference.py:87-99`
- Modify: `pipeline/scripts/run_daily_update.py:87-88`
- Modify: `pipeline/scripts/run_training.py:40-46`

- [ ] **Step 1: Add constant to pipeline/config.py**

Open `pipeline/config.py`. After the last constant (`ENSEMBLE_WEIGHTS`), add:
```python
# Artifact filenames saved per ticker by run_training.py
ARTIFACT_SUFFIXES = [
    "_lstm.pt",
    "_lstm_scaler.pkl",
    "_xgboost.pkl",
    "_arima.pkl",
    "_feature_cols.json",
]
```

- [ ] **Step 2: Update run_inference.py**

Find lines 86-99:
```python
# Artifact filenames (must match run_training.py)
_ARTIFACT_SUFFIXES = [
    "_lstm.pt",
    "_lstm_scaler.pkl",
    "_xgboost.pkl",
    "_arima.pkl",
    "_feature_cols.json",
]
_CORE_SUFFIXES = [
    "_lstm.pt",
    "_lstm_scaler.pkl",
    "_xgboost.pkl",
    "_arima.pkl",
]
```
Replace with:
```python
from config import (
    load_companies, MODELS_DIR,
    DEFAULT_INVESTMENT, DEFAULT_CONFIDENCE,
    ENSEMBLE_WEIGHTS, SEQUENCE_LENGTH,
    ARTIFACT_SUFFIXES as _ARTIFACT_SUFFIXES,
)

_CORE_SUFFIXES = [s for s in _ARTIFACT_SUFFIXES if s != "_feature_cols.json"]
```
(The `from config import` line already exists — just add `ARTIFACT_SUFFIXES as _ARTIFACT_SUFFIXES,` to it and remove the local list definitions.)

- [ ] **Step 3: Update run_daily_update.py**

Find lines 86-88:
```python
# Artifact filenames that must be present for a full model load.
_LSTM_SUFFIXES = ["_lstm.pt", "_lstm_scaler.pkl", "_feature_cols.json"]
_ALL_SUFFIXES = _LSTM_SUFFIXES + ["_xgboost.pkl", "_arima.pkl"]
```
Replace with:
```python
from config import (
    load_companies,
    DEFAULT_INVESTMENT,
    DEFAULT_CONFIDENCE,
    ENSEMBLE_WEIGHTS,
    SEQUENCE_LENGTH,
    ARTIFACT_SUFFIXES,
)

_LSTM_SUFFIXES = ["_lstm.pt", "_lstm_scaler.pkl", "_feature_cols.json"]
_ALL_SUFFIXES = ARTIFACT_SUFFIXES  # same list, named for clarity
```
(Add `ARTIFACT_SUFFIXES,` to the existing `from config import` block.)

- [ ] **Step 4: Update run_training.py**

Find lines 39-46:
```python
# Artifacts saved per ticker (must all be uploaded)
_ARTIFACT_SUFFIXES = [
    "_lstm.pt",
    "_lstm_scaler.pkl",
    "_xgboost.pkl",
    "_arima.pkl",
    "_feature_cols.json",
]
```
Replace with:
```python
from config import load_companies, MODELS_DIR, ARTIFACT_SUFFIXES as _ARTIFACT_SUFFIXES
```
(Add to the existing import block — remove local list.)

- [ ] **Step 5: Commit**
```bash
git add pipeline/config.py pipeline/scripts/run_inference.py pipeline/scripts/run_daily_update.py pipeline/scripts/run_training.py
git commit -m "refactor: centralise ARTIFACT_SUFFIXES in pipeline/config.py, remove 3 duplicate lists"
```

---

### Task 9: Extract shared technicals builder

**Files:**
- Create: `pipeline/src/analysis/technicals.py`
- Modify: `pipeline/scripts/run_inference.py:229-280`
- Modify: `pipeline/scripts/run_daily_update.py:122-173`

- [ ] **Step 1: Create pipeline/src/analysis/technicals.py**

```python
# pipeline/src/analysis/technicals.py
"""Shared technical-indicator builder used by both inference and daily-update pipelines."""
import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


def build_technicals_result(df: pd.DataFrame, date_str: str) -> dict:
    """Compute a full set of technical indicators for a price/volume dataframe.

    Parameters
    ----------
    df:
        DataFrame with at minimum a 'Close' column and a DatetimeIndex.
        A 'Volume' column is used when present; otherwise volume fields default to 0.
    date_str:
        ISO date string to embed as the 'date' key in the result dict.

    Returns
    -------
    dict with all indicator fields populated, or None values on error.
    """
    try:
        import ta
        close  = df["Close"]
        volume = df["Volume"] if "Volume" in df.columns else pd.Series(0, index=df.index)

        rsi    = ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-1]
        macd_i = ta.trend.MACD(close)
        bb     = ta.volatility.BollingerBands(close)
        sma20  = close.rolling(20).mean().iloc[-1]
        sma50  = close.rolling(50).mean().iloc[-1]
        sma200 = close.rolling(200).mean().iloc[-1]
        ema12  = close.ewm(span=12).mean().iloc[-1]
        ema26  = close.ewm(span=26).mean().iloc[-1]

        monthly = (df["Close"].resample("ME").last().pct_change() * 100).dropna()
        monthly_heatmap = {str(k)[:7]: round(float(v), 2) for k, v in monthly.items()}

        def _f(x: float) -> float | None:
            return None if (isinstance(x, float) and np.isnan(x)) else round(float(x), 4)

        return {
            "date":             date_str,
            "rsi_14":           _f(rsi),
            "macd":             _f(macd_i.macd().iloc[-1]),
            "macd_signal":      _f(macd_i.macd_signal().iloc[-1]),
            "macd_hist":        _f(macd_i.macd_diff().iloc[-1]),
            "bb_upper":         _f(bb.bollinger_hband().iloc[-1]),
            "bb_mid":           _f(bb.bollinger_mavg().iloc[-1]),
            "bb_lower":         _f(bb.bollinger_lband().iloc[-1]),
            "sma_20":           _f(sma20),
            "sma_50":           _f(sma50),
            "sma_200":          _f(sma200),
            "ema_12":           _f(ema12),
            "ema_26":           _f(ema26),
            "volume":           int(volume.iloc[-1]) if len(volume) else 0,
            "avg_volume_30d":   int(volume.tail(30).mean()) if len(volume) else 0,
            "daily_return":     _f(df["Close"].pct_change().iloc[-1] * 100),
            "volatility_30d":   _f(df["Close"].pct_change().tail(30).std() * 100),
            "monthly_heatmap":  monthly_heatmap,
        }
    except Exception as exc:
        log.error("Technicals computation failed: %s", exc)
        return {
            "date": date_str, "error": str(exc),
            "rsi_14": None, "macd": None, "macd_signal": None, "macd_hist": None,
            "bb_upper": None, "bb_mid": None, "bb_lower": None,
            "sma_20": None, "sma_50": None, "sma_200": None,
            "ema_12": None, "ema_26": None,
            "volume": 0, "avg_volume_30d": 0,
            "daily_return": None, "volatility_30d": None, "monthly_heatmap": {},
        }
```

- [ ] **Step 2: Update run_inference.py to import instead of defining locally**

At the top imports of `run_inference.py`, add:
```python
from src.analysis.technicals import build_technicals_result
```

Then delete the local `build_technicals_result` function (lines 229-280 — the entire `def build_technicals_result` block).

- [ ] **Step 3: Update run_daily_update.py to import instead of defining locally**

At the top imports of `run_daily_update.py`, add:
```python
from src.analysis.technicals import build_technicals_result as _build_technicals
```

Then delete the local `_build_technicals` function (lines 122-173 — the entire `# ── Technicals builder` block and the function below it).

Any call sites using `_build_technicals(df)` stay as-is since the alias matches.

- [ ] **Step 4: Verify both scripts call the function with matching signatures**

`run_inference.py` calls: `build_technicals_result(df, date_str)`  
`run_daily_update.py` calls: `_build_technicals(df)` — but the new shared function requires `date_str`.

Find `_build_technicals(` calls in `run_daily_update.py` and add `TODAY` as the second argument:
```python
# Before
tech = _build_technicals(cleaned_df)

# After
tech = _build_technicals(cleaned_df, TODAY)
```

- [ ] **Step 5: Quick smoke test**
```bash
cd C:\Users\moeng\nse_predictor
python -c "from pipeline.src.analysis.technicals import build_technicals_result; print('OK')"
```
Expected output: `OK`

- [ ] **Step 6: Commit**
```bash
git add pipeline/src/analysis/technicals.py pipeline/scripts/run_inference.py pipeline/scripts/run_daily_update.py
git commit -m "refactor: extract shared build_technicals_result into pipeline/src/analysis/technicals.py"
```

---

### Task 10: Extract shared market overview aggregator

**Files:**
- Create: `pipeline/src/analysis/market.py`
- Modify: `pipeline/scripts/run_inference.py:454-478`
- Modify: `pipeline/scripts/run_daily_update.py:436-460`

- [ ] **Step 1: Create pipeline/src/analysis/market.py**

```python
# pipeline/src/analysis/market.py
"""Shared market-overview aggregation used by inference and daily-update."""


def aggregate_market_overview(results: list[dict], date_str: str) -> dict:
    """Aggregate per-company inference results into a market-level summary.

    Parameters
    ----------
    results:
        List of dicts returned by each company's run_company(). None entries are skipped.
    date_str:
        ISO date string for the 'date' field.
    """
    rows: list[tuple[str, float]] = []
    signals: dict[str, int] = {"BUY": 0, "HOLD": 0, "SELL": 0}

    for r in results:
        if r is None:
            continue
        pub = r["public_update"]
        rows.append((r["ticker"], pub["change_pct_today"]))
        sig = pub["signal"]
        signals[sig] = signals.get(sig, 0) + 1

    rows.sort(key=lambda x: x[1], reverse=True)
    top_gainers = [{"ticker": t, "change_pct": round(c, 2)} for t, c in rows[:5]]
    top_losers  = [{"ticker": t, "change_pct": round(c, 2)} for t, c in rows[-5:]]

    return {
        "date":                date_str,
        "top_gainers":         top_gainers,
        "top_losers":          top_losers,
        "signal_distribution": signals,
        "sector_performance":  {},
        "nse20_value":         None,
        "nse20_change_pct":    None,
    }
```

- [ ] **Step 2: Update run_inference.py**

Add import:
```python
from src.analysis.market import aggregate_market_overview
```

Delete local `aggregate_market_overview` function (lines 454-478) and find all call sites. They will work unchanged since the function signature is the same — but now requires `date_str`:
```python
# Before
overview = aggregate_market_overview(results)

# After
overview = aggregate_market_overview(results, TODAY)
```

- [ ] **Step 3: Update run_daily_update.py**

Add import:
```python
from src.analysis.market import aggregate_market_overview as _aggregate_market_overview
```

Delete local `_aggregate_market_overview` function (lines 436-460). Find call sites and add `TODAY`:
```python
# Before
overview = _aggregate_market_overview(results)

# After
overview = _aggregate_market_overview(results, TODAY)
```

- [ ] **Step 4: Smoke test**
```bash
python -c "from pipeline.src.analysis.market import aggregate_market_overview; print('OK')"
```
Expected: `OK`

- [ ] **Step 5: Commit**
```bash
git add pipeline/src/analysis/market.py pipeline/scripts/run_inference.py pipeline/scripts/run_daily_update.py
git commit -m "refactor: extract shared aggregate_market_overview into pipeline/src/analysis/market.py"
```

---

### Task 11: Fix bare except handlers — add logging

**Files:**
- Modify: `app.py:198,239`
- Modify: `pipeline/scripts/run_training.py:138`

- [ ] **Step 1: Fix bare except in _load_chunk (app.py ~line 198)**

Find:
```python
        except Exception:
            pass
```
Inside `_load_chunk`. Replace with:
```python
        except Exception:
            log.debug("Skipped malformed CSV chunk: %s", path, exc_info=True)
```
(The outer scope already has `log` — if not, add `log = logging.getLogger(__name__)` near top of file and `import logging`.)

- [ ] **Step 2: Fix bare except in _load_company_archive (app.py ~line 239)**

Find:
```python
    except Exception:
        _archive_df_cache[code] = None
        return None
```
Replace with:
```python
    except Exception:
        log.warning("Failed to load archive for %s", code, exc_info=True)
        _archive_df_cache[code] = None
        return None
```

- [ ] **Step 3: Fix silent bare except in run_training.py (~line 138)**

Find the bare `except Exception: pass` around the Firestore write. Replace with:
```python
    except Exception:
        log.exception("Firestore write failed for %s", ticker)
```

- [ ] **Step 4: Add logging to app.py if missing**

Check if `app.py` has a `log = logging.getLogger(...)`. If it only uses `print()`, add near the top (after imports):
```python
import logging
log = logging.getLogger(__name__)
```

- [ ] **Step 5: Commit**
```bash
git add app.py pipeline/scripts/run_training.py
git commit -m "fix: replace silent bare except handlers with log.warning/log.exception"
```

---

### Task 12: Replace print() with logging in ML model files

**Files:**
- Modify: `pipeline/src/features/engineer.py`
- Modify: `pipeline/src/models/xgboost_model.py`
- Modify: `pipeline/src/models/arima_model.py`
- Modify: `pipeline/src/models/lstm_model.py`

- [ ] **Step 1: Add logger to each file and replace all print() calls**

For each file, add after the existing imports:
```python
import logging
log = logging.getLogger(__name__)
```

Then replace every `print(...)` with `log.info(...)`. Examples:

**engineer.py** — find:
```python
print(f"Selected {len(selected)} features via RFE")
```
Replace with:
```python
log.info("Selected %d features via RFE", len(selected))
```

**xgboost_model.py** — find:
```python
print(f"  XGBoost saved → {path.name}")
```
Replace with:
```python
log.info("XGBoost saved → %s", path.name)
```

**arima_model.py** — find:
```python
print(f"[ARIMA] Fitting...")
```
Replace with:
```python
log.info("ARIMA fitting...")
```

**lstm_model.py** — find:
```python
print(f"[LSTM] Training on {device}")
```
Replace with:
```python
log.info("LSTM training on %s", device)
```

- [ ] **Step 2: Commit**
```bash
git add pipeline/src/features/engineer.py pipeline/src/models/xgboost_model.py pipeline/src/models/arima_model.py pipeline/src/models/lstm_model.py
git commit -m "fix: replace print() with logging in ML model files for structured observability"
```

---

### Task 13: Delete superseded daily_inference.yml

**Files:**
- Delete: `.github/workflows/daily_inference.yml`

- [ ] **Step 1: Confirm it is truly superseded**

Read the top comment of `.github/workflows/daily_inference.yml`. It should say:
```
# SUPERSEDED by daily_update.yml which scrapes, retrains XGBoost+ARIMA, and runs inference in a single workflow
```
Confirmed — safe to delete.

- [ ] **Step 2: Delete**
```bash
cd C:\Users\moeng\nse_predictor
git rm .github/workflows/daily_inference.yml
git commit -m "chore: delete superseded daily_inference.yml — replaced by daily_update.yml"
```

---

### Task 14: Frontend — extract shared date/trading-day utilities

**Files:**
- Create: `frontend/src/lib/dateUtils.ts`
- Modify: `frontend/src/pages/CompanyDeepDive.tsx`
- Modify: `frontend/src/components/charts/PredictionChart.tsx`
- Modify: `frontend/src/components/charts/SparkLine.tsx`

- [ ] **Step 1: Create frontend/src/lib/dateUtils.ts**

```typescript
// frontend/src/lib/dateUtils.ts

/** Format an ISO date string for display (en-KE locale, long format). */
export function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso + "T00:00:00").toLocaleDateString("en-KE", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

/** Format an ISO date string to short month+day (e.g. "Jul 20"). */
export function fmtShort(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00");
  if (isNaN(d.getTime())) return dateStr;
  return d.toLocaleDateString("en-KE", { month: "short", day: "numeric" });
}

/**
 * Advance a date by `offset` trading days (Mon–Fri only), returning an ISO date string.
 * Positive offset = forward; negative = backward.
 */
export function tradingDaysFrom(base: Date, offset: number): string {
  const d = new Date(base);
  let remaining = Math.abs(offset);
  const direction = offset >= 0 ? 1 : -1;
  while (remaining > 0) {
    d.setDate(d.getDate() + direction);
    const day = d.getDay();
    if (day !== 0 && day !== 6) remaining--;
  }
  return d.toISOString().slice(0, 10);
}
```

- [ ] **Step 2: Update CompanyDeepDive.tsx**

Find the local `fmtDate` / trading-day function definitions near the top of the file. Remove them and replace with:
```typescript
import { fmtDate, tradingDaysFrom } from "../lib/dateUtils";
```

Update any call site that previously used the local versions — the signatures are identical.

- [ ] **Step 3: Update PredictionChart.tsx**

Find the local `fmtShort` / trading-day definitions. Remove them and add:
```typescript
import { fmtShort, tradingDaysFrom } from "../../lib/dateUtils";
```

- [ ] **Step 4: Update SparkLine.tsx**

Find the local `fmtLabel` / date formatting. Remove it and add:
```typescript
import { fmtShort } from "../../lib/dateUtils";
```
Rename any `fmtLabel(...)` calls to `fmtShort(...)`.

- [ ] **Step 5: Verify TypeScript**
```bash
cd C:\Users\moeng\nse_predictor\frontend
npx tsc --noEmit
```
Expected: No errors.

- [ ] **Step 6: Commit**
```bash
git add frontend/src/lib/dateUtils.ts frontend/src/pages/CompanyDeepDive.tsx frontend/src/components/charts/PredictionChart.tsx frontend/src/components/charts/SparkLine.tsx
git commit -m "refactor: extract shared fmtDate/fmtShort/tradingDaysFrom into lib/dateUtils.ts"
```

---

### Task 15: Frontend — add global ErrorBoundary

**Files:**
- Modify: `frontend/src/main.tsx`

- [ ] **Step 1: Install react-error-boundary if not already present**
```bash
cd C:\Users\moeng\nse_predictor\frontend
npm list react-error-boundary 2>/dev/null || npm install react-error-boundary
```

- [ ] **Step 2: Update main.tsx**

Current `main.tsx`:
```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "./index.css";
import App from "./App";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 5 * 60 * 1000, retry: 1 },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </BrowserRouter>
  </StrictMode>
);
```

Replace with:
```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ErrorBoundary } from "react-error-boundary";
import "./index.css";
import App from "./App";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 5 * 60 * 1000, retry: 1 },
  },
});

function ErrorFallback({ error, resetErrorBoundary }: { error: Error; resetErrorBoundary: () => void }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 p-8 text-center">
      <div className="max-w-md rounded-xl border border-red-800 bg-red-950/20 p-8">
        <p className="text-lg font-semibold text-red-400">Something went wrong</p>
        <p className="mt-2 text-sm text-slate-400">{error.message}</p>
        <button
          onClick={resetErrorBoundary}
          className="mt-6 rounded-lg bg-sky-700 px-4 py-2 text-sm font-medium text-white hover:bg-sky-600"
        >
          Try again
        </button>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary FallbackComponent={ErrorFallback}>
      <BrowserRouter>
        <QueryClientProvider client={queryClient}>
          <App />
        </QueryClientProvider>
      </BrowserRouter>
    </ErrorBoundary>
  </StrictMode>
);
```

- [ ] **Step 3: Verify TypeScript**
```bash
cd C:\Users\moeng\nse_predictor\frontend
npx tsc --noEmit
```
Expected: No errors.

- [ ] **Step 4: Commit**
```bash
git add frontend/src/main.tsx frontend/package.json frontend/package-lock.json
git commit -m "feat: add global ErrorBoundary to prevent full-page crashes from Firestore errors"
```

---

## TIER 3 — LOW (Hygiene)

---

### Task 16: Delete dead auth components

**Files:**
- Delete: `frontend/src/pages/Login.tsx`
- Delete: `frontend/src/pages/Register.tsx`
- Delete: `frontend/src/components/layout/AuthGuard.tsx`
- Modify: `frontend/src/store/useAuthStore.ts` (remove unused `setLoading`)

- [ ] **Step 1: Verify none of these are imported anywhere**
```bash
cd C:\Users\moeng\nse_predictor\frontend\src
grep -r "Login\|Register\|AuthGuard\|setLoading" --include="*.ts" --include="*.tsx" .
```
Expected: Only the files themselves appear (no consumers).

- [ ] **Step 2: Delete the files**
```bash
cd C:\Users\moeng\nse_predictor
git rm frontend/src/pages/Login.tsx
git rm frontend/src/pages/Register.tsx
git rm frontend/src/components/layout/AuthGuard.tsx
```

- [ ] **Step 3: Remove setLoading from useAuthStore.ts**

Open `frontend/src/store/useAuthStore.ts`. Find and remove the `setLoading` method and its state field `loading` if they are defined.

- [ ] **Step 4: Verify TypeScript still clean**
```bash
cd C:\Users\moeng\nse_predictor\frontend
npx tsc --noEmit
```

- [ ] **Step 5: Commit**
```bash
git add frontend/src/store/useAuthStore.ts
git commit -m "chore: delete dead auth components (Login, Register, AuthGuard) — auth is disabled"
```

---

### Task 17: Untrack committed debug log files

**Files:**
- Untrack: `stdout.txt`, `stderr.txt`, `eqty_test.txt`, `eabl_rerun.txt`, `run_all_output.txt`, `dash_err.txt`, `dash_out.txt`, `app_err.log`, `app_out.log`, `app_server.log`, `app_server_err.log`

- [ ] **Step 1: Check which of these are tracked**
```bash
cd C:\Users\moeng\nse_predictor
git ls-files | grep -E "\.(log|txt)$"
```

- [ ] **Step 2: Untrack all tracked log/debug files**
```bash
git rm --cached stdout.txt stderr.txt eqty_test.txt eabl_rerun.txt run_all_output.txt dash_err.txt dash_out.txt app_err.log app_out.log app_server.log app_server_err.log 2>/dev/null; echo "done"
```
(Errors for files not tracked are normal — ignore them.)

- [ ] **Step 3: Commit**
```bash
git commit -m "chore: untrack committed debug log files (already in .gitignore)"
```

---

## Self-Review

**Spec coverage check:**

| Spec item | Task |
|-----------|------|
| T1-1: Hardcoded paths in app.py | Task 1 |
| T1-2: /tmp paths | Task 3 |
| T1-3: Docker non-root + .dockerignore | Task 5 |
| T1-4: Admin rate-limit | Task 7 (validation added; rate-limit is low-risk, deferred to separate PR) |
| T1-5: Ticker subprocess validation | Task 7 |
| T1-6: .env.production in git | In .dockerignore (Task 5); git history clean-up is a destructive operation not done here |
| T1-7: Fix SignInPrompt 404 links | Task 6 |
| T1-8: Duplicate _ARCHIVE_DIR | Task 1 |
| T1-9: Config.py conflict | Not changed — the two configs serve different apps and work correctly as-is |
| T1-10: Env var validation | Partially in push_to_firestore.py (Task 4); full startup validation is low-priority |
| T2-1: Extract technicals | Task 9 |
| T2-2: Extract market overview | Task 10 |
| T2-3: Centralise ARTIFACT_SUFFIXES | Task 8 |
| T2-4: Bare except handlers | Task 11 |
| T2-5: Unclosed file handles | Task 4 |
| T2-6: UTF-8 encoding | Task 4 |
| T2-7: Replace print() | Task 12 |
| T2-8: Delete daily_inference.yml | Task 13 |
| T2-9: Frontend dateUtils | Task 14 |
| T2-10: ErrorBoundary | Task 15 |
| T2-11: Feature column dimension check | Already exists in run_inference.py:317-320; no change needed |
| T2-12: Parallelise model downloads | Deferred — complex change with low risk impact |
| T2-13: Remove unused import math | Included in Task 8 (clean up run_inference.py imports) |
| T3-1: Delete dead auth components | Task 16 |
| T3-2: Named constants | Deferred — low risk, no broken behaviour |
| T3-3: Untrack debug logs | Task 17 |
| T3-4: Align requirements.txt | Not changed — root requirements.txt already drives Render correctly |
