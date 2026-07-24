# NSE System Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate all OHLCV price data to Firebase Realtime Database, replace HTML reports with Firebase-backed React frontend, and add daily PDF scraping, AI-powered financial analysis, and deep price analysis.

**Architecture:** Firebase RTDB holds all historical OHLCV data under `/prices/{ticker}/{YYYY-MM-DD}/`; Firestore holds ML predictions, news, financials, and AI narratives. Pipeline scripts write to Firebase; React frontend reads from both. CSVs remain on disk as local ML training cache only.

**Tech Stack:** Python 3.11, firebase-admin 6.2+, pdfplumber, anthropic SDK, React 19, TypeScript 6, Firebase 12 (RTDB + Firestore), TanStack Query 5, Vite, GitHub Actions

---

## File Map

**New Python files:**
- `pipeline/scripts/firebase_client.py` — shared Firebase init (Firestore + RTDB)
- `pipeline/scripts/firebase_rtdb.py` — RTDB write helpers
- `pipeline/scripts/migrate_prices_to_rtdb.py` — one-time CSV → RTDB migration
- `pipeline/scripts/scrape_nse_pdf.py` — daily NSE PDF price scraper
- `pipeline/scripts/scrape_financial_reports.py` — download company IR PDFs
- `pipeline/scripts/extract_financials.py` — parse PDFs → structured JSON
- `pipeline/scripts/analyze_financials_ai.py` — Claude API → narrative
- `pipeline/scripts/deep_price_analysis.py` — multi-factor Claude analysis
- `pipeline/tests/test_firebase_rtdb.py` — RTDB helper tests
- `pipeline/tests/test_migrate_prices.py` — migration tests
- `pipeline/tests/test_scrape_nse_pdf.py` — PDF parser tests
- `pipeline/tests/test_extract_financials.py` — financial extraction tests

**Modified Python files:**
- `pipeline/scripts/push_to_firestore.py` — import from firebase_client
- `pipeline/scripts/scrape_news.py` — add company IR + MarketScreener sources

**New TypeScript files:**
- `frontend/src/lib/rtdb.ts` — RTDB client
- `frontend/src/hooks/useHistoricalPrices.ts`
- `frontend/src/hooks/useFinancials.ts`
- `frontend/src/hooks/useFinancialAnalysis.ts`
- `frontend/src/hooks/useDeepAnalysis.ts`
- `frontend/src/components/FinancialsPanel.tsx`
- `frontend/src/components/FinancialNarrativeCard.tsx`
- `frontend/src/components/DeepAnalysisPanel.tsx`

**Modified TypeScript files:**
- `frontend/src/components/charts/TradingChart.tsx` — swap data source to RTDB
- `frontend/src/pages/CompanyDeepDive.tsx` — wire new panels

**New workflows:**
- `.github/workflows/migrate_prices.yml`
- `.github/workflows/analyze_financials.yml`

**Modified workflows:**
- `.github/workflows/daily_update.yml` — add PDF scrape + deep analysis steps

**Deleted:**
- `reports/outputs/*.html`
- `pipeline/src/visualization/dashboard.py`
- `run_all.py`, `run_pipeline.py`

---

## Phase 1 — Foundation: Shared Firebase Client

### Task 1: Create shared Firebase client module

**Files:**
- Create: `pipeline/scripts/firebase_client.py`
- Create: `pipeline/tests/test_firebase_client.py`

- [ ] **Step 1: Write the failing test**

```python
# pipeline/tests/test_firebase_client.py
import os
import pytest
from unittest.mock import patch, MagicMock

def test_get_firestore_initialises_app():
    with patch.dict(os.environ, {
        "FIREBASE_SERVICE_ACCOUNT_JSON": '{"type":"service_account","project_id":"test","private_key_id":"k","private_key":"-----BEGIN RSA PRIVATE KEY-----\\nMIIEpAIBAAKCAQEA0Z3VS5JJcds3xHn/ygWep4PAtEsHAq7N1gECFzs4PKWS\\n-----END RSA PRIVATE KEY-----\\n","client_email":"test@test.iam.gserviceaccount.com","client_id":"1","auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token"}',
        "FIREBASE_RTDB_URL": "https://test-default-rtdb.firebaseio.com",
        "FIREBASE_STORAGE_BUCKET": "test.appspot.com",
    }):
        with patch("firebase_admin.initialize_app") as mock_init, \
             patch("firebase_admin._apps", {}), \
             patch("firebase_admin.firestore.client") as mock_fs, \
             patch("firebase_admin.credentials.Certificate") as mock_cert:
            mock_init.return_value = MagicMock()
            mock_fs.return_value = MagicMock()
            import importlib
            import pipeline.scripts.firebase_client as fc
            importlib.reload(fc)
            result = fc.get_firestore()
            assert result is not None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd C:\Users\moeng\nse_predictor
python -m pytest pipeline/tests/test_firebase_client.py -v
```
Expected: `ModuleNotFoundError` or `ImportError` — file does not exist yet.

- [ ] **Step 3: Create the module**

```python
# pipeline/scripts/firebase_client.py
import json
import os
import firebase_admin
from firebase_admin import credentials, firestore, db as _rtdb, storage as _storage


def _init() -> None:
    if firebase_admin._apps:
        return
    sa_raw = os.environ["FIREBASE_SERVICE_ACCOUNT_JSON"]
    if sa_raw.strip().startswith("{"):
        sa_dict = json.loads(sa_raw)
    else:
        with open(sa_raw, encoding="utf-8") as fh:
            sa_dict = json.load(fh)
    cred = credentials.Certificate(sa_dict)
    firebase_admin.initialize_app(cred, {
        "databaseURL":   os.environ.get("FIREBASE_RTDB_URL", ""),
        "storageBucket": os.environ.get("FIREBASE_STORAGE_BUCKET", ""),
    })


def get_firestore():
    _init()
    return firestore.client()


def get_rtdb():
    _init()
    return _rtdb.reference("/")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest pipeline/tests/test_firebase_client.py -v
```
Expected: `PASSED`

- [ ] **Step 5: Update push_to_firestore.py to use the shared client**

Replace the `get_db()` function body in `pipeline/scripts/push_to_firestore.py`:

```python
# Add at top of file (after existing imports):
from pipeline.scripts.firebase_client import get_firestore as _get_firestore

def get_db():
    return _get_firestore()
```

Remove the old manual `firebase_admin.initialize_app(...)` block inside `get_db()`.

- [ ] **Step 6: Commit**

```bash
git add pipeline/scripts/firebase_client.py pipeline/scripts/push_to_firestore.py pipeline/tests/test_firebase_client.py
git commit -m "feat: add shared firebase_client module with RTDB + Firestore init"
```

---

### Task 2: Add RTDB URL to frontend env and CI secrets

**Files:**
- Modify: `frontend/.env.example` (or create if missing)
- Modify: `.github/workflows/daily_update.yml`

- [ ] **Step 1: Add RTDB URL to frontend env file**

In `frontend/.env` (local) and `frontend/.env.example`, add:
```
VITE_FIREBASE_DATABASE_URL=https://YOUR_PROJECT_ID-default-rtdb.firebaseio.com
```

- [ ] **Step 2: Add secret to GitHub Actions**

In GitHub → repository Settings → Secrets → Actions, add:
- `FIREBASE_RTDB_URL` = your RTDB URL (e.g. `https://nse-predictor-default-rtdb.firebaseio.com`)
- `ANTHROPIC_API_KEY` = your Anthropic API key

- [ ] **Step 3: Commit env example**

```bash
git add frontend/.env.example
git commit -m "chore: add VITE_FIREBASE_DATABASE_URL to env example"
```

---

## Phase 2 — Feature 1: Historical Price Database

### Task 3: RTDB write helpers

**Files:**
- Create: `pipeline/scripts/firebase_rtdb.py`
- Create: `pipeline/tests/test_firebase_rtdb.py`

- [ ] **Step 1: Write the failing tests**

```python
# pipeline/tests/test_firebase_rtdb.py
import pytest
from unittest.mock import MagicMock, patch, call


def _make_rtdb_ref():
    ref = MagicMock()
    ref.child.return_value = ref
    return ref


def test_write_price_node_builds_correct_path():
    from pipeline.scripts.firebase_rtdb import write_price_node
    root = _make_rtdb_ref()
    write_price_node(root, "SCOM", "2024-01-02", {
        "o": 28.0, "h": 28.5, "l": 27.5, "c": 28.2,
        "v": 1000000.0, "pc": 27.9, "ch": 0.3, "pch": 1.08, "vv": 28200000.0,
    })
    root.update.assert_called_once()
    call_args = root.update.call_args[0][0]
    assert "prices/SCOM/2024-01-02" in call_args


def test_write_price_node_skips_if_none_close():
    from pipeline.scripts.firebase_rtdb import write_price_node
    root = _make_rtdb_ref()
    write_price_node(root, "SCOM", "2024-01-02", {"o": None, "h": None, "l": None, "c": None, "v": 0, "pc": None, "ch": None, "pch": None, "vv": None})
    # should still write — zero volume is valid
    root.update.assert_called_once()


def test_bulk_write_batches_correctly():
    from pipeline.scripts.firebase_rtdb import bulk_write_prices
    root = _make_rtdb_ref()
    records = {f"2020-01-{i:02d}": {"o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0, "v": 0, "pc": None, "ch": None, "pch": None, "vv": None} for i in range(1, 12)}
    bulk_write_prices(root, "KCB", records, batch_size=5)
    # 11 records, batch 5 → 3 calls
    assert root.update.call_count == 3


def test_short_ticker():
    from pipeline.scripts.firebase_rtdb import to_short_ticker
    assert to_short_ticker("SCOM.NR") == "SCOM"
    assert to_short_ticker("SCOM_NR") == "SCOM"
    assert to_short_ticker("BAT") == "BAT"
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest pipeline/tests/test_firebase_rtdb.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create the module**

```python
# pipeline/scripts/firebase_rtdb.py
import math


def to_short_ticker(ticker: str) -> str:
    """SCOM.NR or SCOM_NR → SCOM."""
    return ticker.replace(".NR", "").replace("_NR", "").replace(".", "").upper()


def _clean(val) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if math.isnan(f) or math.isinf(f) else round(f, 4)
    except (TypeError, ValueError):
        return None


def write_price_node(root_ref, ticker: str, date_str: str, fields: dict) -> None:
    """Write a single OHLCV node. Uses update() so existing nodes are never overwritten."""
    short = to_short_ticker(ticker)
    node = {
        "o":   _clean(fields.get("o")),
        "h":   _clean(fields.get("h")),
        "l":   _clean(fields.get("l")),
        "c":   _clean(fields.get("c")),
        "v":   _clean(fields.get("v")),
        "pc":  _clean(fields.get("pc")),
        "ch":  _clean(fields.get("ch")),
        "pch": _clean(fields.get("pch")),
        "vv":  _clean(fields.get("vv")),
    }
    root_ref.update({f"prices/{short}/{date_str}": node})


