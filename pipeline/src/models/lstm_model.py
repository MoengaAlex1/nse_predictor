"""
PyTorch LSTM — 3-layer stacked architecture (128→64→32).
"""
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from sklearn.preprocessing import MinMaxScaler
import joblib
from pathlib import Path
from config import SEQUENCE_LENGTH, TRAIN_SPLIT, MODELS_DIR


# ── Dataset ───────────────────────────────────────────────────────────────────

class SequenceDataset(Dataset):
    def __init__(self, data: np.ndarray, seq_len: int = SEQUENCE_LENGTH):
        self.X, self.y = [], []
        for i in range(seq_len, len(data)):
            self.X.append(data[i - seq_len:i])
            self.y.append(data[i, 0])  # Close is column 0
        self.X = torch.tensor(np.array(self.X), dtype=torch.float32)
        self.y = torch.tensor(np.array(self.y), dtype=torch.float32)

    def __len__(self):
        return len(self.y)

    def __getitem__(self, idx):
        return self.X[idx], self.y[idx]


# ── Model ─────────────────────────────────────────────────────────────────────

class NSELSTMModel(nn.Module):
    def __init__(self, n_features: int):
        super().__init__()
        self.lstm1 = nn.LSTM(n_features, 128, batch_first=True)
        self.drop1 = nn.Dropout(0.2)
        self.bn1   = nn.BatchNorm1d(128)

        self.lstm2 = nn.LSTM(128, 64, batch_first=True)
        self.drop2 = nn.Dropout(0.2)
        self.bn2   = nn.BatchNorm1d(64)

        self.lstm3 = nn.LSTM(64, 32, batch_first=True)
        self.drop3 = nn.Dropout(0.2)

        self.fc1 = nn.Linear(32, 16)
        self.relu = nn.ReLU()
        self.fc2 = nn.Linear(16, 1)

    def forward(self, x):
        out, _ = self.lstm1(x)
        out = self.drop1(out)
        out = self.bn1(out.transpose(1, 2)).transpose(1, 2)

        out, _ = self.lstm2(out)
        out = self.drop2(out)
        out = self.bn2(out.transpose(1, 2)).transpose(1, 2)

        out, _ = self.lstm3(out)
        out = self.drop3(out[:, -1, :])  # last timestep only

        out = self.relu(self.fc1(out))
        return self.fc2(out).squeeze(1)


# ── Training ──────────────────────────────────────────────────────────────────

def train_lstm(
    df: pd.DataFrame,
    feature_cols: list,
    target_col: str = "Close",
    epochs: int = 100,
    batch_size: int = 32,
    patience: int = 15,
    lr: float = 1e-3,
):
    """
    Train LSTM on chronological 80/10/10 split.
    Returns (model, scaler, test_ds, device).
    The scaler is fitted ONLY on training data to prevent look-ahead bias.
    """
    torch.manual_seed(42)
    np.random.seed(42)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[LSTM] Training on {device}")

    cols = [target_col] + feature_cols
    data = df[cols].values.astype(float)

    split = int(len(data) * TRAIN_SPLIT)
    val_size = int(split * 0.1)
    train_end = split - val_size

    train_data = data[:train_end]
    val_data   = data[train_end:split]
    test_data  = data[split:]

    # Fit scaler on training data only
    scaler = MinMaxScaler(feature_range=(0, 1))
    train_scaled = scaler.fit_transform(train_data)
    val_scaled   = scaler.transform(val_data)
    test_scaled  = scaler.transform(test_data)

    train_ds = SequenceDataset(train_scaled)
    val_ds   = SequenceDataset(val_scaled)
    test_ds  = SequenceDataset(test_scaled)

    if len(train_ds) == 0:
        raise ValueError(f"Training set too small after sequence splitting (need >{SEQUENCE_LENGTH} rows)")

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=False)
    val_loader   = DataLoader(val_ds,   batch_size=batch_size, shuffle=False)

    n_features = train_scaled.shape[1]
    model = NSELSTMModel(n_features).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, factor=0.5, patience=7, min_lr=1e-6
    )
    criterion = nn.MSELoss()

    best_val_loss = float("inf")
    best_state = None
    no_improve = 0

    for epoch in range(1, epochs + 1):
        model.train()
        train_loss = 0.0
        for X_batch, y_batch in train_loader:
            X_batch, y_batch = X_batch.to(device), y_batch.to(device)
            optimizer.zero_grad()
            pred = model(X_batch)
            loss = criterion(pred, y_batch)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            train_loss += loss.item() * len(y_batch)
        train_loss /= len(train_ds)

        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for X_batch, y_batch in val_loader:
                X_batch, y_batch = X_batch.to(device), y_batch.to(device)
                val_loss += criterion(model(X_batch), y_batch).item() * len(y_batch)
        val_loss /= max(len(val_ds), 1)

        scheduler.step(val_loss)

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
            no_improve = 0
        else:
            no_improve += 1

        if epoch % 10 == 0 or epoch == 1:
            print(f"  Epoch {epoch:3d}/{epochs} — train: {train_loss:.6f}  val: {val_loss:.6f}")

        if no_improve >= patience:
            print(f"  Early stopping at epoch {epoch}")
            break

    if best_state:
        model.load_state_dict(best_state)

    return model, scaler, test_ds, device


