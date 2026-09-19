import os
import logging
from datetime import date, timedelta
import firebase_admin
from firebase_admin import storage as fb_storage

from pipeline.scripts.firebase_client import get_firestore as _get_firestore
from pipeline.src.identity import is_short, short_from_display_ticker, InvalidCompanyKeyError

log = logging.getLogger(__name__)


def get_db():
    return _get_firestore()


def _normalize_or_warn(ticker: str, caller: str) -> str:
    """
    Enforce that every companies-collection doc-id is the short form.

    If the caller hands us a legacy "SCOM.NR" / "SCOM_NR", we log a warning
    and coerce to short — so partial refactors don't silently write to the
    wrong key. Truly malformed ids raise loudly.
    """
    if is_short(ticker):
        return ticker
    try:
        coerced = short_from_display_ticker(ticker)
    except InvalidCompanyKeyError:
        log.error("%s: refusing to write to non-short doc-id %r (unrecoverable)",
                  caller, ticker)
        raise
    log.warning("%s: coerced non-short doc-id %r -> %r (please fix caller)",
                caller, ticker, coerced)
    return coerced


def write_snapshot(db, ticker: str, date_str: str, data: dict) -> None:
    tkr = _normalize_or_warn(ticker, "write_snapshot")
    (db.collection("companies")
       .document(tkr)
       .collection("snapshots")
       .document(date_str)
       .set(data))


def write_technicals(db, ticker: str, date_str: str, data: dict) -> None:
    tkr = _normalize_or_warn(ticker, "write_technicals")
    (db.collection("companies")
       .document(tkr)
       .collection("technicals")
       .document(date_str)
       .set(data))


def update_company_public(db, ticker: str, data: dict) -> None:
    tkr = _normalize_or_warn(ticker, "update_company_public")
    db.collection("companies").document(tkr).set(data, merge=True)


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


def upload_model_to_storage(local_path: str, storage_path: str) -> bool:
    """Push a file to Firebase Storage. Returns True on success, False when
    Storage is unreachable (403 billing-disabled, network flake). Callers
    should treat False as 'the upload didn't happen but pipeline can
    continue' — the same defensive posture download_model_from_storage
    takes. Without this, one 403 on a 60-ticker loop kills the whole run.
    """
    from google.api_core import exceptions as gexc
    try:
        bucket = fb_storage.bucket()
        blob = bucket.blob(storage_path)
        blob.upload_from_filename(local_path)
        return True
    except gexc.Forbidden as e:
        import logging
        logging.getLogger(__name__).error(
            "Storage 403 on upload of %s — skipping upload. Reason: %s",
            storage_path, e,
        )
        return False
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(
            "Storage upload of %s failed (unexpected): %s", storage_path, e,
        )
        return False


def download_model_from_storage(storage_path: str, local_path: str) -> bool:
    """Fetch a file from Firebase Storage to local disk. Returns False on
    'not present' and on infra-level failures we can degrade past (billing
    disabled, transient 5xx). The caller decides whether the missing file
    is fatal or has a fallback (run_inference.py uses the repo-checked-in
    CSVs when Storage is unreachable).
    """
    from google.api_core import exceptions as gexc

    bucket = fb_storage.bucket()
    blob = bucket.blob(storage_path)
    try:
        if not blob.exists():
            return False
    except gexc.Forbidden as e:
        # 403 covers "billing disabled", "IAM revoked", "bucket in a project
        # you can no longer read" — all cases where retrying won't help and
        # the whole pipeline shouldn't abort. Log loudly so ops sees it.
        import logging
        logging.getLogger(__name__).error(
            "Storage 403 for %s — falling back to repo copy. Reason: %s",
            storage_path, e,
        )
        return False
    parent = os.path.dirname(local_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    try:
        blob.download_to_filename(local_path)
    except gexc.Forbidden as e:
        import logging
        logging.getLogger(__name__).error(
            "Storage 403 on download of %s — falling back to repo copy. Reason: %s",
            storage_path, e,
        )
        return False
    return True
