import json
import os
from datetime import date, timedelta
import firebase_admin
from firebase_admin import credentials, firestore, storage as fb_storage


def get_db():
    if not firebase_admin._apps:
        sa_raw = os.environ["FIREBASE_SERVICE_ACCOUNT_JSON"]
        if sa_raw.strip().startswith("{"):
            sa_dict = json.loads(sa_raw)
        else:
            with open(sa_raw, encoding="utf-8") as _fh:
                sa_dict = json.load(_fh)
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
    db.collection("companies").document(ticker).set(data, merge=True)


def prune_old_docs(db, ticker: str, subcollection: str, keep_days: int = 90) -> int:
    """Delete date-keyed subcollection documents older than keep_days. Returns count deleted."""
    cutoff = (date.today() - timedelta(days=keep_days)).isoformat()
    col_ref = (
        db.collection("companies")
          .document(ticker)
          .collection(subcollection)
    )
    old_docs = [d for d in col_ref.stream() if d.id < cutoff]
    for doc in old_docs:
        doc.reference.delete()
    return len(old_docs)


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
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    blob.download_to_filename(local_path)
    return True