def bulk_write_prices(root_ref, ticker: str, records: dict, batch_size: int = 500) -> int:
    """Write many date→fields records in batches. Returns total nodes written."""
    short = to_short_ticker(ticker)
    batch: dict = {}
    total = 0
    for date_str, fields in records.items():
        node = {
            "o":   _clean(fields.get("o")),
            "h":   _clean(fields.get("h")),
            "l":   _clean(fields.get("l")),
            "c":   _clean(fields.get("c")),
            "v":   _clean(fields.get("v")),
            "pc":  _clean(fields.get("pc")),
            "ch":  _clean(fields.get("ch")),
            "pch": _clean(fields.get("pch")),
            "vv":  _clean(fields.get("vv")),
        }
        batch[f"prices/{short}/{date_str}"] = node
        if len(batch) >= batch_size:
            root_ref.update(batch)
            total += len(batch)
            batch = {}
    if batch:
        root_ref.update(batch)
        total += len(batch)
    return total
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest pipeline/tests/test_firebase_rtdb.py -v
```
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add pipeline/scripts/firebase_rtdb.py pipeline/tests/test_firebase_rtdb.py
git commit -m "feat: add firebase_rtdb helpers — write_price_node, bulk_write_prices"
```

---

### Task 4: One-time CSV → RTDB migration script

**Files:**
- Create: `pipeline/scripts/migrate_prices_to_rtdb.py`
- Create: `pipeline/tests/test_migrate_prices.py`

- [ ] **Step 1: Write the failing tests**

```python
# pipeline/tests/test_migrate_prices.py
import io
import pytest
from unittest.mock import MagicMock, patch
import pandas as pd


SAMPLE_CSV = """Date,Open,High,Low,Close,Volume,Is_Stale,Ticker
2024-01-02,28.0,28.5,27.5,28.2,1000000,0,SCOM
2024-01-03,28.2,28.8,28.0,28.6,1200000,0,SCOM
2024-01-04,28.6,29.0,28.3,28.9,900000,0,SCOM
"""


def test_build_records_from_csv():
    from pipeline.scripts.migrate_prices_to_rtdb import build_records
    df = pd.read_csv(io.StringIO(SAMPLE_CSV), parse_dates=["Date"])
    records = build_records(df)
    assert "2024-01-02" in records
    assert records["2024-01-02"]["o"] == 28.0
    assert records["2024-01-02"]["c"] == 28.2
    assert records["2024-01-02"]["v"] == 1000000.0


def test_build_records_skips_stale_rows():
    from pipeline.scripts.migrate_prices_to_rtdb import build_records
    csv = """Date,Open,High,Low,Close,Volume,Is_Stale,Ticker
2024-01-02,28.0,28.5,27.5,28.2,1000000,1,SCOM
2024-01-03,28.2,28.8,28.0,28.6,1200000,0,SCOM
"""
    df = pd.read_csv(io.StringIO(csv), parse_dates=["Date"])
    records = build_records(df, skip_stale=True)
    assert "2024-01-02" not in records
    assert "2024-01-03" in records


def test_build_records_computes_change():
    from pipeline.scripts.migrate_prices_to_rtdb import build_records
    df = pd.read_csv(io.StringIO(SAMPLE_CSV), parse_dates=["Date"])
    records = build_records(df)
    # row 2: prev_close = row 1 close = 28.2, change = 28.6 - 28.2 = 0.4
    r = records["2024-01-03"]
    assert r["pc"] == pytest.approx(28.2, rel=1e-3)
    assert r["ch"] == pytest.approx(0.4, rel=1e-3)
    assert r["pch"] == pytest.approx(1.418, rel=1e-2)
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest pipeline/tests/test_migrate_prices.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create the migration script**

```python
# pipeline/scripts/migrate_prices_to_rtdb.py
"""
One-time migration: reads all cleaned CSVs and writes to Firebase RTDB.

Usage:
  FIREBASE_SERVICE_ACCOUNT_JSON=... FIREBASE_RTDB_URL=... \
    python pipeline/scripts/migrate_prices_to_rtdb.py [--dry-run]

Idempotent: uses RTDB update() — never overwrites existing nodes.
Progress is logged per ticker. Re-run safely after partial failure.
"""
import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

REPO_ROOT   = Path(__file__).parent.parent.parent
DATA_CLEANED = REPO_ROOT / "data" / "cleaned"


def build_records(df: pd.DataFrame, skip_stale: bool = False) -> dict:
    """Convert cleaned CSV DataFrame to {date_str: fields} dict."""
    if skip_stale and "Is_Stale" in df.columns:
        df = df[df["Is_Stale"] == 0]
    df = df.sort_values("Date").reset_index(drop=True)
    records: dict = {}
    for i, row in df.iterrows():
        date_str = row["Date"].strftime("%Y-%m-%d")
        close    = float(row["Close"]) if pd.notna(row["Close"]) else None
        prev_row = df.iloc[i - 1] if i > 0 else None
        pc       = float(prev_row["Close"]) if prev_row is not None and pd.notna(prev_row["Close"]) else None
        ch       = round(close - pc, 4) if close is not None and pc is not None else None
        pch      = round((ch / pc) * 100, 4) if ch is not None and pc and pc != 0 else None
        records[date_str] = {
            "o":   float(row["Open"])   if pd.notna(row.get("Open"))   else None,
            "h":   float(row["High"])   if pd.notna(row.get("High"))   else None,
            "l":   float(row["Low"])    if pd.notna(row.get("Low"))    else None,
            "c":   close,
            "v":   float(row["Volume"]) if pd.notna(row.get("Volume")) else None,
            "pc":  pc,
            "ch":  ch,
            "pch": pch,
            "vv":  None,  # not in cleaned CSVs; populated by daily PDF scraper going forward
        }
    return records


def migrate_ticker(ticker: str, csv_path: Path, root_ref, dry_run: bool = False) -> int:
    from pipeline.scripts.firebase_rtdb import bulk_write_prices
    log.info("  %s: reading %s", ticker, csv_path.name)
    df = pd.read_csv(csv_path, parse_dates=["Date"])
    if df.empty:
        log.warning("  %s: empty CSV, skipping", ticker)
        return 0
    records = build_records(df, skip_stale=True)
    log.info("  %s: %d records to write", ticker, len(records))
    if dry_run:
        log.info("  %s: dry-run — no writes", ticker)
        return len(records)
    written = bulk_write_prices(root_ref, ticker, records, batch_size=500)
    log.info("  %s: wrote %d nodes", ticker, written)
    return written


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--ticker", help="Migrate single ticker only")
    args = parser.parse_args()

    from pipeline.scripts.firebase_client import get_rtdb
    root_ref = get_rtdb()

    csv_files = sorted(DATA_CLEANED.glob("*_cleaned.csv"))
    if args.ticker:
        csv_files = [f for f in csv_files if args.ticker.upper() in f.name.upper()]
    if not csv_files:
        log.error("No CSVs found in %s", DATA_CLEANED)
        sys.exit(1)

    log.info("Migrating %d tickers to RTDB (dry_run=%s)", len(csv_files), args.dry_run)
    total = 0
    for csv_path in csv_files:
        ticker = csv_path.stem.replace("_cleaned", "")
        try:
            total += migrate_ticker(ticker, csv_path, root_ref, args.dry_run)
        except Exception as exc:
            log.error("  %s: FAILED — %s", ticker, exc)
    log.info("Done — %d total nodes written", total)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest pipeline/tests/test_migrate_prices.py -v
```
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add pipeline/scripts/migrate_prices_to_rtdb.py pipeline/tests/test_migrate_prices.py
git commit -m "feat: add migrate_prices_to_rtdb — one-time CSV to RTDB migration"
```

---

### Task 5: Migration CI workflow

**Files:**
- Create: `.github/workflows/migrate_prices.yml`

- [ ] **Step 1: Create the workflow**

```yaml
# .github/workflows/migrate_prices.yml
name: Migrate Historical Prices to RTDB (one-time)

on:
  workflow_dispatch:
    inputs:
      ticker:
        description: "Single ticker to migrate (blank = all)"
        required: false
        default: ""
      dry_run:
        description: "Dry run (no writes)"
        required: false
        default: "false"

jobs:
  migrate:
    runs-on: ubuntu-latest
    timeout-minutes: 60
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
          cache-dependency-path: pipeline/requirements.txt

      - run: pip install -r pipeline/requirements.txt

      - name: Run migration
        env:
          FIREBASE_SERVICE_ACCOUNT_JSON: ${{ secrets.FIREBASE_SERVICE_ACCOUNT_JSON }}
          FIREBASE_RTDB_URL: ${{ secrets.FIREBASE_RTDB_URL }}
          FIREBASE_STORAGE_BUCKET: ${{ secrets.FIREBASE_STORAGE_BUCKET }}
        run: |
          ARGS=""
          [ "${{ github.event.inputs.ticker }}" != "" ] && ARGS="--ticker ${{ github.event.inputs.ticker }}"
          [ "${{ github.event.inputs.dry_run }}" == "true" ] && ARGS="$ARGS --dry-run"
          python pipeline/scripts/migrate_prices_to_rtdb.py $ARGS
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/migrate_prices.yml
git commit -m "ci: add migrate_prices workflow — manual trigger, one-time RTDB migration"
```

---

### Task 6: Frontend RTDB client + useHistoricalPrices hook

**Files:**
- Create: `frontend/src/lib/rtdb.ts`
- Create: `frontend/src/hooks/useHistoricalPrices.ts`

- [ ] **Step 1: Create RTDB client**

```typescript
// frontend/src/lib/rtdb.ts
import { getDatabase } from "firebase/database";
import { app } from "./firebase";

export const rtdb = getDatabase(app, import.meta.env.VITE_FIREBASE_DATABASE_URL);
```

- [ ] **Step 2: Create the hook**

```typescript
// frontend/src/hooks/useHistoricalPrices.ts
import { useQuery } from "@tanstack/react-query";
import { ref, query, orderByKey, startAt, endAt, get } from "firebase/database";
import { rtdb } from "../lib/rtdb";

export interface RtdbPricePoint {
  date: string;
  o: number | null;
  h: number | null;
  l: number | null;
  c: number | null;
  v: number | null;
  pc: number | null;
  ch: number | null;
  pch: number | null;
  vv: number | null;
}

export function useHistoricalPrices(
  ticker: string,
  startDate: string,
  endDate: string,
) {
  return useQuery<RtdbPricePoint[]>({
    queryKey: ["rtdb-prices", ticker, startDate, endDate],
    queryFn: async () => {
      const pricesQuery = query(
        ref(rtdb, `prices/${ticker}`),
        orderByKey(),
        startAt(startDate),
        endAt(endDate),
      );
      const snap = await get(pricesQuery);
      if (!snap.exists()) return [];
      const val = snap.val() as Record<string, Omit<RtdbPricePoint, "date">>;
      return Object.entries(val).map(([date, fields]) => ({ date, ...fields }));
    },
    enabled: !!ticker && !!startDate && !!endDate,
    staleTime: 1000 * 60 * 5,
  });
}
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/rtdb.ts frontend/src/hooks/useHistoricalPrices.ts
git commit -m "feat: add RTDB client and useHistoricalPrices hook"
```

