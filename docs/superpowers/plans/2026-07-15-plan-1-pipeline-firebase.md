# NSE Web Platform — Plan 1: Pipeline Restructure & Firebase Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the Python ML pipeline into a GitHub Actions-ready batch job that writes daily inference results and technicals to Firebase Firestore for all 70 NSE companies.

**Architecture:** Existing `src/` ML modules move into `pipeline/src/` unchanged. Three new entry-point scripts orchestrate them: `run_inference.py` (daily cron), `run_training.py` (weekly cron), `push_to_firestore.py` (shared Firestore writer). GitHub Actions runs both crons. Firebase Storage holds model `.pt`/`.pkl` files; Firestore holds all computed results.

**Tech Stack:** Python 3.11, firebase-admin 6.x, PyTorch 2.x, XGBoost 2.x, statsmodels, pandas, ta, pytest, unittest.mock, GitHub Actions

---

## File Map

```
nse_predictor/
├── pipeline/                        ← NEW top-level pipeline package
│   ├── src/                         ← MOVED from src/ (no code changes)
│   │   ├── analysis/
│   │   ├── data/
│   │   ├── features/
│   │   ├── models/
│   │   └── visualization/
│   ├── config/
│   │   └── companies.json           ← NEW — all 70 NSE companies metadata
│   ├── scripts/
│   │   ├── push_to_firestore.py     ← NEW — Firestore + Storage writer
│   │   ├── run_inference.py         ← NEW — daily job entry point
│   │   └── run_training.py          ← NEW — weekly job entry point
│   ├── data/
│   │   └── raw/                     ← MOVED from data/raw/ (NSE CSVs)
│   ├── config.py                    ← MOVED + updated paths
│   └── requirements.txt             ← NEW — pipeline-specific deps
├── tests/
│   └── pipeline/
│       ├── test_push_to_firestore.py ← NEW
│       └── test_run_inference.py     ← NEW
├── firestore.rules                  ← NEW
├── .github/
│   └── workflows/
│       ├── daily_inference.yml      ← NEW
│       ├── weekly_training.yml      ← NEW
│       └── deploy.yml               ← NEW (placeholder for Plan 2)
└── .gitignore                       ← MODIFIED — add pipeline/data/cleaned/
```

---

## Task 1: Move `src/` to `pipeline/src/` and update root config

**Files:**
- Move: `src/` → `pipeline/src/`
- Move: `data/raw/` → `pipeline/data/raw/`
- Move: `data/cleaned/` → `pipeline/data/cleaned/`
- Move: `data/features/` → `pipeline/data/features/`
- Create: `pipeline/__init__.py`
- Create: `pipeline/src/__init__.py` (already exists as `src/__init__.py`)
- Modify: `config.py` → becomes `pipeline/config.py`

- [ ] **Step 1: Create pipeline directory structure**

```powershell
New-Item -ItemType Directory -Force -Path "C:\Users\moeng\nse_predictor\pipeline\scripts"
New-Item -ItemType Directory -Force -Path "C:\Users\moeng\nse_predictor\pipeline\config"
New-Item -ItemType Directory -Force -Path "C:\Users\moeng\nse_predictor\pipeline\data\raw"
New-Item -ItemType Directory -Force -Path "C:\Users\moeng\nse_predictor\pipeline\data\cleaned"
New-Item -ItemType Directory -Force -Path "C:\Users\moeng\nse_predictor\pipeline\data\features"
New-Item -ItemType Directory -Force -Path "C:\Users\moeng\nse_predictor\tests\pipeline"
```

- [ ] **Step 2: Move `src/` into `pipeline/src/`**

```powershell
Move-Item "C:\Users\moeng\nse_predictor\src" "C:\Users\moeng\nse_predictor\pipeline\src"
```

- [ ] **Step 3: Move data directories**

```powershell
# Copy existing CSVs into new location (keep originals until verified)
Copy-Item "C:\Users\moeng\nse_predictor\data\raw\*" "C:\Users\moeng\nse_predictor\pipeline\data\raw\"
Copy-Item "C:\Users\moeng\nse_predictor\data\cleaned\*" "C:\Users\moeng\nse_predictor\pipeline\data\cleaned\"
Copy-Item "C:\Users\moeng\nse_predictor\data\features\*" "C:\Users\moeng\nse_predictor\pipeline\data\features\" -ErrorAction SilentlyContinue
```

- [ ] **Step 4: Create `pipeline/__init__.py`**

```python
# pipeline/__init__.py
```

- [ ] **Step 5: Write `pipeline/config.py`**

```python
# pipeline/config.py
from pathlib import Path

BASE_DIR      = Path(__file__).parent
DATA_RAW      = BASE_DIR / "data" / "raw"
DATA_CLEANED  = BASE_DIR / "data" / "cleaned"
DATA_FEATURES = BASE_DIR / "data" / "features"
MODELS_DIR    = BASE_DIR / "models" / "saved"
REPORTS_DIR   = BASE_DIR / "reports" / "outputs"

NSE_TICKERS = []  # loaded dynamically from companies.json — see load_companies()

START_DATE = "2015-01-01"

SEQUENCE_LENGTH   = 60
TOP_FEATURES      = 25
TRAIN_SPLIT       = 0.80

DEFAULT_INVESTMENT  = 100_000
DEFAULT_CONFIDENCE  = 0.95
MONTE_CARLO_SIMS    = 10_000
MONTE_CARLO_HORIZON = 30

NSE_DAILY_BAND_PCT  = 9.9
MIN_TRADING_DAYS    = 500
MIN_VOLUME_PCT      = 0.60
MAX_STALE_RUN       = 10
CLOSE_COMPLETENESS  = 0.95

ENSEMBLE_WEIGHTS = (0.25, 0.60, 0.15)  # LSTM, XGBoost, ARIMA


def load_companies() -> list[dict]:
    """Return list of company dicts from companies.json."""
    import json
    path = BASE_DIR / "config" / "companies.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_tickers() -> list[str]:
    return [c["ticker"] for c in load_companies()]
```

- [ ] **Step 6: Update `.gitignore` to cover new paths**

Add these lines to `.gitignore`:
```
# Pipeline data (keep raw CSVs, ignore cleaned/features output)
pipeline/data/cleaned/
pipeline/data/features/
pipeline/models/saved/
```

- [ ] **Step 7: Verify imports still resolve from pipeline root**

```powershell
cd "C:\Users\moeng\nse_predictor"
python -c "import sys; sys.path.insert(0,'pipeline'); from src.data.fetcher import fetch_nse_data; print('OK')"
```

