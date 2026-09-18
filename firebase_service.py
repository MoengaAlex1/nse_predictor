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
_rtdb = None


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
            if sa_raw.strip().startswith("{"):
                sa_dict = json.loads(sa_raw)
            else:
                with open(sa_raw, encoding="utf-8") as _fh:
                    sa_dict = json.load(_fh)
            cred = credentials.Certificate(sa_dict)
            firebase_admin.initialize_app(cred, {"storageBucket": bucket})
        _db = firestore.client()
        return _db
    except Exception as e:
        log.warning("Firebase init failed: %s", e)
        return None


def get_signal(doc_id: str) -> dict | None:
    """Return the latest pre-computed signal for a company from Firestore, or None.

    doc_id must be the short-form Firestore document key (e.g. 'BRIT', not 'BRIT.NR').
    """
    db = _get_db()
    if db is None:
        return None
    try:
        doc = db.collection("companies").document(doc_id).get()
        if doc.exists:
            return doc.to_dict()
        return None
    except Exception as e:
        log.warning("Firestore read failed for %s: %s", doc_id, e)
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


def _get_rtdb():
    """Lazy RTDB client. Requires FIREBASE_DATABASE_URL and the same service
    account used for Firestore. Cached across calls."""
    global _rtdb
    if _rtdb is not None:
        return _rtdb
    # _get_db initialises firebase_admin so we piggy-back on that side effect.
    if _get_db() is None:
        return None
    db_url = os.environ.get("FIREBASE_DATABASE_URL", "").strip()
    if not db_url:
        return None
    try:
        from firebase_admin import db as fb_db
        _rtdb = fb_db.reference("/", url=db_url)
        return _rtdb
    except Exception as e:
        log.warning("RTDB init failed: %s", e)
        return None


def get_history(doc_id: str):
    """Return a pandas DataFrame indexed by date for one ticker, sourced from
    RTDB `prices/{doc_id}`. Returns None if RTDB isn't configured, the ticker
    has no rows, or firebase_admin isn't importable. `doc_id` must be the
    short form (SCOM, EQTY) — the same key `bulk_write_prices` writes under.

    Columns: Open / High / Low / Close / Volume. Matches the shape the Dash
    app's chart builders expected from the on-disk CSV path.
    """
    root = _get_rtdb()
    if root is None:
        return None
    try:
        node = root.child(f"prices/{doc_id}").get()
    except Exception as e:
        log.warning("RTDB read failed for %s: %s", doc_id, e)
        return None
    if not isinstance(node, dict) or not node:
        return None
    try:
        import pandas as pd
    except ImportError:
        return None
    rows = []
    for date_str, row in node.items():
        if not isinstance(row, dict):
            continue
        rows.append({
            "Date":   date_str,
            "Open":   row.get("o"),
            "High":   row.get("h"),
            "Low":    row.get("l"),
            "Close":  row.get("c"),
            "Volume": row.get("v"),
        })
    if not rows:
        return None
    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"]).set_index("Date").sort_index()
    return df
