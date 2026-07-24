"""
Pytest configuration for pipeline tests.

Stubs out firebase_admin at the sys.modules level before any test module
imports pipeline.scripts.scrape_news (which initialises Firebase at module
import time). Without this, CI fails because no service-account credentials
are present in the test environment.
"""
import sys
from unittest.mock import MagicMock

# Build a minimal firebase_admin stub and plant it into sys.modules BEFORE
# any test file imports from pipeline.scripts.scrape_news.
_fa_stub = MagicMock()
_fa_stub._apps = {}  # makes `if not firebase_admin._apps` falsy → init runs
_fa_stub.initialize_app = MagicMock()
_fa_stub.credentials.Certificate = MagicMock(return_value=MagicMock())

_fs_stub = MagicMock()
_fs_stub.client = MagicMock(return_value=MagicMock())
_fa_stub.firestore = _fs_stub

sys.modules.setdefault("firebase_admin", _fa_stub)
sys.modules.setdefault("firebase_admin.credentials", _fa_stub.credentials)
sys.modules.setdefault("firebase_admin.firestore", _fs_stub)