Expected output: `OK`

- [ ] **Step 8: Commit**

```powershell
cd "C:\Users\moeng\nse_predictor"
git add pipeline/ tests/ .gitignore
git rm -r --cached src/ data/   # remove old locations from git index
git commit -m "refactor: move src/ and data/ into pipeline/ directory"
```

---

## Task 2: Create `companies.json` for all 70 NSE companies

**Files:**
- Create: `pipeline/config/companies.json`

- [ ] **Step 1: Create `companies.json` with known companies**

Create `pipeline/config/companies.json`:

```json
[
  {"ticker":"SCOM.NR","name":"Safaricom PLC","short":"SCOM","sector":"Telecom","color":"#38bdf8","icon":"📱","csv":"SCOM_NR_raw.csv"},
  {"ticker":"EQTY.NR","name":"Equity Group Holdings","short":"EQTY","sector":"Banking","color":"#a78bfa","icon":"🏦","csv":"EQTY_NR_raw.csv"},
  {"ticker":"KCB.NR","name":"KCB Group PLC","short":"KCB","sector":"Banking","color":"#f472b6","icon":"🏦","csv":"KCB_NR_raw.csv"},
  {"ticker":"EABL.NR","name":"East African Breweries","short":"EABL","sector":"Beverages","color":"#fb923c","icon":"🍺","csv":"EABL_NR_raw.csv"},
  {"ticker":"COOP.NR","name":"Co-operative Bank Kenya","short":"COOP","sector":"Banking","color":"#34d399","icon":"🏦","csv":"COOP_NR_raw.csv"},
  {"ticker":"ABSA.NR","name":"ABSA Bank Kenya","short":"ABSA","sector":"Banking","color":"#60a5fa","icon":"🏦","csv":"ABSA_NR_raw.csv"},
  {"ticker":"SCBK.NR","name":"Standard Chartered Bank Kenya","short":"SCBK","sector":"Banking","color":"#818cf8","icon":"🏦","csv":"SCBK_NR_raw.csv"},
  {"ticker":"DTK.NR","name":"Diamond Trust Bank Kenya","short":"DTK","sector":"Banking","color":"#c084fc","icon":"🏦","csv":"DTK_NR_raw.csv"},
  {"ticker":"I&M.NR","name":"I&M Holdings","short":"I&M","sector":"Banking","color":"#e879f9","icon":"🏦","csv":"IM_NR_raw.csv"},
  {"ticker":"NCBA.NR","name":"NCBA Group","short":"NCBA","sector":"Banking","color":"#f9a8d4","icon":"🏦","csv":"NCBA_NR_raw.csv"},
  {"ticker":"HF.NR","name":"HF Group","short":"HF","sector":"Banking","color":"#93c5fd","icon":"🏦","csv":"HF_NR_raw.csv"},
  {"ticker":"NBK.NR","name":"National Bank of Kenya","short":"NBK","sector":"Banking","color":"#6ee7b7","icon":"🏦","csv":"NBK_NR_raw.csv"},
  {"ticker":"SBIC.NR","name":"Stanbic Holdings Kenya","short":"SBIC","sector":"Banking","color":"#fca5a5","icon":"🏦","csv":"SBIC_NR_raw.csv"},
  {"ticker":"JUBILEE.NR","name":"Jubilee Holdings","short":"JUB","sector":"Insurance","color":"#4ade80","icon":"🛡️","csv":"JUBILEE_NR_raw.csv"},
  {"ticker":"BRITAM.NR","name":"Britam Holdings","short":"BRIT","sector":"Insurance","color":"#86efac","icon":"🛡️","csv":"BRITAM_NR_raw.csv"},
  {"ticker":"CIC.NR","name":"CIC Insurance Group","short":"CIC","sector":"Insurance","color":"#bbf7d0","icon":"🛡️","csv":"CIC_NR_raw.csv"},
  {"ticker":"LIBERTY.NR","name":"Liberty Kenya Holdings","short":"LIB","sector":"Insurance","color":"#a3e635","icon":"🛡️","csv":"LIBERTY_NR_raw.csv"},
  {"ticker":"KENRE.NR","name":"Kenya Reinsurance Corp","short":"KENRE","sector":"Insurance","color":"#d9f99d","icon":"🛡️","csv":"KENRE_NR_raw.csv"},
  {"ticker":"PAK.NR","name":"Pan Africa Insurance","short":"PAK","sector":"Insurance","color":"#bef264","icon":"🛡️","csv":"PAK_NR_raw.csv"},
  {"ticker":"BAT.NR","name":"British American Tobacco Kenya","short":"BAT","sector":"Manufacturing","color":"#fde047","icon":"🏭","csv":"BAT_NR_raw.csv"},
  {"ticker":"BAMB.NR","name":"Bamburi Cement","short":"BAMB","sector":"Construction","color":"#fcd34d","icon":"🏗️","csv":"BAMB_NR_raw.csv"},
  {"ticker":"CROWN.NR","name":"Crown Paints Kenya","short":"CROWN","sector":"Construction","color":"#fbbf24","icon":"🏗️","csv":"CROWN_NR_raw.csv"},
  {"ticker":"EAPC.NR","name":"East African Portland Cement","short":"EAPC","sector":"Construction","color":"#f59e0b","icon":"🏗️","csv":"EAPC_NR_raw.csv"},
  {"ticker":"TCL.NR","name":"TransCentury","short":"TCL","sector":"Construction","color":"#d97706","icon":"🏗️","csv":"TCL_NR_raw.csv"},
  {"ticker":"KEGN.NR","name":"KenGen","short":"KEGN","sector":"Energy","color":"#fb923c","icon":"⚡","csv":"KEGN_NR_raw.csv"},
  {"ticker":"KPLC.NR","name":"Kenya Power & Lighting","short":"KPLC","sector":"Energy","color":"#f97316","icon":"⚡","csv":"KPLC_NR_raw.csv"},
  {"ticker":"TOTL.NR","name":"Total Energies Kenya","short":"TOTL","sector":"Energy","color":"#ea580c","icon":"⛽","csv":"TOTL_NR_raw.csv"},
  {"ticker":"KENOL.NR","name":"KenolKobil","short":"KENOL","sector":"Energy","color":"#dc2626","icon":"⛽","csv":"KENOL_NR_raw.csv"},
  {"ticker":"KA.NR","name":"Kenya Airways","short":"KA","sector":"Transport","color":"#ef4444","icon":"✈️","csv":"KA_NR_raw.csv"},
  {"ticker":"NCM.NR","name":"Nation Media Group","short":"NCM","sector":"Commercial","color":"#22d3ee","icon":"📰","csv":"NCM_NR_raw.csv"},
  {"ticker":"SCAN.NR","name":"Scangroup","short":"SCAN","sector":"Commercial","color":"#06b6d4","icon":"📢","csv":"SCAN_NR_raw.csv"},
  {"ticker":"NSE.NR","name":"Nairobi Securities Exchange","short":"NSE","sector":"Commercial","color":"#0891b2","icon":"📈","csv":"NSE_NR_raw.csv"},
  {"ticker":"LONGHORN.NR","name":"Longhorn Publishers","short":"LHP","sector":"Commercial","color":"#0e7490","icon":"📚","csv":"LONGHORN_NR_raw.csv"},
  {"ticker":"EXPRESS.NR","name":"Express Kenya","short":"XPRS","sector":"Commercial","color":"#155e75","icon":"🚚","csv":"EXPRESS_NR_raw.csv"},
  {"ticker":"TPS.NR","name":"TPS Eastern Africa (Serena)","short":"TPS","sector":"Tourism","color":"#fbbf24","icon":"🏨","csv":"TPS_NR_raw.csv"},
  {"ticker":"UNGA.NR","name":"Unga Group","short":"UNGA","sector":"Agricultural","color":"#84cc16","icon":"🌾","csv":"UNGA_NR_raw.csv"},
  {"ticker":"SASINI.NR","name":"Sasini PLC","short":"SASINI","sector":"Agricultural","color":"#65a30d","icon":"🍃","csv":"SASINI_NR_raw.csv"},
  {"ticker":"KAKUZI.NR","name":"Kakuzi PLC","short":"KAKUZI","sector":"Agricultural","color":"#4d7c0f","icon":"🥑","csv":"KAKUZI_NR_raw.csv"},
  {"ticker":"KAPCHORUA.NR","name":"Kapchorua Tea","short":"KAPC","sector":"Agricultural","color":"#3f6212","icon":"🍵","csv":"KAPCHORUA_NR_raw.csv"},
  {"ticker":"LIMURU.NR","name":"Limuru Tea","short":"LIMURU","sector":"Agricultural","color":"#22c55e","icon":"🍵","csv":"LIMURU_NR_raw.csv"},
  {"ticker":"WTK.NR","name":"Williamson Tea Kenya","short":"WTK","sector":"Agricultural","color":"#16a34a","icon":"🍵","csv":"WTK_NR_raw.csv"},
  {"ticker":"BOC.NR","name":"BOC Kenya","short":"BOC","sector":"Manufacturing","color":"#f87171","icon":"🏭","csv":"BOC_NR_raw.csv"},
  {"ticker":"CABL.NR","name":"East African Cables","short":"CABL","sector":"Manufacturing","color":"#fb923c","icon":"🏭","csv":"CABL_NR_raw.csv"},
  {"ticker":"CARBACID.NR","name":"Carbacid Investments","short":"CARB","sector":"Manufacturing","color":"#fbbf24","icon":"🏭","csv":"CARBACID_NR_raw.csv"},
  {"ticker":"EVRD.NR","name":"Eveready East Africa","short":"EVRD","sector":"Manufacturing","color":"#facc15","icon":"🔋","csv":"EVRD_NR_raw.csv"},
  {"ticker":"PZCU.NR","name":"PZ Cussons Kenya","short":"PZCU","sector":"Manufacturing","color":"#a3e635","icon":"🏭","csv":"PZCU_NR_raw.csv"},
  {"ticker":"UNILEVER.NR","name":"Unilever Kenya","short":"UNVR","sector":"Manufacturing","color":"#4ade80","icon":"🏭","csv":"UNILEVER_NR_raw.csv"},
  {"ticker":"MUMIAS.NR","name":"Mumias Sugar","short":"MSC","sector":"Agricultural","color":"#86efac","icon":"🌾","csv":"MUMIAS_NR_raw.csv"},
  {"ticker":"CENTUM.NR","name":"Centum Investment Company","short":"CENTUM","sector":"Investment","color":"#818cf8","icon":"💼","csv":"CENTUM_NR_raw.csv"},
  {"ticker":"ICDC.NR","name":"ICDC Investment Company","short":"ICDC","sector":"Investment","color":"#a5b4fc","icon":"💼","csv":"ICDC_NR_raw.csv"},
  {"ticker":"OLYMPIA.NR","name":"Olympia Capital Holdings","short":"OLY","sector":"Investment","color":"#c7d2fe","icon":"💼","csv":"OLYMPIA_NR_raw.csv"},
  {"ticker":"FAHR.NR","name":"Fahari I-REIT","short":"FAHR","sector":"REIT","color":"#fde68a","icon":"🏢","csv":"FAHR_NR_raw.csv"},
  {"ticker":"ILAM.NR","name":"ILAM Fahari I-REIT","short":"ILAM","sector":"REIT","color":"#fef08a","icon":"🏢","csv":"ILAM_NR_raw.csv"},
  {"ticker":"RDMP.NR","name":"Rea Vipingo Plantations","short":"RDMP","sector":"Agricultural","color":"#bbf7d0","icon":"🌱","csv":"RDMP_NR_raw.csv"},
  {"ticker":"CGEN.NR","name":"Car & General Kenya","short":"CGEN","sector":"Automobiles","color":"#94a3b8","icon":"🚗","csv":"CGEN_NR_raw.csv"}
]
```