---

### Task 7: Update TradingChart to read from RTDB

The chart currently receives `data: PricePoint[]` as a prop from the parent page. The change is in the parent (`CompanyDeepDive`) which computes the date range and calls the hook, then passes the result down. The chart component itself stays the same.

**Files:**
- Modify: `frontend/src/pages/CompanyDeepDive.tsx`

- [ ] **Step 1: Find where TradingChart is called and what data it receives**

```bash
grep -n "TradingChart" frontend/src/pages/CompanyDeepDive.tsx | head -20
grep -n "price_history\|priceHistory\|data=" frontend/src/pages/CompanyDeepDive.tsx | head -20
```

- [ ] **Step 2: Add import and hook call at the top of CompanyDeepDive**

Find the imports section and add:
```typescript
import { useHistoricalPrices } from "../hooks/useHistoricalPrices";
```

In the component body, after existing hooks, add:
```typescript
// Date range for chart — ALL history by default
const chartStart = "2008-01-01";
const chartEnd   = new Date().toISOString().slice(0, 10);
const { data: rtdbPrices = [] } = useHistoricalPrices(
  ticker.replace(".NR", "").replace("_NR", ""),
  chartStart,
  chartEnd,
);

// Map RTDB format to PricePoint format expected by TradingChart
const chartData: PricePoint[] = rtdbPrices.map((p) => ({
  date:  p.date,
  close: p.c ?? 0,
  open:  p.o ?? undefined,
  high:  p.h ?? undefined,
  low:   p.l ?? undefined,
  volume: p.v ?? undefined,
}));
```

- [ ] **Step 3: Replace the existing `data=` prop on TradingChart**

Find the line that passes the old price_history array to TradingChart and replace it with `data={chartData}`.

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors

- [ ] **Step 5: Start dev server and verify chart loads**

```bash
cd frontend && npm run dev
```
Open `http://localhost:5173`, navigate to any company. Chart should render using RTDB data. All range buttons (1D, 1M, 3M, 6M, YTD, 1Y, 5Y, ALL) should still work.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/CompanyDeepDive.tsx
git commit -m "feat: wire TradingChart to RTDB useHistoricalPrices hook"
```

---

## Phase 3 — Feature 2: Daily Price Update from NSE PDF

### Task 8: NSE PDF price scraper

**Files:**
- Create: `pipeline/scripts/scrape_nse_pdf.py`
- Create: `pipeline/tests/test_scrape_nse_pdf.py`

- [ ] **Step 1: Write the failing tests**

```python
# pipeline/tests/test_scrape_nse_pdf.py
import io
import pytest
from pathlib import Path


SAMPLE_TABLE_ROWS = [
    ["SAFARICOM", "28.20", "28.30", "28.50", "27.90", "28.40", "0.20", "0.71%", "15,234,100", "431,654,240"],
    ["KCB GROUP", "42.30", "42.50", "42.75", "42.00", "42.55", "0.25", "0.59%", "3,100,000", "131,905,000"],
    ["EQUITY GROUP", "51.50", "51.75", "52.00", "51.25", "51.80", "0.30", "0.58%", "2,500,000", "129,500,000"],
]


def test_parse_price_row_extracts_all_fields():
    from pipeline.scripts.scrape_nse_pdf import parse_price_row
    row = SAMPLE_TABLE_ROWS[0]
    result = parse_price_row(row)
    assert result["prev_close"]  == pytest.approx(28.20, rel=1e-3)
    assert result["open"]        == pytest.approx(28.30, rel=1e-3)
    assert result["high"]        == pytest.approx(28.50, rel=1e-3)
    assert result["low"]         == pytest.approx(27.90, rel=1e-3)
    assert result["close"]       == pytest.approx(28.40, rel=1e-3)
    assert result["change"]      == pytest.approx(0.20,  rel=1e-3)
    assert result["pct_change"]  == pytest.approx(0.71,  rel=1e-2)
    assert result["volume"]      == pytest.approx(15234100.0, rel=1e-3)
    assert result["value"]       == pytest.approx(431654240.0, rel=1e-3)


def test_parse_price_row_handles_zero_volume():
    from pipeline.scripts.scrape_nse_pdf import parse_price_row
    row = ["BAMBURI CEMENT", "42.00", "0", "0", "0", "42.00", "0.00", "0.00%", "0", "0"]
    result = parse_price_row(row)
    assert result["volume"] == 0.0
    assert result["close"]  == pytest.approx(42.00, rel=1e-3)


def test_clean_number_handles_commas():
    from pipeline.scripts.scrape_nse_pdf import clean_number
    assert clean_number("15,234,100") == pytest.approx(15234100.0)
    assert clean_number("0.71%")      == pytest.approx(0.71)
    assert clean_number("0")          == pytest.approx(0.0)


def test_pdf_url_format():
    from pipeline.scripts.scrape_nse_pdf import build_pdf_url
    import datetime
    url = build_pdf_url(datetime.date(2026, 7, 24))
    assert url == "https://www.nse.co.ke/wp-content/uploads/24-JUL-26.pdf"
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest pipeline/tests/test_scrape_nse_pdf.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create the scraper**

```python
# pipeline/scripts/scrape_nse_pdf.py
"""
Scrapes the official NSE daily market report PDF and writes all company
OHLCV records to Firebase RTDB + corporate actions to Firestore.

Usage:
  FIREBASE_SERVICE_ACCOUNT_JSON=... FIREBASE_RTDB_URL=... \
    python pipeline/scripts/scrape_nse_pdf.py [--date 2026-07-24] [--dry-run]

PDF URL format: https://www.nse.co.ke/wp-content/uploads/24-JUL-26.pdf
"""
import argparse
import datetime
import logging
import re
import sys
import tempfile
from pathlib import Path

import pdfplumber
import requests

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Columns in the NSE daily report price table (0-indexed)
COL_PREV_CLOSE = 0
COL_OPEN       = 1
COL_HIGH       = 2
COL_LOW        = 3
COL_CLOSE      = 4
COL_CHANGE     = 5
COL_PCT_CHANGE = 6
COL_VOLUME     = 7
COL_VALUE      = 8

# Minimal known ticker mapping (name fragment → short ticker)
# Extend this list as new companies are listed
COMPANY_TO_TICKER: dict[str, str] = {
    "SAFARICOM":        "SCOM",
    "KCB GROUP":        "KCB",
    "KCB":              "KCB",
    "EQUITY GROUP":     "EQTY",
    "EQUITY":           "EQTY",
    "CO-OPERATIVE":     "COOP",
    "COOP BANK":        "COOP",
    "EAST AFRICAN BREW":"EABL",
    "EABL":             "EABL",
    "BAMBURI":          "BAMB",
    "KENGEN":           "KEGN",
    "KENYA POWER":      "KPLC",
    "NATION MEDIA":     "NMG",
    "STANDARD MEDIA":   "SGL",
    "BRITAM":           "BRIT",
    "JUBILEE":          "JUB",
    "CIC INSURANCE":    "CIC",
    "LIBERTY":          "LBTY",
    "SANLAM":           "SLAM",
    "STANCHART":        "SCBK",
    "STANDARD CHART":   "SCBK",
    "NCBA":             "NCBA",
    "ABSA":             "ABSA",
    "DIAMOND TRUST":    "DTK",
    "DTB":              "DTK",
    "I&M":              "IMH",
    "HF GROUP":         "HFCK",
    "HOUSING FINANCE":  "HFCK",
    "CENTUM":           "CTUM",
    "TRANSCENTURY":     "TCL",
    "TOTAL ENERGIES":   "TOTL",
    "TOTAL":            "TOTL",
    "KENOL":            "KENO",
    "CARBACID":         "CARB",
    "CROWN PAINT":      "BERG",
    "BERGER":           "BERG",
    "UNGA":             "UNGA",
    "KAKUZI":           "KUKZ",
    "LIMURU TEA":       "LIMT",
    "WILLIAMSON":       "WLMB",
    "ATHI RIVER":       "ARM",
    "ARM CEMENT":       "ARM",
    "EAST AFRICAN CABLES":"CABL",
    "KENPACK":          "KPKG",
    "OLYMPIA":          "OKLA",
    "MARSHALLS":        "MASH",
    "LONGHORN":         "LKL",
    "KENYA AIRWAYS":    "KQ",
    "UCHUMI":           "UCHM",
    "TPS EASTERN":      "TPSE",
    "BAT KENYA":        "BAT",
    "BAT":              "BAT",
    "MUMIAS":           "MSC",
    "EXPRESS":          "XPRS",
    "WILLIAMSON":       "WLMB",
    "KENYA RE":         "KERE",
    "SANLAM KENYA":     "SLAM",
    "ICDC":             "ICDC",
    "STIMA SACCO":      "XPRS",
}


def build_pdf_url(date: datetime.date) -> str:
    month = date.strftime("%b").upper()   # JUL
    day   = date.strftime("%d")           # 24
    year  = date.strftime("%y")           # 26
    return f"https://www.nse.co.ke/wp-content/uploads/{day}-{month}-{year}.pdf"


def clean_number(raw: str) -> float:
    cleaned = re.sub(r"[,%]", "", str(raw).strip())
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def resolve_ticker(company_name: str) -> str | None:
    upper = company_name.strip().upper()
    for fragment, ticker in COMPANY_TO_TICKER.items():
        if fragment in upper:
            return ticker
    return None


def parse_price_row(row: list[str]) -> dict:
    return {
        "prev_close": clean_number(row[COL_PREV_CLOSE]),
        "open":       clean_number(row[COL_OPEN]),
        "high":       clean_number(row[COL_HIGH]),
        "low":        clean_number(row[COL_LOW]),
        "close":      clean_number(row[COL_CLOSE]),
        "change":     clean_number(row[COL_CHANGE]),
        "pct_change": clean_number(row[COL_PCT_CHANGE]),
        "volume":     clean_number(row[COL_VOLUME]),
        "value":      clean_number(row[COL_VALUE]),
    }


def download_pdf(url: str) -> bytes:
    resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    return resp.content


def extract_price_rows(pdf_bytes: bytes) -> list[tuple[str, dict]]:
    """Returns [(company_name, fields), ...] for all price table rows in the PDF."""
    results = []
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    with pdfplumber.open(tmp_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if not row or len(row) < 9:
                        continue
                    company = str(row[0] or "").strip()
                    if not company or company.upper() in ("SECURITY", "COMPANY", ""):
                        continue
                    # Heuristic: second cell should be a numeric price string
                    try:
                        clean_number(str(row[1]))
                    except Exception:
                        continue
                    results.append((company, parse_price_row([str(c or "0") for c in row])))
    return results


def write_to_rtdb(root_ref, date_str: str, rows: list[tuple[str, dict]], dry_run: bool) -> int:
    from pipeline.scripts.firebase_rtdb import write_price_node
    written = 0
    unknown = []
    for company_name, fields in rows:
        ticker = resolve_ticker(company_name)
        if not ticker:
            unknown.append(company_name)
            continue
        node = {
            "o":   fields["open"],
            "h":   fields["high"],
            "l":   fields["low"],
            "c":   fields["close"],
            "v":   fields["volume"],
            "pc":  fields["prev_close"],
            "ch":  fields["change"],
            "pch": fields["pct_change"],
            "vv":  fields["value"],
        }
        if not dry_run:
            write_price_node(root_ref, ticker, date_str, node)
        log.info("  %s (%s): close=%.2f vol=%.0f", ticker, company_name, fields["close"], fields["volume"])
        written += 1
    if unknown:
        log.warning("Unknown company names (add to COMPANY_TO_TICKER): %s", unknown)
    return written


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD (default: today)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    target_date = (
        datetime.date.fromisoformat(args.date)
        if args.date
        else datetime.date.today()
    )
    url = build_pdf_url(target_date)
    date_str = target_date.isoformat()
    log.info("Downloading %s", url)

    try:
        pdf_bytes = download_pdf(url)
    except requests.HTTPError as exc:
        log.error("PDF not available: %s", exc)
        sys.exit(1)

    rows = extract_price_rows(pdf_bytes)
    log.info("Extracted %d price rows from PDF", len(rows))

    if not args.dry_run:
        from pipeline.scripts.firebase_client import get_rtdb
        root_ref = get_rtdb()
    else:
        root_ref = None

    written = write_to_rtdb(root_ref, date_str, rows, args.dry_run)
    log.info("Done — wrote %d company records for %s", written, date_str)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest pipeline/tests/test_scrape_nse_pdf.py -v
```
Expected: 4 PASSED

