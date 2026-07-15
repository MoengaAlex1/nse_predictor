import json
import os
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
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    blob.download_to_filename(local_path)
    return True