> **Note:** Verify the complete 70-company list at https://www.nse.co.ke/listed-companies/. Add any missing tickers following the same schema. For each company added, source its historical CSV from NSE and place it in `pipeline/data/raw/<CSV_NAME>`.

- [ ] **Step 2: Verify JSON is valid**

```powershell
python -c "import json; data=json.load(open('pipeline/config/companies.json')); print(f'Loaded {len(data)} companies')"
```

Expected: `Loaded 54 companies` (or however many you have — add remaining to reach 70)

- [ ] **Step 3: Commit**

```powershell
git add pipeline/config/companies.json
git commit -m "feat: add companies.json with NSE company metadata"
```

---

## Task 3: Create `pipeline/requirements.txt`

**Files:**
- Create: `pipeline/requirements.txt`

- [ ] **Step 1: Write requirements file**

```
# pipeline/requirements.txt
pandas>=2.0
numpy>=1.24
scikit-learn>=1.3
xgboost>=2.0
statsmodels>=0.14
ta>=0.11
torch>=2.0
firebase-admin>=6.0
pytest>=7.4
```

- [ ] **Step 2: Verify install (in a test environment)**

```powershell
pip install -r pipeline/requirements.txt --dry-run
```

Expected: no errors, lists packages to install

- [ ] **Step 3: Commit**

