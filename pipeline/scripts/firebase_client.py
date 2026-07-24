import json
import os
import firebase_admin
from firebase_admin import credentials, firestore, db as _rtdb, storage as _storage


def _init() -> None:
    if firebase_admin._apps:
        return
    sa_raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    if not sa_raw:
        raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON env var is not set")
    if sa_raw.strip().startswith("{"):
        sa_dict = json.loads(sa_raw)
    else:
        with open(sa_raw, encoding="utf-8") as fh:
            sa_dict = json.load(fh)
    cred = credentials.Certificate(sa_dict)
    firebase_admin.initialize_app(cred, {
        "databaseURL":   os.environ.get("FIREBASE_RTDB_URL", ""),
        "storageBucket": os.environ.get("FIREBASE_STORAGE_BUCKET", ""),
    })


def get_firestore():
    _init()
    return firestore.client()


def get_rtdb():
    _init()
    return _rtdb.reference("/")
