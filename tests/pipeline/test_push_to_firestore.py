# tests/pipeline/test_push_to_firestore.py
import json
import os
from unittest.mock import MagicMock, patch
import pytest

os.environ.setdefault("FIREBASE_SERVICE_ACCOUNT_JSON", json.dumps({
    "type": "service_account", "project_id": "test",
    "private_key_id": "x", "private_key": "x",
    "client_email": "x@test.iam.gserviceaccount.com",
    "client_id": "x", "auth_uri": "", "token_uri": "",
    "auth_provider_x509_cert_url": "", "client_x509_cert_url": ""
}))
os.environ.setdefault("FIREBASE_STORAGE_BUCKET", "test.appspot.com")


@patch("pipeline.scripts.push_to_firestore.firebase_admin")
@patch("pipeline.scripts.push_to_firestore.firestore")
@patch("pipeline.scripts.push_to_firestore.credentials")
def test_write_snapshot_calls_correct_path(mock_creds, mock_fs, mock_admin):
    mock_admin._apps = []
    mock_db = MagicMock()
    mock_fs.client.return_value = mock_db

    from pipeline.scripts.push_to_firestore import write_snapshot
    data = {"signal": "BUY", "current_price_KES": 33.05}
    write_snapshot(mock_db, "SCOM_NR", "2026-07-15", data)

    mock_db.collection.assert_called_with("companies")
    mock_db.collection().document.assert_called_with("SCOM_NR")
    mock_db.collection().document().collection.assert_called_with("snapshots")
    mock_db.collection().document().collection().document.assert_called_with("2026-07-15")
    mock_db.collection().document().collection().document().set.assert_called_once_with(data)


@patch("pipeline.scripts.push_to_firestore.firebase_admin")
@patch("pipeline.scripts.push_to_firestore.firestore")
@patch("pipeline.scripts.push_to_firestore.credentials")
def test_update_company_public_writes_summary_fields(mock_creds, mock_fs, mock_admin):
    mock_admin._apps = []
    mock_db = MagicMock()
    mock_fs.client.return_value = mock_db

    from pipeline.scripts.push_to_firestore import update_company_public
    data = {"current_price": 33.05, "signal": "SELL", "price_preview": [32.0, 33.0]}
    update_company_public(mock_db, "SCOM_NR", data)

    mock_db.collection().document().update.assert_called_once_with(data)


@patch("pipeline.scripts.push_to_firestore.firebase_admin")
@patch("pipeline.scripts.push_to_firestore.firestore")
@patch("pipeline.scripts.push_to_firestore.credentials")
def test_write_market_overview_uses_correct_collection(mock_creds, mock_fs, mock_admin):
    mock_admin._apps = []
    mock_db = MagicMock()
    mock_fs.client.return_value = mock_db

    from pipeline.scripts.push_to_firestore import write_market_overview
    data = {"top_gainers": [], "top_losers": [], "signal_distribution": {"BUY": 10}}
    write_market_overview(mock_db, "2026-07-15", data)

    mock_db.collection.assert_called_with("market_overview")
    mock_db.collection().document.assert_called_with("2026-07-15")
    mock_db.collection().document().set.assert_called_once_with(data)