```powershell
git add pipeline/requirements.txt
git commit -m "feat: add pipeline requirements.txt"
```

---

## Task 4: Create `push_to_firestore.py`

**Files:**
- Create: `pipeline/scripts/push_to_firestore.py`
- Create: `tests/pipeline/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Write the failing test**

Create `tests/__init__.py` (empty) and `tests/pipeline/__init__.py` (empty), then create `tests/pipeline/test_push_to_firestore.py`:

```python
# tests/pipeline/test_push_to_firestore.py
import json
import os
from unittest.mock import MagicMock, patch, call
import pytest

# Set required env vars before importing module
os.environ.setdefault("FIREBASE_SERVICE_ACCOUNT_JSON", json.dumps({
    "type": "service_account", "project_id": "test",
    "private_key_id": "x", "private_key": "x",
    "client_email": "x@test.iam.gserviceaccount.com",
    "client_id": "x", "auth_uri": "", "token_uri": "",
    "auth_provider_x509_cert_url": "", "client_x509_cert_url": ""
}))
os.environ.setdefault("FIREBASE_STORAGE_BUCKET", "test.appspot.com")


@patch("pipeline.scripts.push_to_firestore.firebase_admin")
@patch("pipeline.scripts.push_to_firestore.firestore")
@patch("pipeline.scripts.push_to_firestore.credentials")
def test_write_snapshot_calls_correct_path(mock_creds, mock_fs, mock_admin):
    mock_admin._apps = []
    mock_db = MagicMock()
    mock_fs.client.return_value = mock_db

    from pipeline.scripts.push_to_firestore import write_snapshot
    data = {"signal": "BUY", "current_price_KES": 33.05}
    write_snapshot(mock_db, "SCOM_NR", "2026-07-15", data)

    mock_db.collection.assert_called_with("companies")
    mock_db.collection().document.assert_called_with("SCOM_NR")
    mock_db.collection().document().collection.assert_called_with("snapshots")
    mock_db.collection().document().collection().document.assert_called_with("2026-07-15")
    mock_db.collection().document().collection().document().set.assert_called_once_with(data)


@patch("pipeline.scripts.push_to_firestore.firebase_admin")
@patch("pipeline.scripts.push_to_firestore.firestore")
@patch("pipeline.scripts.push_to_firestore.credentials")
def test_update_company_public_writes_summary_fields(mock_creds, mock_fs, mock_admin):
    mock_admin._apps = []
    mock_db = MagicMock()
    mock_fs.client.return_value = mock_db

    from pipeline.scripts.push_to_firestore import update_company_public
    data = {"current_price": 33.05, "signal": "SELL", "price_preview": [32.0, 33.0]}
    update_company_public(mock_db, "SCOM_NR", data)

    mock_db.collection().document().update.assert_called_once_with(data)


@patch("pipeline.scripts.push_to_firestore.firebase_admin")
@patch("pipeline.scripts.push_to_firestore.firestore")
@patch("pipeline.scripts.push_to_firestore.credentials")
def test_write_market_overview_uses_correct_collection(mock_creds, mock_fs, mock_admin):
    mock_admin._apps = []
    mock_db = MagicMock()
    mock_fs.client.return_value = mock_db

    from pipeline.scripts.push_to_firestore import write_market_overview
    data = {"top_gainers": [], "top_losers": [], "signal_distribution": {"BUY": 10}}
    write_market_overview(mock_db, "2026-07-15", data)

    mock_db.collection.assert_called_with("market_overview")
    mock_db.collection().document.assert_called_with("2026-07-15")
    mock_db.collection().document().set.assert_called_once_with(data)
```

- [ ] **Step 2: Run tests to confirm they fail**

```powershell
cd "C:\Users\moeng\nse_predictor"
python -m pytest tests/pipeline/test_push_to_firestore.py -v 2>&1 | Select-Object -First 20
```

Expected: `ModuleNotFoundError: No module named 'pipeline.scripts.push_to_firestore'`

- [ ] **Step 3: Create `pipeline/scripts/__init__.py`**

```python
# pipeline/scripts/__init__.py
```

- [ ] **Step 4: Write `pipeline/scripts/push_to_firestore.py`**

```python
# pipeline/scripts/push_to_firestore.py
import os
import json
import firebase_admin
from firebase_admin import credentials, firestore, storage as fb_storage


def get_db():
    if not firebase_admin._apps:
        sa_raw = os.environ["FIREBASE_SERVICE_ACCOUNT_JSON"]
        sa_dict = json.loads(sa_raw) if sa_raw.strip().startswith("{") else json.loads(open(sa_raw).read())
        cred = credentials.Certificate(sa_dict)
        firebase_admin.initialize_app(cred, {
            "storageBucket": os.environ["FIREBASE_STORAGE_BUCKET"]
        })
    return firestore.client()


def write_snapshot(db, ticker: str, date_str: str, data: dict) -> None:
    (db.collection("companies")
       .document(ticker)
       .collection("snapshots")
       .document(date_str)
       .set(data))


def write_technicals(db, ticker: str, date_str: str, data: dict) -> None:
    (db.collection("companies")
       .document(ticker)
       .collection("technicals")
       .document(date_str)
       .set(data))


def update_company_public(db, ticker: str, data: dict) -> None:
    db.collection("companies").document(ticker).update(data)


def write_market_overview(db, date_str: str, data: dict) -> None:
    (db.collection("market_overview")
       .document(date_str)
       .set(data))


def upload_model_to_storage(local_path: str, storage_path: str) -> None:
    bucket = fb_storage.bucket()
    blob = bucket.blob(storage_path)
    blob.upload_from_filename(local_path)


def download_model_from_storage(storage_path: str, local_path: str) -> bool:
    bucket = fb_storage.bucket()
    blob = bucket.blob(storage_path)
    if not blob.exists():
        return False
    import os
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    blob.download_to_filename(local_path)
    return True
