import json
from pathlib import Path

BASE_DIR      = Path(__file__).parent   # pipeline/
REPO_ROOT     = BASE_DIR.parent         # repo root

DATA_RAW      = REPO_ROOT / "data" / "raw"
DATA_CLEANED  = REPO_ROOT / "data" / "cleaned"
DATA_FEATURES = REPO_ROOT / "data" / "features"
MODELS_DIR    = BASE_DIR / "models" / "saved"
REPORTS_DIR   = BASE_DIR / "reports" / "outputs"

NSE_TICKERS = []  # loaded dynamically from companies.json

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

ENSEMBLE_WEIGHTS = (0.25, 0.60, 0.15)


def load_companies() -> list[dict]:
    path = BASE_DIR / "config" / "companies.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_tickers() -> list[str]:
    return [c["ticker"] for c in load_companies()]