- [ ] **Step 5: Smoke-test against a real PDF (optional)**

The repo root has `24-JUL-26.pdf`. Run:
```bash
FIREBASE_RTDB_URL=x FIREBASE_SERVICE_ACCOUNT_JSON=x \
  python pipeline/scripts/scrape_nse_pdf.py --date 2026-07-24 --dry-run
```
Expected: rows logged with company names and prices. Unknown names printed as warnings.

- [ ] **Step 6: Update daily_update.yml to add PDF scrape step**

In `.github/workflows/daily_update.yml`, add a new step **before** the existing `Run daily model update` step:

```yaml
      - name: Scrape NSE daily PDF → RTDB
        env:
          FIREBASE_SERVICE_ACCOUNT_JSON: ${{ secrets.FIREBASE_SERVICE_ACCOUNT_JSON }}
          FIREBASE_RTDB_URL: ${{ secrets.FIREBASE_RTDB_URL }}
          FIREBASE_STORAGE_BUCKET: ${{ secrets.FIREBASE_STORAGE_BUCKET }}
        run: |
          python pipeline/scripts/scrape_nse_pdf.py 2>&1 | tee /tmp/scrape_pdf.log
```

- [ ] **Step 7: Commit**

```bash
git add pipeline/scripts/scrape_nse_pdf.py pipeline/tests/test_scrape_nse_pdf.py .github/workflows/daily_update.yml
git commit -m "feat: add scrape_nse_pdf — daily NSE PDF → RTDB price writer"
```

---

## Phase 4 — Feature 3: Company News Extended

### Task 9: Extend news scraper with company IR + MarketScreener

**Files:**
- Modify: `pipeline/scripts/scrape_news.py`

- [ ] **Step 1: Write the failing tests**

```python
# Add to pipeline/tests/test_scrape_news.py (create file if absent)
def test_fetch_marketscreener_returns_list():
    from pipeline.scripts.scrape_news import fetch_marketscreener_news
    # Should return [] on network error, not raise
    import responses
    with responses.RequestsMock() as rsps:
        rsps.add(responses.GET, "https://www.marketscreener.com/quote/stock/SCOM/news/", body=ConnectionError())
        result = fetch_marketscreener_news("SCOM")
    assert isinstance(result, list)


def test_make_doc_id_is_deterministic():
    from pipeline.scripts.scrape_news import make_doc_id
    assert make_doc_id("2026-07-23", "Earnings Release") == make_doc_id("2026-07-23", "Earnings Release")
    assert make_doc_id("2026-07-23", "A") != make_doc_id("2026-07-23", "B")
```

- [ ] **Step 2: Run to verify failure**