```

- [ ] **Step 5: Run tests — expect pass**

```powershell
python -m pytest tests/pipeline/test_push_to_firestore.py -v
```

Expected:
```
test_push_to_firestore.py::test_write_snapshot_calls_correct_path PASSED
test_push_to_firestore.py::test_update_company_public_writes_summary_fields PASSED
test_push_to_firestore.py::test_write_market_overview_uses_correct_collection PASSED
3 passed
```

- [ ] **Step 6: Commit**

```powershell
git add pipeline/scripts/ tests/
git commit -m "feat: add push_to_firestore.py with Firestore writer functions"
```

---

## Task 5: Create `run_inference.py` — daily entry point

**Files:**
- Create: `pipeline/scripts/run_inference.py`
- Create: `tests/pipeline/test_run_inference.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/pipeline/test_run_inference.py
import sys, os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "pipeline"))

MOCK_DF = pd.DataFrame({
    "Open": [30.0, 31.0, 32.0],
    "High": [31.0, 32.0, 33.0],
    "Low":  [29.0, 30.0, 31.0],
    "Close":[30.5, 31.5, 32.5],
    "Volume":[1000, 1100, 1200],
}, index=pd.date_range("2026-07-13", periods=3))


def test_build_company_result_has_required_keys():
    from pipeline.scripts.run_inference import build_company_result
    signal = {
        "signal": "BUY",
        "risk_adjusted_signal": "BUY",
        "current_price_KES": 32.5,
        "predicted_price_KES": 34.0,
        "predicted_change_pct": 4.6,
        "var_95_pct": -2.1,
        "rationale": "Model predicts 4.6% gain",
    }
    metrics = {"rmse": 1.2, "mae": 0.9, "mape": 3.1, "directional_accuracy": 78.0}
    actuals = np.array([30.5, 31.5, 32.5])
    preds   = np.array([30.8, 31.2, 32.1])
    forecast = np.array([33.0, 33.5, 34.0])

    result = build_company_result(signal, metrics, actuals, preds, forecast)

    for key in ["signal", "risk_adjusted_signal", "current_price_KES",
                "predicted_price_KES", "predicted_change_pct",
                "var_95_pct", "rationale", "metrics",
                "actuals", "preds", "forecast"]:
        assert key in result, f"Missing key: {key}"

    assert isinstance(result["actuals"], list)
    assert isinstance(result["preds"], list)
    assert isinstance(result["forecast"], list)


def test_build_technicals_result_has_required_keys():
    from pipeline.scripts.run_inference import build_technicals_result
    result = build_technicals_result(MOCK_DF, "2026-07-15")
    for key in ["rsi_14", "sma_20", "sma_50", "sma_200",
                "ema_12", "ema_26", "volume", "daily_return",
                "monthly_heatmap"]:
        assert key in result, f"Missing key: {key}"
```

- [ ] **Step 2: Run test — expect fail**

```powershell
python -m pytest tests/pipeline/test_run_inference.py -v 2>&1 | Select-Object -First 10
```

Expected: `ImportError: cannot import name 'build_company_result'`

- [ ] **Step 3: Write `pipeline/scripts/run_inference.py`**

```python
# pipeline/scripts/run_inference.py
"""
Daily inference entry point.
Usage: python pipeline/scripts/run_inference.py
Env:   FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_STORAGE_BUCKET
"""
import sys, os, json, logging
from pathlib import Path
from datetime import date, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

PIPELINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_ROOT))
sys.path.insert(0, str(PIPELINE_ROOT.parent))

from config import load_companies, DEFAULT_INVESTMENT, DEFAULT_CONFIDENCE
from src.data.fetcher import fetch_nse_data
from src.data.cleaner import clean_ohlcv
from src.analysis.price_trend import price_change_analysis
from src.analysis.returns import daily_return_analysis
from src.analysis.moving_averages import compute_moving_averages
from src.analysis.risk import value_at_risk
from src.features.engineer import build_feature_matrix, select_top_features
from src.models.arima_model import arima_predict_test
from src.models.lstm_model import train_lstm, lstm_predict, save_lstm
from src.models.xgboost_model import train_xgboost, save_xgboost, evaluate
from src.models.ensemble import ensemble_predict, generate_signal, compute_ensemble_metrics
from scripts.push_to_firestore import (
    get_db, write_snapshot, write_technicals,
    update_company_public, write_market_overview,
    download_model_from_storage,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TODAY = date.today().isoformat()
MODELS_TMP = Path("/tmp/nse_models")


def _download_models(ticker: str) -> bool:
    """Pull saved model files from Firebase Storage into /tmp/nse_models/."""
    safe = ticker.replace(".", "_")
    files = [f"{safe}_lstm.pt", f"{safe}_lstm_scaler.pkl", f"{safe}_xgboost.pkl"]
    all_ok = True
    for fname in files:
        ok = download_model_from_storage(
            storage_path=f"models/{fname}",
            local_path=str(MODELS_TMP / fname),
        )
        if not ok:
            log.warning("Model not found in Storage: %s — will train from scratch", fname)
            all_ok = False
    return all_ok


def build_company_result(
    signal: dict,
    metrics: dict,
    actuals: np.ndarray,
    preds: np.ndarray,
    forecast: np.ndarray,
) -> dict:
    return {
        **signal,
        "metrics": metrics,
        "actuals": actuals.tolist(),
        "preds": preds.tolist(),
        "forecast": forecast.tolist(),
    }


def build_technicals_result(df: pd.DataFrame, date_str: str) -> dict:
    try:
        import ta
        close = df["Close"]
        volume = df["Volume"] if "Volume" in df.columns else pd.Series(0, index=df.index)

        rsi    = ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-1]
        macd_i = ta.trend.MACD(close)
        bb     = ta.volatility.BollingerBands(close)
        sma20  = close.rolling(20).mean().iloc[-1]
        sma50  = close.rolling(50).mean().iloc[-1]
        sma200 = close.rolling(200).mean().iloc[-1]
        ema12  = close.ewm(span=12).mean().iloc[-1]
        ema26  = close.ewm(span=26).mean().iloc[-1]

        monthly = (
            df["Close"].resample("ME").last().pct_change() * 100
        ).dropna()
        monthly_heatmap = {
            str(k)[:7]: round(float(v), 2)
            for k, v in monthly.items()
        }

        def _f(x):
            return None if (isinstance(x, float) and np.isnan(x)) else round(float(x), 4)

        return {
            "date": date_str,
            "rsi_14":      _f(rsi),
            "macd":        _f(macd_i.macd().iloc[-1]),
            "macd_signal": _f(macd_i.macd_signal().iloc[-1]),
            "macd_hist":   _f(macd_i.macd_diff().iloc[-1]),
            "bb_upper":    _f(bb.bollinger_hband().iloc[-1]),
            "bb_mid":      _f(bb.bollinger_mavg().iloc[-1]),
            "bb_lower":    _f(bb.bollinger_lband().iloc[-1]),
            "sma_20":  _f(sma20),
            "sma_50":  _f(sma50),
            "sma_200": _f(sma200),
            "ema_12":  _f(ema12),
            "ema_26":  _f(ema26),
            "volume":       int(volume.iloc[-1]) if len(volume) else 0,
            "avg_volume_30d": int(volume.tail(30).mean()) if len(volume) else 0,
            "daily_return":   _f(df["Close"].pct_change().iloc[-1] * 100),
            "volatility_30d": _f(df["Close"].pct_change().tail(30).std() * 100),
            "monthly_heatmap": monthly_heatmap,
        }
    except Exception as e:
        log.error("Technicals failed: %s", e)
        return {"date": date_str, "error": str(e), "monthly_heatmap": {},
                "rsi_14": None, "sma_20": None, "sma_50": None, "sma_200": None,
                "ema_12": None, "ema_26": None, "volume": 0, "daily_return": None}


