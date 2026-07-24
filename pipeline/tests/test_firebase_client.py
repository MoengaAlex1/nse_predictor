import importlib
import os
from unittest.mock import MagicMock, patch


def test_get_firestore_returns_client():
    env = {
        "FIREBASE_SERVICE_ACCOUNT_JSON": '{"type":"service_account","project_id":"p","private_key_id":"k","private_key":"-----BEGIN RSA PRIVATE KEY-----\\nMIIEowIBAAKCAQEA2a2rwplBQLF29amygykEMmYz0+Ks9vBKqNzOuOQBkEBKAFGe\\nyP0aUHBQQaHRGCdKAPbSoJqEdYMPEAZHEEBUfBfVNDqhDdRJP5YzMJpJkoBdRJWQ\\n-----END RSA PRIVATE KEY-----\\n","client_email":"t@p.iam.gserviceaccount.com","client_id":"1","auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token","auth_provider_x509_cert_url":"https://www.googleapis.com/oauth2/v1/certs","client_x509_cert_url":"https://www.googleapis.com/robot/v1/metadata/x509/t%40p.iam.gserviceaccount.com"}',
        "FIREBASE_RTDB_URL": "https://test-rtdb.firebaseio.com",
        "FIREBASE_STORAGE_BUCKET": "test.appspot.com",
    }
    with patch.dict(os.environ, env), \
         patch("firebase_admin._apps", {}), \
         patch("firebase_admin.initialize_app", return_value=MagicMock()), \
         patch("firebase_admin.credentials.Certificate", return_value=MagicMock()), \
         patch("firebase_admin.firestore.client", return_value=MagicMock()) as mock_fs:
        import pipeline.scripts.firebase_client as fc
        importlib.reload(fc)
        result = fc.get_firestore()
        assert result is not None


def test_get_rtdb_returns_reference():
    env = {
        "FIREBASE_SERVICE_ACCOUNT_JSON": '{"type":"service_account","project_id":"p","private_key_id":"k","private_key":"-----BEGIN RSA PRIVATE KEY-----\\nMIIEowIBAAKCAQEA2a2rwplBQLzz\\n-----END RSA PRIVATE KEY-----\\n","client_email":"t@p.iam.gserviceaccount.com","client_id":"1","auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token","auth_provider_x509_cert_url":"https://www.googleapis.com/oauth2/v1/certs","client_x509_cert_url":"https://www.googleapis.com/robot/v1/metadata/x509/t%40p.iam.gserviceaccount.com"}',
        "FIREBASE_RTDB_URL": "https://test-rtdb.firebaseio.com",
        "FIREBASE_STORAGE_BUCKET": "test.appspot.com",
    }
    with patch.dict(os.environ, env), \
         patch("firebase_admin._apps", {}), \
         patch("firebase_admin.initialize_app", return_value=MagicMock()), \
         patch("firebase_admin.credentials.Certificate", return_value=MagicMock()), \
         patch("firebase_admin.db.reference", return_value=MagicMock()) as mock_rtdb:
        import pipeline.scripts.firebase_client as fc
        importlib.reload(fc)
        result = fc.get_rtdb()
        assert result is not None


def test_init_not_called_twice():
    with patch("firebase_admin._apps", {"[DEFAULT]": MagicMock()}), \
         patch("firebase_admin.initialize_app") as mock_init, \
         patch("firebase_admin.firestore.client", return_value=MagicMock()):
        import pipeline.scripts.firebase_client as fc
        importlib.reload(fc)
        fc.get_firestore()
        mock_init.assert_not_called()
