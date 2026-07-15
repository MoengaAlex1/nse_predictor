"""
PyTorch LSTM — mirrors the plan's architecture (128→64→32 stacked LSTM).
Replaces tensorflow/keras for Python 3.14 compatibility.
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


# ── Dataset ───────────────────────────────────────────────────────────────

class SequenceDataset(Dataset):
    def __init__(self, data: np.ndarray, seq_len: int = SEQUENCE_LENGTH):
        self.X, self.y = [], []
        for i in range(seq_len, len(data)):
            self.X.append(data[i - seq_len:i])
            self.y.append(data[i, 0])  # Close price is index 0
        self.X = torch.tensor(np.array(self.X), dtype=torch.float32)
        self.y = torch.tensor(np.array(self.y), dtype=torch.float32)

    def __len__(self):
        return len(self.y)

    def __getitem__(self, idx):
        return self.X[idx], self.y[idx]


# ── Model ─────────────────────────────────────────────────────────────────

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
        out = self.drop3(out[:, -1, :])  # last timestep

        out = self.relu(self.fc1(out))
        return self.fc2(out).squeeze(1)


# ── Training ──────────────────────────────────────────────────────────────

def train_lstm(
    df: pd.DataFrame,
    feature_cols: list,
    target_col: str = "Close",
    epochs: int = 100,
    batch_size: int = 32,
    patience: int = 15,
    lr: float = 1e-3,
):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[LSTM] Training on {device}")

    data = df[[target_col] + feature_cols].values
    split = int(len(data) * TRAIN_SPLIT)
    train_data, test_data = data[:split], data[split:]

    scaler = MinMaxScaler(feature_range=(0, 1))
    train_scaled = scaler.fit_transform(train_data)
    test_scaled  = scaler.transform(test_data)

    val_size = int(len(train_scaled) * 0.1)
    val_scaled   = train_scaled[-val_size:]
    train_scaled = train_scaled[:-val_size]

    train_ds = SequenceDataset(train_scaled)
    val_ds   = SequenceDataset(val_scaled)
    test_ds  = SequenceDataset(test_scaled)

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
        # Train
        model.train()
        train_loss = 0.0
        for X_batch, y_batch in train_loader:
            X_batch, y_batch = X_batch.to(device), y_batch.to(device)
            optimizer.zero_grad()
            pred = model(X_batch)
            loss = criterion(pred, y_batch)
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * len(y_batch)
        train_loss /= len(train_ds)

        # Validate
        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for X_batch, y_batch in val_loader:
                X_batch, y_batch = X_batch.to(device), y_batch.to(device)
                pred = model(X_batch)
                val_loss += criterion(pred, y_batch).item() * len(y_batch)
        val_loss /= max(len(val_ds), 1)

        scheduler.step(val_loss)

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
            no_improve = 0
        else:
            no_improve += 1

        if epoch % 10 == 0 or epoch == 1:
            print(f"  Epoch {epoch:3d}/{epochs} — train_loss: {train_loss:.6f}  val_loss: {val_loss:.6f}")

        if no_improve >= patience:
            print(f"  Early stopping at epoch {epoch}")
            break

    if best_state:
        model.load_state_dict(best_state)

    return model, scaler, test_ds, device


def lstm_predict(model, test_ds: SequenceDataset, scaler, device,
                 n_price_features: int) -> tuple[np.ndarray, np.ndarray]:
    model.eval()
    loader = DataLoader(test_ds, batch_size=64, shuffle=False)
    preds, actuals = [], []
    with torch.no_grad():
        for X_batch, y_batch in loader:
            pred = model(X_batch.to(device)).cpu().numpy()
            preds.extend(pred)
            actuals.extend(y_batch.numpy())

    # Inverse-transform the Close price (index 0)
    def inverse_close(vals):
        dummy = np.zeros((len(vals), n_price_features))
        dummy[:, 0] = vals
        return scaler.inverse_transform(dummy)[:, 0]

    return inverse_close(np.array(preds)), inverse_close(np.array(actuals))


def save_lstm(model, scaler, ticker: str) -> Path:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), MODELS_DIR / f"{ticker.replace('.', '_')}_lstm.pt")
    joblib.dump(scaler, MODELS_DIR / f"{ticker.replace('.', '_')}_lstm_scaler.pkl")
    print(f"  LSTM model saved -> {ticker}_lstm.pt")
    return MODELS_DIR


def load_lstm(ticker: str, n_features: int):
    model = NSELSTMModel(n_features)
    model.load_state_dict(
        torch.load(MODELS_DIR / f"{ticker.replace('.', '_')}_lstm.pt",
                   map_location="cpu")
    )
    model.eval()
    scaler = joblib.load(MODELS_DIR / f"{ticker.replace('.', '_')}_lstm_scaler.pkl")
    return model, scaler