def run_company(company: dict) -> dict | None:
    ticker = company["ticker"]
    safe   = ticker.replace(".", "_")
    csv_p  = PIPELINE_ROOT / "data" / "raw" / company["csv"]
    log.info("Processing %s ...", ticker)

    try:
        raw_df = fetch_nse_data(ticker, csv_path=str(csv_p) if csv_p.exists() else None)
        cleaned_df, _ = clean_ohlcv(raw_df, ticker=ticker)

        ret_df, _   = daily_return_analysis(cleaned_df)
        ma_df       = compute_moving_averages(ret_df)
        var_res     = value_at_risk(cleaned_df, investment=DEFAULT_INVESTMENT,
                                    confidence=DEFAULT_CONFIDENCE)
        feature_df  = build_feature_matrix(ma_df)
        feature_cols = select_top_features(feature_df)

        # ARIMA
        arima_preds, arima_actuals = arima_predict_test(cleaned_df["Close"])

        # LSTM
        model, scaler, test_ds, device = train_lstm(feature_df, feature_cols)
        n_price = 1 + len(feature_cols)
        lstm_preds, lstm_actuals = lstm_predict(model, test_ds, scaler, device, n_price)

        # XGBoost
        xgb_model, _, xgb_actuals, xgb_preds = train_xgboost(feature_df, feature_cols)

        # Ensemble
        n = min(len(lstm_preds), len(xgb_preds), len(arima_preds))
        ens_preds   = ensemble_predict(lstm_preds[-n:], xgb_preds[-n:], arima_preds[-n:])
        ens_metrics = compute_ensemble_metrics(lstm_actuals[-n:], ens_preds)

        current_price  = float(cleaned_df["Close"].iloc[-1])
        predicted_next = float(ens_preds[-1]) if len(ens_preds) > 0 else current_price
        var_pct        = var_res["historical_var_pct"]
        signal_result  = generate_signal(current_price, predicted_next, var_pct)

        # 30-day forward forecast: repeat last prediction as placeholder
        # (replace with actual forecast logic when model supports it)
        forecast = [float(predicted_next)] * 30

        snapshot   = build_company_result(signal_result, ens_metrics,
                                          lstm_actuals[-n:], ens_preds, np.array(forecast))
        technicals = build_technicals_result(cleaned_df, TODAY)

        price_preview = cleaned_df["Close"].tail(30).tolist()

        return {
            "ticker": safe,
            "snapshot": snapshot,
            "technicals": technicals,
            "public_update": {
                "current_price": current_price,
                "change_pct_today": float(cleaned_df["Close"].pct_change().iloc[-1] * 100),
                "signal": signal_result["signal"],
                "price_preview": price_preview,
                "last_updated": TODAY,
            },
        }
    except Exception as e:
        log.error("FAILED %s: %s", ticker, e, exc_info=True)
        return None


def aggregate_market_overview(results: list[dict]) -> dict:
    rows = []
    sector_totals: dict[str, list] = {}
    signals = {"BUY": 0, "HOLD": 0, "SELL": 0}

    for r in results:
        if r is None:
            continue
        pub = r["public_update"]
        snap = r["snapshot"]
        rows.append((r["ticker"], pub["change_pct_today"]))
        sig = pub["signal"]
        signals[sig] = signals.get(sig, 0) + 1

    rows.sort(key=lambda x: x[1], reverse=True)
    top_gainers = [{"ticker": t, "change_pct": round(c, 2)} for t, c in rows[:5]]
    top_losers  = [{"ticker": t, "change_pct": round(c, 2)} for t, c in rows[-5:]]

    return {
        "date": TODAY,
        "top_gainers": top_gainers,
        "top_losers": top_losers,
        "signal_distribution": signals,
        "sector_performance": {},   # populated in future iteration
        "nse20_value": None,
        "nse20_change_pct": None,
    }


def main():
    MODELS_TMP.mkdir(parents=True, exist_ok=True)
    db        = get_db()
    companies = load_companies()
    results   = []

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(run_company, c): c for c in companies}
        for fut in as_completed(futures):
            res = fut.result()
            if res is None:
                continue
            write_snapshot(db, res["ticker"], TODAY, res["snapshot"])
            write_technicals(db, res["ticker"], TODAY, res["technicals"])
            update_company_public(db, res["ticker"], res["public_update"])
            results.append(res)
            log.info("Written to Firestore: %s", res["ticker"])

    overview = aggregate_market_overview(results)
    write_market_overview(db, TODAY, overview)
    log.info("Market overview written. Done — %d companies processed.", len(results))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests — expect pass**

```powershell
python -m pytest tests/pipeline/test_run_inference.py -v
```

Expected:
```
test_run_inference.py::test_build_company_result_has_required_keys PASSED
test_run_inference.py::test_build_technicals_result_has_required_keys PASSED
2 passed
```

- [ ] **Step 5: Commit**

```powershell
git add pipeline/scripts/run_inference.py tests/pipeline/test_run_inference.py
git commit -m "feat: add run_inference.py daily pipeline entry point"
```

---

## Task 6: Create `run_training.py` — weekly training entry point

**Files:**
- Create: `pipeline/scripts/run_training.py`

- [ ] **Step 1: Write `pipeline/scripts/run_training.py`**

