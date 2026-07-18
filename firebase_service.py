"""
Firebase service for reading pre-computed signals and writing admin job status.
Falls back gracefully if Firebase credentials are not configured.
"""
import json
import logging
import os
from datetime import datetime

log = logging.getLogger(__name__)

_db = None


def _get_db():
    global _db
    if _db is not None:
        return _db
    sa_raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON", "")
    bucket = os.environ.get("FIREBASE_STORAGE_BUCKET", "")
    if not sa_raw or not bucket:
        return None
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
        if not firebase_admin._apps:
            sa_dict = json.loads(sa_raw) if sa_raw.strip().startswith("{") else json.loads(open(sa_raw).read())
            cred = credentials.Certificate(sa_dict)
            firebase_admin.initialize_app(cred, {"storageBucket": bucket})
        _db = firestore.client()
        return _db
    except Exception as e:
        log.warning("Firebase init failed: %s", e)
        return None


def get_signal(ticker: str) -> dict | None:
    """Return the latest pre-computed signal for a ticker from Firestore, or None."""
    db = _get_db()
    if db is None:
        return None
    safe = ticker.replace(".", "_")
    try:
        doc = db.collection("companies").document(safe).get()
        if doc.exists:
            return doc.to_dict()
        return None
    except Exception as e:
        log.warning("Firestore read failed for %s: %s", ticker, e)
        return None


def get_all_signals() -> dict:
    """Return {ticker: signal_dict} for all companies. Empty dict if Firebase unavailable."""
    db = _get_db()
    if db is None:
        return {}
    try:
        docs = db.collection("companies").stream()
        return {doc.id: doc.to_dict() for doc in docs}
    except Exception as e:
        log.warning("Firestore bulk read failed: %s", e)
        return {}


def get_last_update_dates() -> dict:
    """Return {ticker: last_updated_date_str} for all companies."""
    signals = get_all_signals()
    return {t: s.get("last_updated", "never") for t, s in signals.items()}


def write_admin_log(job_id: str, data: dict) -> None:
    """Write an admin job log entry to Firestore."""
    db = _get_db()
    if db is None:
        return
    try:
        db.collection("admin_jobs").document(job_id).set({
            **data,
            "timestamp": datetime.utcnow().isoformat(),
        })
    except Exception as e:
        log.warning("Failed to write admin log: %s", e)


def firebase_available() -> bool:
    return _get_db() is not None
