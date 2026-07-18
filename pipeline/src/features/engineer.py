import json
import pandas as pd
import numpy as np
from pathlib import Path
from config import DATA_FEATURES, TOP_FEATURES, MODELS_DIR

try:
    import ta
    _TA_AVAILABLE = True
except ImportError:
    _TA_AVAILABLE = False
    print("Warning: 'ta' library not installed. Run: pip install ta")


def build_feature_matrix(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    close = df["Close"]
    high  = df["High"]
    low   = df["Low"]
    vol   = df["Volume"]

    if _TA_AVAILABLE:
        # ── Trend ──────────────────────────────────────────────────────────
        df["SMA_10"]      = ta.trend.sma_indicator(close, 10)
        df["SMA_20"]      = ta.trend.sma_indicator(close, 20)
        df["SMA_50"]      = ta.trend.sma_indicator(close, 50)
        df["EMA_12"]      = ta.trend.ema_indicator(close, 12)
        df["EMA_26"]      = ta.trend.ema_indicator(close, 26)
        df["MACD"]        = ta.trend.macd(close)
        df["MACD_signal"] = ta.trend.macd_signal(close)
        df["MACD_diff"]   = ta.trend.macd_diff(close)
        df["ADX"]         = ta.trend.adx(high, low, close)

        # ── Momentum ───────────────────────────────────────────────────────
        df["RSI_14"]    = ta.momentum.rsi(close, window=14)
        df["RSI_9"]     = ta.momentum.rsi(close, window=9)
        df["Stoch_K"]   = ta.momentum.stoch(high, low, close)
        df["Stoch_D"]   = ta.momentum.stoch_signal(high, low, close)
        df["Williams_R"]= ta.momentum.williams_r(high, low, close)
        df["ROC"]       = ta.momentum.roc(close, window=12)

        # ── Volatility ─────────────────────────────────────────────────────
        df["BB_upper"]      = ta.volatility.bollinger_hband(close)
        df["BB_lower"]      = ta.volatility.bollinger_lband(close)
        df["BB_width"]      = ta.volatility.bollinger_wband(close)
        df["ATR"]           = ta.volatility.average_true_range(high, low, close)
        df["Keltner_upper"] = ta.volatility.keltner_channel_hband(high, low, close)
        df["Keltner_lower"] = ta.volatility.keltner_channel_lband(high, low, close)

        # ── Volume ─────────────────────────────────────────────────────────
        df["OBV"]  = ta.volume.on_balance_volume(close, vol)
        df["VWAP"] = ta.volume.volume_weighted_average_price(high, low, close, vol)
        df["MFI"]  = ta.volume.money_flow_index(high, low, close, vol)

    else:
        # Minimal fallback without 'ta'
        df["SMA_10"] = close.rolling(10).mean()
        df["SMA_20"] = close.rolling(20).mean()
        df["SMA_50"] = close.rolling(50).mean()
        df["EMA_12"] = close.ewm(span=12, adjust=False).mean()
        df["EMA_26"] = close.ewm(span=26, adjust=False).mean()

    # ── Price-derived features ─────────────────────────────────────────────
    df["daily_return"]  = close.pct_change()
    df["log_return"]    = np.log(close / close.shift(1))
    df["HL_ratio"]      = (high - low) / close
    df["OC_ratio"]      = (close - df["Open"]) / df["Open"]
    df["gap_pct"]       = (df["Open"] - close.shift(1)) / close.shift(1)

    for lag in [1, 3, 5, 10, 20]:
        df[f"return_lag_{lag}"] = df["daily_return"].shift(lag)

    df["volatility_5d"]  = df["daily_return"].rolling(5).std()
    df["volatility_20d"] = df["daily_return"].rolling(20).std()
    df["volatility_60d"] = df["daily_return"].rolling(60).std()

    # NSE 10% daily band proximity flag
    df["near_band_limit"] = (df["daily_return"].abs() >= 0.08).astype(int)

    df = df.dropna()
    return df


def select_top_features(
    df: pd.DataFrame,
    target_col: str = "Close",
    n_features: int = TOP_FEATURES,
) -> list:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.feature_selection import RFE

    exclude = {"Open", "High", "Low", "Close", "Volume", "Ticker",
               "is_stale", "is_outlier", "golden_cross", "death_cross"}
    feature_cols = [c for c in df.columns if c not in exclude]

    X = df[feature_cols].values
    y = df[target_col].values

    rf = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
    rfe = RFE(estimator=rf, n_features_to_select=n_features, step=5)
    rfe.fit(X, y)

    selected = [feature_cols[i] for i, s in enumerate(rfe.support_) if s]
    print(f"Selected {len(selected)} features via RFE:")
    for f in selected:
        print(f"  • {f}")
    return selected


def save_features(df: pd.DataFrame, ticker: str) -> Path:
    DATA_FEATURES.mkdir(parents=True, exist_ok=True)
    path = DATA_FEATURES / f"{ticker.replace('.', '_')}_features.csv"
    df.to_csv(path)
    return path


def save_feature_cols(feature_cols: list, ticker: str, model_dir: Path = MODELS_DIR) -> Path:
    """Persist the RFE-selected feature list alongside the model artifacts."""
    model_dir.mkdir(parents=True, exist_ok=True)
    path = model_dir / f"{ticker.replace('.', '_')}_feature_cols.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(feature_cols, f)
    print(f"  Feature cols saved → {path.name}  ({len(feature_cols)} features)")
    return path


def load_feature_cols(ticker: str, model_dir: Path = MODELS_DIR) -> list:
    """Load the feature list that was used when the model was trained."""
    path = model_dir / f"{ticker.replace('.', '_')}_feature_cols.json"
    if not path.exists():
        raise FileNotFoundError(f"Feature cols not found: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)