```python
# pipeline/scripts/run_training.py
"""
Weekly training entry point — trains LSTM, XGBoost, ARIMA for all companies
and uploads model artifacts to Firebase Storage.

Usage: python pipeline/scripts/run_training.py
Env:   FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_STORAGE_BUCKET
"""
import sys, os, logging
from pathlib import Path
from datetime import date

PIPELINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_ROOT))
sys.path.insert(0, str(PIPELINE_ROOT.parent))

from config import load_companies, DEFAULT_INVESTMENT, DEFAULT_CONFIDENCE, MODELS_DIR
from src.data.fetcher import fetch_nse_data
from src.data.cleaner import clean_ohlcv
from src.analysis.returns import daily_return_analysis
from src.analysis.moving_averages import compute_moving_averages
from src.features.engineer import build_feature_matrix, select_top_features
from src.models.lstm_model import train_lstm, save_lstm
from src.models.xgboost_model import train_xgboost, save_xgboost, evaluate
from src.models.arima_model import arima_predict_test
from src.models.ensemble import compute_ensemble_metrics, ensemble_predict
from scripts.push_to_firestore import get_db, upload_model_to_storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TODAY = date.today().isoformat()


def train_company(company: dict, db) -> dict | None:
    ticker = company["ticker"]
    safe   = ticker.replace(".", "_")
    csv_p  = PIPELINE_ROOT / "data" / "raw" / company["csv"]
    log.info("Training %s ...", ticker)

    try:
        raw_df      = fetch_nse_data(ticker, csv_path=str(csv_p) if csv_p.exists() else None)
        cleaned_df, _ = clean_ohlcv(raw_df, ticker=ticker)
        ret_df, _   = daily_return_analysis(cleaned_df)
        ma_df       = compute_moving_averages(ret_df)
        feature_df  = build_feature_matrix(ma_df)
        feature_cols = select_top_features(feature_df)

        # LSTM
        model, scaler, test_ds, device = train_lstm(feature_df, feature_cols)
        save_lstm(model, scaler, ticker)
        n_price = 1 + len(feature_cols)
        from src.models.lstm_model import lstm_predict
        lstm_preds, lstm_actuals = lstm_predict(model, test_ds, scaler, device, n_price)

        # XGBoost
        xgb_model, _, xgb_actuals, xgb_preds = train_xgboost(feature_df, feature_cols)
        save_xgboost(xgb_model, ticker)

        # ARIMA
        arima_preds, arima_actuals = arima_predict_test(cleaned_df["Close"])

        # Upload models to Firebase Storage
        local_models = MODELS_DIR
        for fname in [f"{safe}_lstm.pt", f"{safe}_lstm_scaler.pkl", f"{safe}_xgboost.pkl"]:
            local_path = str(local_models / fname)
            if Path(local_path).exists():
                upload_model_to_storage(local_path, f"models/{fname}")
                log.info("Uploaded %s", fname)

        # Compute ensemble metrics for logging
        n = min(len(lstm_preds), len(xgb_preds), len(arima_preds))
        from src.models.ensemble import ensemble_predict, compute_ensemble_metrics
        ens = ensemble_predict(lstm_preds[-n:], xgb_preds[-n:], arima_preds[-n:])
        metrics = compute_ensemble_metrics(lstm_actuals[-n:], ens)

        # Write training run record to Firestore
        (db.collection("companies")
           .document(safe)
           .collection("training_runs")
           .document(TODAY)
           .set({"date": TODAY, "metrics": metrics, "status": "ok"}))

        log.info("Done %s — MAPE=%.2f%%", ticker, metrics.get("mape", -1))
        return {"ticker": safe, "metrics": metrics}

    except Exception as e:
        log.error("FAILED %s: %s", ticker, e, exc_info=True)
        return None


def main():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    db        = get_db()
    companies = load_companies()
    ok, failed = 0, 0

    for company in companies:
        result = train_company(company, db)
        if result:
            ok += 1
        else:
            failed += 1

    log.info("Training complete: %d ok, %d failed", ok, failed)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```powershell
git add pipeline/scripts/run_training.py
git commit -m "feat: add run_training.py weekly model training entry point"
```

---

## Task 7: Write `firestore.rules`

**Files:**
- Create: `firestore.rules`

- [ ] **Step 1: Write security rules**

```javascript
// firestore.rules
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {

    // Company metadata + public signal/preview — anyone can read
    match /companies/{ticker} {
      allow read: if true;
      allow write: if false;
    }

    // Full snapshots (predictions, actuals, metrics) — logged-in users only
    match /companies/{ticker}/snapshots/{date} {
      allow read: if request.auth != null;
      allow write: if false;
    }

    // Technical indicators — logged-in users only
    match /companies/{ticker}/technicals/{date} {
      allow read: if request.auth != null;
      allow write: if false;
    }

    // Training run history — logged-in users only
    match /companies/{ticker}/training_runs/{date} {
      allow read: if request.auth != null;
      allow write: if false;
    }

    // Market overview — anyone can read
    match /market_overview/{date} {
      allow read: if true;
      allow write: if false;
    }

    // User profile + watchlist — owner only
    match /users/{uid} {
      allow read, write: if request.auth != null && request.auth.uid == uid;
    }
  }
}
```

- [ ] **Step 2: Commit**

```powershell
git add firestore.rules
git commit -m "feat: add Firestore security rules"
```

---

## Task 8: Create GitHub Actions workflows

**Files:**
- Create: `.github/workflows/daily_inference.yml`
- Create: `.github/workflows/weekly_training.yml`
- Create: `.github/workflows/deploy.yml`

- [ ] **Step 1: Create `.github/workflows/` directory**

```powershell
New-Item -ItemType Directory -Force -Path "C:\Users\moeng\nse_predictor\.github\workflows"
```

- [ ] **Step 2: Write `daily_inference.yml`**

```yaml
# .github/workflows/daily_inference.yml
name: Daily NSE Inference

on:
  schedule:
    - cron: "0 15 * * 1-5"   # 15:00 UTC = 18:00 EAT, Mon–Fri
  workflow_dispatch:           # allow manual trigger

jobs:
  inference:
    runs-on: ubuntu-latest
    timeout-minutes: 90

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"
          cache-dependency-path: pipeline/requirements.txt

      - name: Install dependencies
        run: pip install -r pipeline/requirements.txt

      - name: Run inference
        env:
          FIREBASE_SERVICE_ACCOUNT_JSON: ${{ secrets.FIREBASE_SERVICE_ACCOUNT_JSON }}
          FIREBASE_STORAGE_BUCKET: ${{ secrets.FIREBASE_STORAGE_BUCKET }}
        run: |
          cd $GITHUB_WORKSPACE
          python pipeline/scripts/run_inference.py

      - name: Notify on failure
        if: failure()
        run: echo "::error::Daily inference failed — check logs above"