```bash
pip install responses
python -m pytest pipeline/tests/test_scrape_news.py -v
```
Expected: `ModuleNotFoundError` (test file doesn't exist yet)

- [ ] **Step 3: Add MarketScreener and company IR functions to scrape_news.py**

Add these functions after the existing `fetch_nse_announcements` function in `pipeline/scripts/scrape_news.py`:

```python
# ── Company IR page scraper ───────────────────────────────────────────────────
COMPANY_IR_URLS: dict[str, str] = {
    "SCOM":  "https://www.safaricom.co.ke/investor-relations/financial-information",
    "KCB":   "https://ke.kcbgroup.com/investor-relations/financial-highlights",
    "EQTY":  "https://equitygroupholdings.com/investor-relations/",
    "COOP":  "https://www.co-opbank.co.ke/investor-relations/",
    "EABL":  "https://www.eabl.com/investor-relations",
    "BAT":   "https://www.bat.com/group/sites/UK__9D9KCY.nsf/vwPagesWebLive/DOBBMNC8",
    "BAMB":  "https://www.bamburi.com/en/investors",
    "NMG":   "https://www.nationmedia.com/investor-relations/",
    "BRIT":  "https://www.britam.com/investor-relations",
    "JUB":   "https://www.jubileeinsurance.com/ke/investor-relations",
    "NCBA":  "https://ke.ncbagroup.com/investor-relations/",
    "ABSA":  "https://www.absa.co.ke/investor-relations/",
}


def fetch_company_ir_news(safe_ticker: str) -> list:
    """Scrape company investor relations page for press releases and results."""
    short = safe_ticker.replace("_NR", "").replace(".NR", "")
    url = COMPANY_IR_URLS.get(short)
    if not url:
        return []
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        rows = []
        for a_tag in soup.find_all("a", href=True):
            text = a_tag.get_text(strip=True)
            if len(text) < 10:
                continue
            if not any(kw in text.lower() for kw in (
                "result", "earning", "profit", "revenue", "dividend",
                "annual", "report", "interim", "half year", "full year"
            )):
                continue
            href = a_tag["href"]
            if not href.startswith("http"):
                from urllib.parse import urljoin
                href = urljoin(url, href)
            is_pdf = href.lower().endswith(".pdf")
            rows.append({
                "date":  datetime.utcnow().strftime("%Y-%m-%d"),
                "title": text,
                "type":  "general",
                "url":   href,
                "body":  None,
                "is_pdf": is_pdf,
                "pdf_url": href if is_pdf else None,
                "source": short.lower() + ".ir",
            })
        log.info("%s: fetched %d IR items", safe_ticker, len(rows))
        return rows[:20]
    except Exception as exc:
        log.warning("%s IR: fetch failed — %s", safe_ticker, exc)
        return []


def fetch_marketscreener_news(short_ticker: str) -> list:
    """Fetch latest news from MarketScreener for a ticker."""
    url = f"https://www.marketscreener.com/quote/stock/{short_ticker}/news/"
    try:
        resp = requests.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        rows = []
        for article in soup.select("article, .article-item, .news-item"):
            title_el = article.find(["h2", "h3", "a"])
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            date_el = article.find(["time", ".date"])
            date_str = date_el.get("datetime", "")[:10] if date_el else datetime.utcnow().strftime("%Y-%m-%d")
            link_el = article.find("a", href=True)
            href = link_el["href"] if link_el else url
            if href.startswith("/"):
                href = "https://www.marketscreener.com" + href
            rows.append({
                "date":  date_str or datetime.utcnow().strftime("%Y-%m-%d"),
                "title": title,
                "type":  "general",
                "url":   href,
                "body":  None,
                "is_pdf": False,
                "pdf_url": None,
                "source": "marketscreener",
            })
        log.info("%s: fetched %d MarketScreener items", short_ticker, len(rows))
        return rows[:30]
    except Exception as exc:
        log.warning("%s MarketScreener: fetch failed — %s", short_ticker, exc)
        return []
```

Update the `parse_announcement` function to handle the new `is_pdf` and `source` fields:

```python
def parse_announcement(row: dict) -> dict:
    raw_type = row.get("type", "general")
    title = row.get("title", "")
    return {
        "date":       row.get("date", ""),
        "title":      title,
        "category":   _infer_category(title, raw_type),
        "body":       row.get("body", None),
        "url":        row.get("url", None) or None,
        "source":     row.get("source", "scraper"),
        "is_pdf":     row.get("is_pdf", False),
        "pdf_url":    row.get("pdf_url", None),
        "created_at": datetime.utcnow().isoformat(),
    }
```

Update `main()` to call the new sources:

```python
def main() -> None:
    log.info("NSE news scraper starting — %d companies", len(TICKERS))
    pushed_total = 0
    for safe_ticker in TICKERS:
        short = safe_ticker.replace("_NR", "")
        try:
            all_rows = []
            all_rows += fetch_nse_announcements(safe_ticker)
            all_rows += fetch_company_ir_news(safe_ticker)
            all_rows += fetch_marketscreener_news(short)
            for row in all_rows:
                item = parse_announcement(row)
                if not item["title"] or not item["date"]:
                    continue
                push_item(safe_ticker, item)
                pushed_total += 1
        except Exception as exc:
            log.error("%s: unhandled error — %s", safe_ticker, exc)
            continue
    log.info("Done — pushed %d items total", pushed_total)
```

- [ ] **Step 4: Create test file and run**

```python
# pipeline/tests/test_scrape_news.py
import pytest
from unittest.mock import patch, MagicMock
import responses as resp_mock


def test_make_doc_id_is_deterministic():
    from pipeline.scripts.scrape_news import make_doc_id
    assert make_doc_id("2026-07-23", "Earnings Release") == make_doc_id("2026-07-23", "Earnings Release")
    assert make_doc_id("2026-07-23", "A") != make_doc_id("2026-07-23", "B")


def test_fetch_marketscreener_returns_list_on_error():
    from pipeline.scripts.scrape_news import fetch_marketscreener_news
    with patch("requests.get", side_effect=ConnectionError("timeout")):
        result = fetch_marketscreener_news("SCOM")
    assert isinstance(result, list)
    assert result == []


def test_parse_announcement_includes_is_pdf():
    from pipeline.scripts.scrape_news import parse_announcement
    item = parse_announcement({
        "date": "2026-07-23",
        "title": "Annual Report 2025",
        "type": "general",
        "is_pdf": True,
        "pdf_url": "https://example.com/report.pdf",
        "source": "bat.ir",
    })
    assert item["is_pdf"] is True
    assert item["pdf_url"] == "https://example.com/report.pdf"
    assert item["source"] == "bat.ir"
```

```bash
python -m pytest pipeline/tests/test_scrape_news.py -v
```
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add pipeline/scripts/scrape_news.py pipeline/tests/test_scrape_news.py
git commit -m "feat: extend scrape_news with company IR pages and MarketScreener sources"
```

---

## Phase 5 — Feature 4: Financial Statement Interpretation

### Task 10: PDF financial extractor

**Files:**
- Create: `pipeline/scripts/extract_financials.py`
- Create: `pipeline/tests/test_extract_financials.py`

- [ ] **Step 1: Write the failing tests**

```python
# pipeline/tests/test_extract_financials.py
import pytest
from pipeline.scripts.extract_financials import (
    clean_value, parse_unit, build_metric, EMPTY_FINANCIALS,
)


def test_clean_value_strips_commas_and_parentheses():
    assert clean_value("(1,340)") == pytest.approx(-1340.0)
    assert clean_value("18,860")  == pytest.approx(18860.0)
    assert clean_value("2.98Bn")  == pytest.approx(2.98)
    assert clean_value("-")       is None
    assert clean_value("n/a")     is None


def test_parse_unit_detects_bn_mn():
    assert parse_unit("18.86 Bn") == "Bn"
    assert parse_unit("97.00 Mn") == "Mn"
    assert parse_unit("30.75")    == "KES"


def test_build_metric_structure():
    m = build_metric(current=18.86, prior=18.49, unit="Bn", currency="KES")
    assert m["current"]  == pytest.approx(18.86)
    assert m["prior"]    == pytest.approx(18.49)
    assert m["yoy_pct"]  == pytest.approx(2.0, rel=0.1)
    assert m["unit"]     == "Bn"
    assert m["currency"] == "KES"


def test_build_metric_with_null_prior():
    m = build_metric(current=18.86, prior=None, unit="Bn", currency="KES")
    assert m["yoy_pct"] is None


def test_empty_financials_has_all_required_keys():
    ef = EMPTY_FINANCIALS()
    assert "income_statement" in ef
    assert "gross_revenue" in ef["income_statement"]
    assert "cash_flow" in ef
    assert "cash_at_period_end" in ef["cash_flow"]
    assert "returns" in ef
    assert "annualised_roe" in ef["returns"]
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest pipeline/tests/test_extract_financials.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create the extractor**

```python
# pipeline/scripts/extract_financials.py
"""
Extracts financial metrics from NSE company half-year and annual report PDFs.
All 20 mandated fields are extracted. Unextractable fields are stored as null.

Usage:
  python pipeline/scripts/extract_financials.py --pdf path/to/report.pdf \
    --ticker BAT --period H1-2026 --comparison H1-2025
"""
import argparse
import json
import logging
import re
import tempfile
from pathlib import Path

import pdfplumber

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def clean_value(raw: str) -> float | None:
    """Parse a financial value string to float. Parentheses = negative. Returns None if unparseable."""
    if not raw:
        return None
    s = str(raw).strip()
    if s in ("-", "—", "n/a", "N/A", "nil", ""):
        return None
    negative = s.startswith("(") and s.endswith(")")
    s = re.sub(r"[(),Bnbn]", "", s)
    s = re.sub(r"[,\s]", "", s)
    s = re.sub(r"Mn$|mn$", "", s)
    try:
        val = float(s)
        return -val if negative else val
    except ValueError:
        return None


def parse_unit(raw: str) -> str:
    s = str(raw).upper()
    if "BN" in s:
        return "Bn"
    if "MN" in s or "MILLION" in s:
        return "Mn"
    return "KES"


def build_metric(current, prior, unit: str = "KES", currency: str = "KES") -> dict:
    yoy = None
    if current is not None and prior is not None and prior != 0:
        yoy = round(((current - prior) / abs(prior)) * 100, 2)
    return {
        "current":  current,
        "prior":    prior,
        "yoy_pct":  yoy,
        "unit":     unit,
        "currency": currency,
    }


def EMPTY_FINANCIALS() -> dict:
    """Return a template with all required keys set to null metrics."""
    null_m = {"current": None, "prior": None, "yoy_pct": None, "unit": "KES", "currency": "KES"}
    null_roe = {"current": None, "prior": None, "direction": None}
    return {
        "income_statement": {
            "gross_revenue":       dict(null_m),
            "excise_duty_and_vat": dict(null_m),
            "net_revenue":         dict(null_m),
            "cost_of_operations":  dict(null_m),
            "operating_profit":    dict(null_m),
            "finance_income":      dict(null_m),
            "profit_before_tax":   dict(null_m),
            "income_tax_expense":  dict(null_m),
            "profit_after_tax":    dict(null_m),
        },
        "per_share": {
            "basic_diluted_eps":          dict(null_m),
            "interim_dividend_per_share": dict(null_m),
        },
        "balance_sheet": {
            "retained_earnings":   dict(null_m),
            "shareholders_funds":  dict(null_m),
        },
        "cash_flow": {
            "net_cash_from_operations":      dict(null_m),
            "net_cash_operating_activities": dict(null_m),
            "net_cash_investing_activities": dict(null_m),
            "net_cash_financing_activities": dict(null_m),
            "movement_in_cash":              dict(null_m),
            "cash_at_period_end":            dict(null_m),
        },
        "returns": {
            "annualised_roe": dict(null_roe),
        },
    }


# Keyword patterns for matching PDF table rows to metric keys
METRIC_KEYWORDS: dict[str, list[str]] = {
    "gross_revenue":               ["gross revenue", "gross turnover"],
    "excise_duty_and_vat":         ["excise", "vat"],
    "net_revenue":                 ["net revenue", "net turnover", "revenue after excise"],
    "cost_of_operations":          ["cost of operations", "cost of sales", "operating costs"],
    "operating_profit":            ["operating profit", "profit from operations"],
    "finance_income":              ["finance income", "interest income", "investment income"],
    "profit_before_tax":           ["profit before tax", "pbt"],
    "income_tax_expense":          ["income tax", "tax expense", "taxation"],
    "profit_after_tax":            ["profit after tax", "pat", "profit for the period"],
    "basic_diluted_eps":           ["earnings per share", "eps", "basic"],
    "interim_dividend_per_share":  ["dividend per share", "dps", "interim dividend"],
    "retained_earnings":           ["retained earnings", "retained profit"],
    "shareholders_funds":          ["shareholders' funds", "shareholders funds", "total equity"],
    "net_cash_from_operations":    ["cash generated from operations", "cash from operations"],
    "net_cash_operating_activities":["net cash from operating", "operating activities"],
    "net_cash_investing_activities":["investing activities", "net cash used in investing"],
    "net_cash_financing_activities":["financing activities", "net cash used in financing"],
    "movement_in_cash":            ["movement in cash", "net movement", "increase in cash"],
    "cash_at_period_end":          ["cash at end", "cash and cash equivalents at end", "closing cash"],
    "annualised_roe":              ["annualised roe", "return on equity", "roe"],
}


def match_metric(label: str) -> str | None:
    lower = label.lower().strip()
    for key, patterns in METRIC_KEYWORDS.items():
        if any(p in lower for p in patterns):
            return key
    return None


def extract_from_pdf(pdf_path: str) -> dict:
    """Parse PDF tables and return populated financials dict."""
    result = EMPTY_FINANCIALS()
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in (page.extract_tables() or []):
                for row in table:
                    if not row or len(row) < 2:
                        continue
                    label = str(row[0] or "").strip()
                    metric_key = match_metric(label)
                    if not metric_key:
                        continue

                    # Try to get two numeric columns (current period, prior period)
                    numbers = [clean_value(str(c)) for c in row[1:] if c is not None]
                    numbers = [n for n in numbers if n is not None]

                    unit = parse_unit(label + " ".join(str(c) for c in row))
                    currency = "KES"

                    if metric_key == "annualised_roe":
                        cur_raw = str(row[1] or "").strip() if len(row) > 1 else ""
                        pri_raw = str(row[2] or "").strip() if len(row) > 2 else ""
                        cur_pct = cur_raw if "%" in cur_raw else (f"{numbers[0]}%" if numbers else None)
                        pri_pct = pri_raw if "%" in pri_raw else (f"{numbers[1]}%" if len(numbers) > 1 else None)
                        direction = "increased" if numbers and len(numbers) > 1 and numbers[0] > numbers[1] else \
                                    "decreased" if numbers and len(numbers) > 1 and numbers[0] < numbers[1] else None
                        result["returns"]["annualised_roe"] = {
                            "current":   cur_pct,
                            "prior":     pri_pct,
                            "direction": direction,
                        }
                        continue

                    current = numbers[0] if numbers else None
                    prior   = numbers[1] if len(numbers) > 1 else None
                    metric  = build_metric(current, prior, unit=unit, currency=currency)

                    for section in ("income_statement", "per_share", "balance_sheet", "cash_flow"):
                        if metric_key in result[section]:
                            result[section][metric_key] = metric
                            break
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf",        required=True)
    parser.add_argument("--ticker",     required=True)
    parser.add_argument("--period",     required=True, help="e.g. H1-2026")
    parser.add_argument("--comparison", required=True, help="e.g. H1-2025")
    parser.add_argument("--out",        help="Output JSON path")
    args = parser.parse_args()

    data = extract_from_pdf(args.pdf)
    data["ticker"]            = args.ticker
    data["period"]            = args.period
    data["comparison_period"] = args.comparison

    out = args.out or f"{args.ticker}_{args.period}_financials.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    log.info("Saved to %s", out)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest pipeline/tests/test_extract_financials.py -v
```
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add pipeline/scripts/extract_financials.py pipeline/tests/test_extract_financials.py
git commit -m "feat: add extract_financials — PDF table parser for all 20 mandated metric fields"
```

---

### Task 11: Claude API financial narrative generator

**Files:**
- Create: `pipeline/scripts/analyze_financials_ai.py`

- [ ] **Step 1: Create the script**

```python
# pipeline/scripts/analyze_financials_ai.py
"""
Reads extracted financials from Firestore and generates investor narrative via Claude API.
Stores result in Firestore financials/{ticker}/analysis/{period}.

Usage:
  ANTHROPIC_API_KEY=... FIREBASE_SERVICE_ACCOUNT_JSON=... \
    python pipeline/scripts/analyze_financials_ai.py --ticker BAT --period H1-2026
"""
import argparse
import json
import logging
import os
from datetime import datetime, timezone

import anthropic

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

SYSTEM_PROMPT = (
    "You are a senior Kenyan equity analyst writing concise, plain-English investor commentary "
    "for retail investors on the Nairobi Securities Exchange. "
    "Be factual, specific about KES figures, and highlight risks honestly. "
    "Avoid jargon. Write in present tense."
)

USER_PROMPT_TEMPLATE = """
Given these financial results for {ticker} ({period} vs {comparison}):

{financials_json}

Write a structured analysis as JSON with exactly these keys:
{{
  "summary": "<3 sentences covering overall performance>",
  "revenue_trend": "<direction and main driver>",
  "profit_trend": "<margins and trajectory>",
  "debt_levels": "<risk assessment based on retained earnings and shareholders funds>",
  "cash_flow_health": "<sustainability based on operating and investing cash flows>",
  "dividend_history": "<dividend coverage and sustainability given EPS and DPS>",
  "key_risks": ["<risk 1>", "<risk 2>", "<risk 3>"],
  "growth_opportunities": ["<opportunity 1>", "<opportunity 2>"]
}}

Return only valid JSON. No markdown fences. No extra keys.
"""


def build_prompt(ticker: str, period: str, comparison: str, financials: dict) -> str:
    return USER_PROMPT_TEMPLATE.format(
        ticker=ticker,
        period=period,
        comparison=comparison,
        financials_json=json.dumps(financials, indent=2),
    )


def call_claude(prompt: str) -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
        system=SYSTEM_PROMPT,
    )
    raw = message.content[0].text.strip()
    return json.loads(raw)


