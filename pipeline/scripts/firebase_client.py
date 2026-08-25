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
    # Recent firebase-admin releases surface the "Invalid database id
    # (default)" gRPC error when the SDK is left to infer the database
    # from the environment. Passing an explicit database_id keeps the
    # call working across SDK versions. Override with FIRESTORE_DATABASE_ID
    # if the project uses a named (non-default) Firestore database.
    db_id = os.environ.get("FIRESTORE_DATABASE_ID", "(default)")
    try:
        return firestore.client(database_id=db_id)
    except TypeError:
        # Older firebase-admin versions (< 6.something) don't accept the
        # database_id kwarg — fall back to the plain call.
        return firestore.client()


def get_rtdb():
    _init()
    return _rtdb.reference("/")