```

- [ ] **Step 3: Write `weekly_training.yml`**

```yaml
# .github/workflows/weekly_training.yml
name: Weekly NSE Model Training

on:
  schedule:
    - cron: "0 23 * * 0"    # 23:00 UTC Saturday = 02:00 EAT Sunday
  workflow_dispatch:

jobs:
  training:
    runs-on: ubuntu-latest
    timeout-minutes: 300      # up to 5 hrs for 70 companies

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"
          cache-dependency-path: pipeline/requirements.txt

      - name: Install dependencies
        run: pip install -r pipeline/requirements.txt

      - name: Run training
        env:
          FIREBASE_SERVICE_ACCOUNT_JSON: ${{ secrets.FIREBASE_SERVICE_ACCOUNT_JSON }}
          FIREBASE_STORAGE_BUCKET: ${{ secrets.FIREBASE_STORAGE_BUCKET }}
        run: |
          cd $GITHUB_WORKSPACE
          python pipeline/scripts/run_training.py

      - name: Notify on failure
        if: failure()
        run: echo "::error::Weekly training failed — check logs above"
```

- [ ] **Step 4: Write `deploy.yml` (placeholder — completed in Plan 2)**

```yaml
# .github/workflows/deploy.yml
name: Deploy Frontend

on:
  push:
    branches: [main]
    paths:
      - "frontend/**"

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Deploy to Cloudflare Pages
        run: echo "Frontend deploy — implemented in Plan 2"
```

- [ ] **Step 5: Commit**

```powershell
git add .github/
git commit -m "feat: add GitHub Actions workflows for daily inference, weekly training, and deploy"
```

---

## Task 9: Seed Firestore company documents

**Files:**
- Create: `pipeline/scripts/seed_companies.py`

Run this once to populate the `companies/{ticker}` top-level documents in Firestore from `companies.json`.

- [ ] **Step 1: Write `seed_companies.py`**

```python
# pipeline/scripts/seed_companies.py
"""
Run once: populates companies/{ticker} documents in Firestore.
Usage: python pipeline/scripts/seed_companies.py
Env:   FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_STORAGE_BUCKET
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import load_companies
from scripts.push_to_firestore import get_db

def main():
    db = get_db()
    companies = load_companies()
    for c in companies:
        safe = c["ticker"].replace(".", "_")
        doc = {
            "name":         c["name"],
            "short":        c["short"],
            "sector":       c["sector"],
            "color":        c["color"],
            "icon":         c["icon"],
            "ticker":       c["ticker"],
            "csv":          c["csv"],
            "current_price":    None,
            "change_pct_today": None,
            "signal":           None,
            "price_preview":    [],
            "last_updated":     None,
        }
        db.collection("companies").document(safe).set(doc, merge=True)
        print(f"  Seeded: {safe}")
    print(f"\nDone — {len(companies)} companies seeded.")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run locally to seed Firestore**

Set your environment variables first, then:

```powershell
$env:FIREBASE_SERVICE_ACCOUNT_JSON = Get-Content "path\to\serviceAccountKey.json" -Raw
$env:FIREBASE_STORAGE_BUCKET = "your-project-id.appspot.com"
cd "C:\Users\moeng\nse_predictor"
python pipeline/scripts/seed_companies.py
```

Expected output:
```
  Seeded: SCOM_NR
  Seeded: EQTY_NR
  ...
Done — 54 companies seeded.
```

- [ ] **Step 3: Commit**

```powershell
git add pipeline/scripts/seed_companies.py
git commit -m "feat: add seed_companies.py to initialise Firestore company documents"
```

---

## Task 10: End-to-end dry-run verification

- [ ] **Step 1: Run full test suite**

```powershell
cd "C:\Users\moeng\nse_predictor"
python -m pytest tests/ -v
```

Expected:
```
tests/pipeline/test_push_to_firestore.py::test_write_snapshot_calls_correct_path PASSED
tests/pipeline/test_push_to_firestore.py::test_update_company_public_writes_summary_fields PASSED
tests/pipeline/test_push_to_firestore.py::test_write_market_overview_uses_correct_collection PASSED
tests/pipeline/test_run_inference.py::test_build_company_result_has_required_keys PASSED
tests/pipeline/test_run_inference.py::test_build_technicals_result_has_required_keys PASSED
5 passed
```

- [ ] **Step 2: Run inference dry-run on 1 company (local, no Firestore)**

```powershell
cd "C:\Users\moeng\nse_predictor"
python -c "
import sys; sys.path.insert(0,'pipeline')
from scripts.run_inference import run_company
from config import load_companies
companies = load_companies()
scom = next(c for c in companies if c['ticker'] == 'SCOM.NR')
result = run_company(scom)
if result:
    print('Signal:', result['snapshot']['signal'])
    print('Price:', result['snapshot']['current_price_KES'])
    print('Technicals keys:', list(result['technicals'].keys()))
else:
    print('FAILED')
"
```

Expected: prints signal, price, and technicals keys without error.

- [ ] **Step 3: Add GitHub Actions secrets in your repo**

Go to: `github.com/MoengaAlex1/<repo-name>/settings/secrets/actions`

Add:
- `FIREBASE_SERVICE_ACCOUNT_JSON` — paste full JSON from Firebase Console → Project Settings → Service Accounts → Generate new private key
- `FIREBASE_STORAGE_BUCKET` — e.g. `your-project-id.appspot.com`

- [ ] **Step 4: Trigger daily inference manually to verify workflow**

Go to: GitHub → Actions → "Daily NSE Inference" → Run workflow

Verify: workflow completes without errors, Firestore shows populated documents.

- [ ] **Step 5: Final commit with tag**

```powershell
git tag plan-1-complete
git push origin main --tags
```

---

## Summary

**What Plan 1 delivers:**
- Python pipeline reorganised into `pipeline/` — clean separation from future frontend
- `companies.json` — single config file drives everything for all 70 companies
- `push_to_firestore.py` — typed Firestore writer (tested with mocks)
- `run_inference.py` — daily batch job: cleans, runs ensemble, writes snapshots + technicals
- `run_training.py` — weekly training job: retrains models, uploads to Firebase Storage
- `seed_companies.py` — one-time Firestore seed for company metadata
- `firestore.rules` — security rules matching the spec
- Three GitHub Actions workflows: daily inference, weekly training, frontend deploy

**Plan 2 builds on this:** React/Vite/TypeScript frontend scaffold, Firebase Auth, routing, layout, AuthGuard — all reading from the Firestore that Plan 1 populates.
