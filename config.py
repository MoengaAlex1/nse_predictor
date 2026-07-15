from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent
DATA_RAW      = BASE_DIR / "data" / "raw"
DATA_CLEANED  = BASE_DIR / "data" / "cleaned"
DATA_FEATURES = BASE_DIR / "data" / "features"
MODELS_DIR    = BASE_DIR / "models" / "saved"
REPORTS_DIR   = BASE_DIR / "reports" / "outputs"

# ── NSE Tickers ────────────────────────────────────────────────────────────
NSE_TICKERS = ["SCOM.NR", "EQTY.NR", "KCB.NR", "EABL.NR", "COOP.NR"]

# ── Data window ────────────────────────────────────────────────────────────
START_DATE = "2015-01-01"

# ── Model hyperparameters ──────────────────────────────────────────────────
SEQUENCE_LENGTH = 60   # look-back window for LSTM (trading days)
TOP_FEATURES    = 25   # features selected by RFE
TRAIN_SPLIT     = 0.80 # chronological train/test ratio

# ── Risk defaults ──────────────────────────────────────────────────────────
DEFAULT_INVESTMENT  = 100_000  # KES
DEFAULT_CONFIDENCE  = 0.95
MONTE_CARLO_SIMS    = 10_000
MONTE_CARLO_HORIZON = 30       # days

# ── NSE market rules ───────────────────────────────────────────────────────
NSE_DAILY_BAND_PCT  = 9.9      # ±9.9% hard cap on predicted daily move
MIN_TRADING_DAYS    = 500      # minimum history required for modelling
MIN_VOLUME_PCT      = 0.60     # fraction of days that must have Volume > 0
MAX_STALE_RUN       = 10       # consecutive stale days → liquidity warning
CLOSE_COMPLETENESS  = 0.95     # minimum Close price completeness

# ── Ensemble weights ───────────────────────────────────────────────────────
ENSEMBLE_WEIGHTS = (0.25, 0.60, 0.15)  # LSTM, XGBoost, ARIMA — XGBoost weighted higher on NSE stale data