# ── Evaluation (test-set, used during training to log metrics) ────────────────

def lstm_predict(
    model: NSELSTMModel,
    test_ds: SequenceDataset,
    scaler,
    device,
    n_total_features: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Run model on prebuilt test SequenceDataset and return (preds, actuals) in original scale."""
    model.eval()
    loader = DataLoader(test_ds, batch_size=64, shuffle=False)
    preds, actuals = [], []
    with torch.no_grad():
        for X_batch, y_batch in loader:
            pred = model(X_batch.to(device)).cpu().numpy()
            preds.extend(pred)
            actuals.extend(y_batch.numpy())

    def inverse_close(vals):
        dummy = np.zeros((len(vals), n_total_features))
        dummy[:, 0] = vals
        return scaler.inverse_transform(dummy)[:, 0]

    return inverse_close(np.array(preds)), inverse_close(np.array(actuals))


# ── Forward Prediction (used during inference) ────────────────────────────────

def lstm_predict_next(
    model: NSELSTMModel,
    df: pd.DataFrame,
    feature_cols: list,
    scaler,
    device,
    seq_len: int = SEQUENCE_LENGTH,
) -> float:
    """
    Predict the NEXT trading day's Close price.
    Uses the most recent seq_len rows as the lookback window.
    """
    model.eval()
    cols = ["Close"] + feature_cols
    data = df[cols].values.astype(float)
    if len(data) < seq_len:
        raise ValueError(f"Need >= {seq_len} rows for prediction, got {len(data)}")

    window = scaler.transform(data[-seq_len:])
    x = torch.tensor(window[np.newaxis], dtype=torch.float32).to(device)
    with torch.no_grad():
        pred_scaled = model(x).item()

    dummy = np.zeros((1, window.shape[1]))
    dummy[0, 0] = pred_scaled
    return float(scaler.inverse_transform(dummy)[0, 0])


def lstm_forecast_30d(
    model: NSELSTMModel,
    df: pd.DataFrame,
    feature_cols: list,
    scaler,
    device,
    seq_len: int = SEQUENCE_LENGTH,
    steps: int = 30,
) -> list[float]:
    """
    Multi-step rolling forecast: each predicted Close feeds back into next window.
    Non-Close features are carried forward from the last known row.
    Accuracy degrades beyond 5-10 steps — use ARIMA for longer horizons.
    """
    model.eval()
    cols = ["Close"] + feature_cols
    data = df[cols].values.astype(float)
    if len(data) < seq_len:
        raise ValueError(f"Need >= {seq_len} rows for forecast, got {len(data)}")

    window = scaler.transform(data[-seq_len:]).copy()
    forecasts = []

    for _ in range(steps):
        x = torch.tensor(window[np.newaxis], dtype=torch.float32).to(device)
        with torch.no_grad():
            pred_scaled = model(x).item()

        dummy = np.zeros((1, window.shape[1]))
        dummy[0, 0] = pred_scaled
        pred_price = float(scaler.inverse_transform(dummy)[0, 0])
        forecasts.append(pred_price)

        new_row = window[-1].copy()
        new_row[0] = pred_scaled
        window = np.vstack([window[1:], new_row])

    return forecasts


# ── Save / Load ───────────────────────────────────────────────────────────────

def save_lstm(model: NSELSTMModel, scaler, ticker: str, model_dir: Path = MODELS_DIR) -> Path:
    model_dir.mkdir(parents=True, exist_ok=True)
    safe = ticker.replace(".", "_")
    torch.save(model.state_dict(), model_dir / f"{safe}_lstm.pt")
    joblib.dump(scaler, model_dir / f"{safe}_lstm_scaler.pkl")
    print(f"  LSTM saved → {safe}_lstm.pt")
    return model_dir


def load_lstm(ticker: str, n_features: int, model_dir: Path = MODELS_DIR):
    """Load LSTM model and scaler from model_dir. n_features = 1 + len(feature_cols)."""
    safe = ticker.replace(".", "_")
    model = NSELSTMModel(n_features)
    state = torch.load(
        model_dir / f"{safe}_lstm.pt",
        map_location="cpu",
        weights_only=True,
    )
    model.load_state_dict(state)
    model.eval()
    scaler = joblib.load(model_dir / f"{safe}_lstm_scaler.pkl")
    return model, scaler