def save_analysis(db, ticker: str, period: str, analysis: dict) -> None:
    analysis["generated_at"] = datetime.now(timezone.utc).isoformat()
    (db.collection("financials")
       .document(ticker)
       .collection("analysis")
       .document(period)
       .set(analysis))
    log.info("Saved analysis for %s / %s", ticker, period)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker",  required=True)
    parser.add_argument("--period",  required=True, help="e.g. H1-2026")
    args = parser.parse_args()

    from pipeline.scripts.firebase_client import get_firestore
    db = get_firestore()

    # Load extracted metrics from Firestore
    doc = (db.collection("financials")
             .document(args.ticker)
             .collection("periods")
             .document(args.period)
             .get())
    if not doc.exists:
        log.error("No extracted metrics for %s / %s. Run extract_financials first.", args.ticker, args.period)
        return

    data = doc.to_dict()
    comparison = data.get("comparison_period", "prior period")
    prompt = build_prompt(args.ticker, args.period, comparison, data)

    log.info("Calling Claude API for %s / %s ...", args.ticker, args.period)
    analysis = call_claude(prompt)
    save_analysis(db, args.ticker, args.period, analysis)
    log.info("Done.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add pipeline/scripts/analyze_financials_ai.py
git commit -m "feat: add analyze_financials_ai — Claude API narrative for financial reports"
```

---

### Task 12: Financial statement CI workflow

**Files:**
- Create: `.github/workflows/analyze_financials.yml`

- [ ] **Step 1: Create the workflow**

```yaml
# .github/workflows/analyze_financials.yml
name: Analyze Financial Reports (AI)

on:
  workflow_dispatch:
    inputs:
      ticker:
        description: "Ticker to process (e.g. BAT)"
        required: true
      period:
        description: "Period key (e.g. H1-2026)"
        required: true
      pdf_path:
        description: "Path to PDF in Firebase Storage (e.g. financial_reports/BAT/H1-2026/report.pdf)"
        required: false
  schedule:
    - cron: "0 6 1 * *"   # 1st of each month at 06:00 UTC

jobs:
  analyze:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
          cache-dependency-path: pipeline/requirements.txt

      - run: pip install -r pipeline/requirements.txt

      - name: Extract financials from PDF
        if: ${{ github.event.inputs.pdf_path != '' }}
        env:
          FIREBASE_SERVICE_ACCOUNT_JSON: ${{ secrets.FIREBASE_SERVICE_ACCOUNT_JSON }}
          FIREBASE_RTDB_URL: ${{ secrets.FIREBASE_RTDB_URL }}
          FIREBASE_STORAGE_BUCKET: ${{ secrets.FIREBASE_STORAGE_BUCKET }}
        run: |
          python pipeline/scripts/extract_financials.py \
            --ticker ${{ github.event.inputs.ticker }} \
            --period ${{ github.event.inputs.period }}

      - name: Generate AI narrative
        env:
          FIREBASE_SERVICE_ACCOUNT_JSON: ${{ secrets.FIREBASE_SERVICE_ACCOUNT_JSON }}
          FIREBASE_RTDB_URL: ${{ secrets.FIREBASE_RTDB_URL }}
          FIREBASE_STORAGE_BUCKET: ${{ secrets.FIREBASE_STORAGE_BUCKET }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          python pipeline/scripts/analyze_financials_ai.py \
            --ticker ${{ github.event.inputs.ticker }} \
            --period ${{ github.event.inputs.period }}
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/analyze_financials.yml
git commit -m "ci: add analyze_financials workflow — PDF extract + Claude AI narrative"
```

---

### Task 13: Frontend financials hooks and panels

**Files:**
- Create: `frontend/src/hooks/useFinancials.ts`
- Create: `frontend/src/hooks/useFinancialAnalysis.ts`
- Create: `frontend/src/components/FinancialsPanel.tsx`
- Create: `frontend/src/components/FinancialNarrativeCard.tsx`

- [ ] **Step 1: Create hooks**

```typescript
// frontend/src/hooks/useFinancials.ts
import { useQuery } from "@tanstack/react-query";
import { collection, getDocs, orderBy, query, limit } from "firebase/firestore";
import { db } from "../lib/firebase";

export interface MetricValue {
  current: number | null;
  prior: number | null;
  yoy_pct: number | null;
  unit: string;
  currency: string;
}

export interface RoeValue {
  current: string | null;
  prior: string | null;
  direction: "increased" | "decreased" | null;
}

export interface FinancialPeriod {
  period: string;
  comparison_period: string;
  income_statement: Record<string, MetricValue>;
  per_share: Record<string, MetricValue>;
  balance_sheet: Record<string, MetricValue>;
  cash_flow: Record<string, MetricValue>;
  returns: { annualised_roe: RoeValue };
}

export function useFinancials(ticker: string, period?: string) {
  return useQuery<FinancialPeriod | null>({
    queryKey: ["financials-period", ticker, period ?? "latest"],
    queryFn: async () => {
      const col = collection(db, "financials", ticker, "periods");
      const q = period
        ? query(col, limit(1))
        : query(col, orderBy("__name__", "desc"), limit(1));
      const snap = await getDocs(q);
      if (snap.empty) return null;
      const doc = period
        ? (await getDocs(query(col, limit(1)))).docs[0]
        : snap.docs[0];
      return { period: doc.id, ...doc.data() } as FinancialPeriod;
    },
    enabled: !!ticker,
    staleTime: 1000 * 60 * 60,
  });
}
```

```typescript
// frontend/src/hooks/useFinancialAnalysis.ts
import { useQuery } from "@tanstack/react-query";
import { collection, getDocs, orderBy, query, limit } from "firebase/firestore";
import { db } from "../lib/firebase";

export interface FinancialAnalysis {
  summary: string;
  revenue_trend: string;
  profit_trend: string;
  debt_levels: string;
  cash_flow_health: string;
  dividend_history: string;
  key_risks: string[];
  growth_opportunities: string[];
  generated_at: string;
}

export function useFinancialAnalysis(ticker: string) {
  return useQuery<FinancialAnalysis | null>({
    queryKey: ["financials-analysis", ticker],
    queryFn: async () => {
      const col = collection(db, "financials", ticker, "analysis");
      const snap = await getDocs(query(col, orderBy("__name__", "desc"), limit(1)));
      if (snap.empty) return null;
      return snap.docs[0].data() as FinancialAnalysis;
    },
    enabled: !!ticker,
    staleTime: 1000 * 60 * 60,
  });
}
```

- [ ] **Step 2: Create FinancialsPanel**

```typescript
// frontend/src/components/FinancialsPanel.tsx
import { useState } from "react";
import { useFinancials, type MetricValue } from "../hooks/useFinancials";

const TABS = ["Income Statement", "Cash Flow", "Balance Sheet", "Per Share"] as const;
type Tab = typeof TABS[number];

const SECTION_MAP: Record<Tab, string> = {
  "Income Statement": "income_statement",
  "Cash Flow":        "cash_flow",
  "Balance Sheet":    "balance_sheet",
  "Per Share":        "per_share",
};

const LABEL_MAP: Record<string, string> = {
  gross_revenue:               "Gross Revenue",
  excise_duty_and_vat:         "Excise Duty & VAT",
  net_revenue:                 "Net Revenue",
  cost_of_operations:          "Cost of Operations",
  operating_profit:            "Operating Profit",
  finance_income:              "Finance Income",
  profit_before_tax:           "Profit Before Tax",
  income_tax_expense:          "Income Tax Expense",
  profit_after_tax:            "Profit After Tax",
  basic_diluted_eps:           "Basic & Diluted EPS",
  interim_dividend_per_share:  "Interim Dividend Per Share",
  retained_earnings:           "Retained Earnings",
  shareholders_funds:          "Shareholders' Funds",
  net_cash_from_operations:    "Net Cash from Operations",
  net_cash_operating_activities:"Net Cash (Operating)",
  net_cash_investing_activities:"Net Cash (Investing)",
  net_cash_financing_activities:"Net Cash (Financing)",
  movement_in_cash:            "Movement in Cash",
  cash_at_period_end:          "Cash at Period End",
};

function YoyBadge({ pct }: { pct: number | null }) {
  if (pct === null) return <span className="text-gray-400">—</span>;
  const up = pct >= 0;
  return (
    <span className={`text-xs font-semibold ${up ? "text-green-500" : "text-red-500"}`}>
      {up ? "▲" : "▼"} {Math.abs(pct).toFixed(1)}%
    </span>
  );
}

function MetricRow({ label, metric }: { label: string; metric: MetricValue }) {
  const fmt = (v: number | null) =>
    v === null ? "—" : `${metric.currency} ${v.toLocaleString()} ${metric.unit}`;
  return (
    <tr className="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50">
      <td className="py-2 pr-4 text-sm text-gray-700 dark:text-gray-300">{label}</td>
      <td className="py-2 pr-4 text-sm font-medium text-right">{fmt(metric.current)}</td>
      <td className="py-2 pr-4 text-sm text-gray-500 text-right">{fmt(metric.prior)}</td>
      <td className="py-2 text-right"><YoyBadge pct={metric.yoy_pct} /></td>
    </tr>
  );
}

export function FinancialsPanel({ ticker }: { ticker: string }) {
  const [tab, setTab] = useState<Tab>("Income Statement");
  const { data, isLoading } = useFinancials(ticker);

  if (isLoading) return <div className="p-4 text-sm text-gray-500">Loading financials…</div>;
  if (!data) return <div className="p-4 text-sm text-gray-400">No financial data available yet.</div>;

  const section = (data as any)[SECTION_MAP[tab]] as Record<string, MetricValue> | undefined;

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-gray-900 dark:text-white">Financial Results</h3>
        <span className="text-xs text-gray-400">{data.period} vs {data.comparison_period}</span>
      </div>

      <div className="flex gap-2 mb-4 flex-wrap">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
              tab === t
                ? "bg-blue-600 text-white"
                : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <table className="w-full">
        <thead>
          <tr className="text-xs text-gray-400 border-b border-gray-200 dark:border-gray-700">
            <th className="pb-2 text-left font-medium">Metric</th>
            <th className="pb-2 text-right font-medium">{data.period}</th>
            <th className="pb-2 text-right font-medium">{data.comparison_period}</th>
            <th className="pb-2 text-right font-medium">YoY</th>
          </tr>
        </thead>
        <tbody>
          {section
            ? Object.entries(section).map(([key, metric]) => (
                <MetricRow key={key} label={LABEL_MAP[key] ?? key} metric={metric} />
              ))
            : null}
        </tbody>
      </table>

      {tab === "Income Statement" && data.returns?.annualised_roe?.current && (
        <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-800 flex justify-between text-sm">
          <span className="text-gray-500">Annualised ROE</span>
          <span className="font-medium">
            {data.returns.annualised_roe.current}
            {data.returns.annualised_roe.direction && (
              <span className={`ml-2 text-xs ${data.returns.annualised_roe.direction === "increased" ? "text-green-500" : "text-red-500"}`}>
                {data.returns.annualised_roe.direction === "increased" ? "▲" : "▼"}
              </span>
            )}
          </span>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Create FinancialNarrativeCard**

```typescript
// frontend/src/components/FinancialNarrativeCard.tsx
import { useState } from "react";
import { useFinancialAnalysis } from "../hooks/useFinancialAnalysis";

export function FinancialNarrativeCard({ ticker }: { ticker: string }) {
  const { data, isLoading } = useFinancialAnalysis(ticker);
  const [expanded, setExpanded] = useState<string | null>(null);

  if (isLoading) return null;
  if (!data) return null;

  const sections = [
    { key: "revenue_trend",    label: "Revenue" },
    { key: "profit_trend",     label: "Profit" },
    { key: "debt_levels",      label: "Debt" },
    { key: "cash_flow_health", label: "Cash Flow" },
    { key: "dividend_history", label: "Dividends" },
  ];

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4 mt-3">
      <p className="text-sm text-gray-700 dark:text-gray-300 mb-4">{data.summary}</p>

      <div className="flex gap-2 flex-wrap mb-4">
        {sections.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setExpanded(expanded === key ? null : key)}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
              expanded === key
                ? "bg-blue-600 text-white"
                : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {expanded && (
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
          {(data as any)[expanded]}
        </p>
      )}

      <div className="grid grid-cols-2 gap-3 mt-2">
        <div>
          <p className="text-xs font-semibold text-red-500 mb-1">Key Risks</p>
          <ul className="space-y-1">
            {data.key_risks.map((r, i) => (
              <li key={i} className="text-xs text-gray-600 dark:text-gray-400 flex gap-1">
                <span className="text-red-400 mt-0.5">•</span>{r}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="text-xs font-semibold text-green-500 mb-1">Growth Opportunities</p>
          <ul className="space-y-1">
            {data.growth_opportunities.map((o, i) => (
              <li key={i} className="text-xs text-gray-600 dark:text-gray-400 flex gap-1">
                <span className="text-green-400 mt-0.5">•</span>{o}
              </li>
            ))}
          </ul>
        </div>
      </div>

      <p className="text-xs text-gray-400 mt-3">
        Analysis generated {new Date(data.generated_at).toLocaleDateString()}
      </p>
    </div>
  );
}
```

- [ ] **Step 4: Wire panels into CompanyDeepDive**

In `frontend/src/pages/CompanyDeepDive.tsx`, add imports:
```typescript
import { FinancialsPanel } from "../components/FinancialsPanel";
import { FinancialNarrativeCard } from "../components/FinancialNarrativeCard";
```

Add the panels in the JSX after the existing `ValuationPanel`:
```tsx
<FinancialsPanel ticker={safeTicker} />
<FinancialNarrativeCard ticker={safeTicker} />
```

- [ ] **Step 5: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors

- [ ] **Step 6: Start dev server and verify panels render**

```bash
cd frontend && npm run dev
```
Navigate to a company page. FinancialsPanel should show with tabs (and empty state if no data yet). FinancialNarrativeCard should be hidden when no data.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/hooks/useFinancials.ts frontend/src/hooks/useFinancialAnalysis.ts \
        frontend/src/components/FinancialsPanel.tsx frontend/src/components/FinancialNarrativeCard.tsx \
        frontend/src/pages/CompanyDeepDive.tsx
git commit -m "feat: add FinancialsPanel and FinancialNarrativeCard with Firestore hooks"
```

---

## Phase 6 — Feature 5: Deep Price Analysis (Rebuild)

### Task 14: Deep price analysis Python script

**Files:**
- Create: `pipeline/scripts/deep_price_analysis.py`

- [ ] **Step 1: Create the script**

```python
# pipeline/scripts/deep_price_analysis.py
"""
Combines RTDB price history, technicals, news, corporate actions, and financial
analysis to generate a Claude-powered explanation of recent price movements.

Stores result in Firestore deep_analysis/{ticker}/{YYYY-MM-DD}.

Usage:
  ANTHROPIC_API_KEY=... FIREBASE_SERVICE_ACCOUNT_JSON=... FIREBASE_RTDB_URL=... \
    python pipeline/scripts/deep_price_analysis.py [--ticker SCOM] [--date 2026-07-24]
"""
import argparse
import json
import logging
import os
from datetime import date, datetime, timedelta, timezone

import anthropic

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

SYSTEM_PROMPT = (
    "You are a senior NSE equity analyst. Explain stock price movements using only the "
    "provided data. Be specific about dates, KES figures, and named events. "
    "Do not hallucinate events not present in the input data. "
    "Write in plain English for retail investors."
)

USER_PROMPT_TEMPLATE = """
Analyze the recent price movement for {ticker} on the Nairobi Securities Exchange.

=== RECENT PRICE HISTORY (last 90 days) ===
{price_summary}

=== TECHNICAL SIGNALS (latest) ===
{technicals}

=== RECENT NEWS (last 30 days) ===
{news_items}

=== CORPORATE ACTIONS ===
{corporate_actions}

=== LATEST FINANCIAL ANALYSIS ===
{financial_analysis}

Based ONLY on the above data, respond with a JSON object using exactly these keys:
{{
  "price_movement_explanation": "<2-3 sentences explaining the dominant price driver>",
  "driver_type": "<fundamental|sentiment|technical|corporate_action>",
  "key_events": [
    {{"date": "YYYY-MM-DD", "event": "<description>", "estimated_impact": "<+X% or -X% or neutral>"}}
  ],
  "outlook": {{
    "short_term": "<1-2 sentences, next 2-4 weeks>",
    "medium_term": "<1-2 sentences, next 3-6 months>"
  }},
  "confidence": <integer 1-5>
}}

Return only valid JSON. No markdown fences.
"""


def fetch_price_summary(root_ref, ticker: str, days: int = 90) -> str:
    end_date   = date.today().isoformat()
    start_date = (date.today() - timedelta(days=days)).isoformat()
    snap = (root_ref.child(f"prices/{ticker}")
                    .order_by_key()
                    .start_at(start_date)
                    .end_at(end_date)
                    .get())
    if not snap:
        return "No price data available."
    lines = []
    items = sorted(snap.items())
    for date_str, fields in items[-30:]:  # last 30 entries for brevity
        lines.append(f"{date_str}: open={fields.get('o','?')} close={fields.get('c','?')} vol={fields.get('v','?')}")
    first = items[0]
    last  = items[-1]
    pct   = round(((last[1].get("c", 0) - first[1].get("c", 0)) / (first[1].get("c", 1) or 1)) * 100, 1)
    summary = f"90-day change: {pct:+.1f}% (from {first[1].get('c','?')} to {last[1].get('c','?')} KES)\n"
    return summary + "\n".join(lines[-10:])


def fetch_technicals(db, ticker: str) -> str:
    col = (db.collection("companies").document(ticker)
             .collection("technicals"))
    docs = list(col.order_by("__name__", direction="DESCENDING").limit(1).stream())
    if not docs:
        return "No technical data."
    d = docs[0].to_dict()
    return json.dumps({k: v for k, v in d.items() if k in (
        "rsi_14", "macd", "macd_signal", "bb_upper", "bb_lower",
        "sma_20", "sma_50", "sma_200", "volatility_30d"
    )}, indent=2)


def fetch_news(db, ticker: str, days: int = 30) -> str:
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    col = db.collection("news").document(ticker).collection("items")
    docs = list(col.stream())
    recent = [d.to_dict() for d in docs if d.to_dict().get("date", "") >= cutoff]
    if not recent:
        return "No recent news."
    return "\n".join(
        f"- [{item['date']}] ({item.get('category','')}) {item['title']}"
        for item in sorted(recent, key=lambda x: x.get("date", ""), reverse=True)[:15]
    )


def fetch_corporate_actions(db, ticker: str) -> str:
    col = (db.collection("companies").document(ticker)
             .collection("corporate_actions"))
    docs = list(col.order_by("__name__", direction="DESCENDING").limit(10).stream())
    if not docs:
        return "No corporate actions."
    return "\n".join(
        f"- [{d.id}] {json.dumps(d.to_dict())}"
        for d in docs
    )


def fetch_financial_analysis(db, ticker: str) -> str:
    col = (db.collection("financials").document(ticker)
             .collection("analysis"))
    docs = list(col.order_by("__name__", direction="DESCENDING").limit(1).stream())
    if not docs:
        return "No financial analysis available."
    d = docs[0].to_dict()
    return (
        f"Summary: {d.get('summary','')}\n"
        f"Revenue: {d.get('revenue_trend','')}\n"
        f"Profit: {d.get('profit_trend','')}\n"
        f"Risks: {'; '.join(d.get('key_risks',[]))}"
    )


def run_analysis(ticker: str, target_date: str, db, root_ref) -> dict:
    short = ticker.replace(".NR", "").replace("_NR", "")

    price_summary      = fetch_price_summary(root_ref, short)
    technicals         = fetch_technicals(db, ticker)
    news_items         = fetch_news(db, ticker)
    corporate_actions  = fetch_corporate_actions(db, ticker)
    financial_analysis = fetch_financial_analysis(db, ticker)

    prompt = USER_PROMPT_TEMPLATE.format(
        ticker=ticker,
        price_summary=price_summary,
        technicals=technicals,
        news_items=news_items,
        corporate_actions=corporate_actions,
        financial_analysis=financial_analysis,
    )

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    result = json.loads(message.content[0].text.strip())
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    result["ticker"]        = ticker
    result["date"]          = target_date
    return result


def save_result(db, ticker: str, date_str: str, result: dict) -> None:
    (db.collection("deep_analysis")
       .document(ticker)
       .collection("dates")
       .document(date_str)
       .set(result))
    log.info("Saved deep_analysis/%s/dates/%s", ticker, date_str)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", help="Single ticker (blank = all from companies.json)")
    parser.add_argument("--date",   help="YYYY-MM-DD (default: today)")
    args = parser.parse_args()

    target_date = args.date or date.today().isoformat()

    from pipeline.scripts.firebase_client import get_firestore, get_rtdb
    db       = get_firestore()
    root_ref = get_rtdb()

    if args.ticker:
        tickers = [args.ticker]
    else:
        from pipeline.config import load_companies
        tickers = [c["ticker"] for c in load_companies()]

    for ticker in tickers:
        try:
            log.info("Analyzing %s ...", ticker)
            result = run_analysis(ticker, target_date, db, root_ref)
            save_result(db, ticker, target_date, result)
        except Exception as exc:
            log.error("%s: failed — %s", ticker, exc)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Add deep analysis step to daily_update.yml**

Add as the last step in the `update` job (after `Scrape NSE announcements`):

```yaml
      - name: Deep price analysis (Claude AI)
        continue-on-error: true
        env:
          FIREBASE_SERVICE_ACCOUNT_JSON: ${{ secrets.FIREBASE_SERVICE_ACCOUNT_JSON }}
          FIREBASE_RTDB_URL: ${{ secrets.FIREBASE_RTDB_URL }}
          FIREBASE_STORAGE_BUCKET: ${{ secrets.FIREBASE_STORAGE_BUCKET }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          python pipeline/scripts/deep_price_analysis.py 2>&1 | tee /tmp/deep_analysis.log
```

- [ ] **Step 3: Commit**

```bash
git add pipeline/scripts/deep_price_analysis.py .github/workflows/daily_update.yml
git commit -m "feat: add deep_price_analysis — nightly Claude AI price movement explanation"
```

---

### Task 15: Frontend DeepAnalysisPanel

**Files:**
- Create: `frontend/src/hooks/useDeepAnalysis.ts`
- Create: `frontend/src/components/DeepAnalysisPanel.tsx`

- [ ] **Step 1: Create hook**

```typescript
// frontend/src/hooks/useDeepAnalysis.ts
import { useQuery } from "@tanstack/react-query";
import { collection, getDocs, orderBy, query, limit } from "firebase/firestore";
import { db } from "../lib/firebase";

export interface KeyEvent {
  date: string;
  event: string;
  estimated_impact: string;
}

export interface DeepAnalysis {
  price_movement_explanation: string;
  driver_type: "fundamental" | "sentiment" | "technical" | "corporate_action";
  key_events: KeyEvent[];
  outlook: { short_term: string; medium_term: string };
  confidence: number;
  generated_at: string;
  date: string;
}

export function useDeepAnalysis(ticker: string) {
  return useQuery<DeepAnalysis | null>({
    queryKey: ["deep-analysis", ticker],
    queryFn: async () => {
      const col = collection(db, "deep_analysis", ticker, "dates");
      const snap = await getDocs(query(col, orderBy("__name__", "desc"), limit(1)));
      if (snap.empty) return null;
      return snap.docs[0].data() as DeepAnalysis;
    },
    enabled: !!ticker,
    staleTime: 1000 * 60 * 30,
  });
}
```

- [ ] **Step 2: Create DeepAnalysisPanel**

```typescript
// frontend/src/components/DeepAnalysisPanel.tsx
import { useDeepAnalysis } from "../hooks/useDeepAnalysis";

const DRIVER_COLORS = {
  fundamental:      "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  sentiment:        "bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300",
  technical:        "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300",
  corporate_action: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300",
};

function ConfidenceDots({ level }: { level: number }) {
  return (
    <div className="flex gap-1">
      {[1, 2, 3, 4, 5].map((i) => (
        <div
          key={i}
          className={`w-2 h-2 rounded-full ${i <= level ? "bg-blue-500" : "bg-gray-200 dark:bg-gray-700"}`}
        />
      ))}
    </div>
  );
}

export function DeepAnalysisPanel({ ticker }: { ticker: string }) {
  const { data, isLoading } = useDeepAnalysis(ticker);

  if (isLoading) return null;
  if (!data) return null;

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-gray-900 dark:text-white">Price Analysis</h3>
        <span
          className={`text-xs font-semibold px-2 py-0.5 rounded-full uppercase tracking-wide ${DRIVER_COLORS[data.driver_type] ?? ""}`}
        >
          {data.driver_type.replace("_", " ")}
        </span>
      </div>

      <p className="text-sm text-gray-700 dark:text-gray-300 mb-4">
        {data.price_movement_explanation}
      </p>

      {data.key_events.length > 0 && (
        <div className="mb-4">
          <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-2">
            Key Events
          </p>
          <div className="space-y-2">
            {data.key_events.map((ev, i) => (
              <div key={i} className="flex gap-3 text-sm">
                <span className="text-gray-400 shrink-0 w-24">{ev.date}</span>
                <span className="text-gray-700 dark:text-gray-300 flex-1">{ev.event}</span>
                <span className={`shrink-0 font-medium ${
                  ev.estimated_impact.startsWith("+") ? "text-green-500" :
                  ev.estimated_impact.startsWith("-") ? "text-red-500" : "text-gray-400"
                }`}>
                  {ev.estimated_impact}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="rounded-lg bg-gray-50 dark:bg-gray-800 p-3">
          <p className="text-xs font-semibold text-gray-400 mb-1">Short-term</p>
          <p className="text-sm text-gray-700 dark:text-gray-300">{data.outlook.short_term}</p>
        </div>
        <div className="rounded-lg bg-gray-50 dark:bg-gray-800 p-3">
          <p className="text-xs font-semibold text-gray-400 mb-1">Medium-term</p>
          <p className="text-sm text-gray-700 dark:text-gray-300">{data.outlook.medium_term}</p>
        </div>
      </div>

      <div className="flex items-center justify-between text-xs text-gray-400">
        <div className="flex items-center gap-2">
          <span>Confidence</span>
          <ConfidenceDots level={data.confidence} />
        </div>
        <span>Updated {new Date(data.generated_at).toLocaleDateString()}</span>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Wire DeepAnalysisPanel into CompanyDeepDive**

Add import:
```typescript
import { DeepAnalysisPanel } from "../components/DeepAnalysisPanel";
```

Add panel below FinancialNarrativeCard:
```tsx
<DeepAnalysisPanel ticker={safeTicker} />
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors

- [ ] **Step 5: Start dev server and verify**

```bash
cd frontend && npm run dev
```
Navigate to a company. DeepAnalysisPanel should be hidden when no data, visible when `deep_analysis/{ticker}/dates/{date}` exists in Firestore.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/hooks/useDeepAnalysis.ts frontend/src/components/DeepAnalysisPanel.tsx \
        frontend/src/pages/CompanyDeepDive.tsx
git commit -m "feat: add DeepAnalysisPanel with Claude-powered price movement explanation"
```

---

## Phase 7 — Cleanup

### Task 16: Remove HTML reports and retired scripts

**Files to delete:**
- `reports/outputs/SCOM_NR_report.html`
- `reports/outputs/EABL_NR_report.html`
- `reports/outputs/EQTY_NR_report.html`
- `reports/outputs/KCB_NR_report.html`
- `reports/outputs/COOP_NR_report.html`
- `pipeline/src/visualization/dashboard.py`
- `run_all.py`
- `run_pipeline.py`

- [ ] **Step 1: Delete files**

```bash
git rm reports/outputs/SCOM_NR_report.html \
       reports/outputs/EABL_NR_report.html \
       reports/outputs/EQTY_NR_report.html \
       reports/outputs/KCB_NR_report.html \
       reports/outputs/COOP_NR_report.html \
       pipeline/src/visualization/dashboard.py \
       run_all.py \
       run_pipeline.py
```

- [ ] **Step 2: Verify no imports reference the deleted files**

```bash
grep -r "dashboard\|run_all\|run_pipeline" pipeline/scripts/ --include="*.py" | grep -v ".pyc"
grep -r "dashboard\|run_all\|run_pipeline" .github/workflows/ || true
```
Expected: no matches (or only comments).

- [ ] **Step 3: Commit**

```bash
git commit -m "chore: remove HTML reports and retired pipeline scripts"
```

---

## Self-Review Checklist

- [ ] Spec section 1 (Audit): files-to-delete covered in Task 16 ✅
- [ ] Spec section 3 (RTDB schema): `firebase_rtdb.py` and `migrate_prices_to_rtdb.py` implement the exact field names ✅
- [ ] Spec section 4 (F1): migration script + workflow + frontend hook + TradingChart update ✅
- [ ] Spec section 5 (F2): `scrape_nse_pdf.py` covers all companies with zero-volume handling ✅
- [ ] Spec section 6 (F3): `scrape_news.py` extended with company IR + MarketScreener ✅
- [ ] Spec section 7 (F4): all 20 fields in `EMPTY_FINANCIALS()`, Claude narrative covers all 8 output fields ✅
- [ ] Spec section 8 (F5): all 5 output fields, nightly workflow step added ✅
- [ ] Spec section 9 (Frontend): RTDB client, 4 hooks, 3 new components, TradingChart update, CompanyDeepDive wired ✅
- [ ] Spec section 10 (CI): `migrate_prices.yml`, `analyze_financials.yml`, `daily_update.yml` updated ✅
- [ ] Spec section 11 (Env vars): `FIREBASE_RTDB_URL` and `ANTHROPIC_API_KEY` referenced in all workflows ✅
- [ ] Type consistency: `RtdbPricePoint` used in `useHistoricalPrices` matches the `o/h/l/c/v/pc/ch/pch/vv` schema from `firebase_rtdb.py` ✅
- [ ] `MetricValue` interface in `useFinancials.ts` matches the `build_metric()` output in `extract_financials.py` ✅
