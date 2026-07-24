"""
Patch firebase_admin into sys.modules before any test file imports scrape_news.
The module-level init guard checks `firebase_admin._apps`; setting it non-empty
skips the Certificate() call that requires a real key file.
"""
import sys
from unittest.mock import MagicMock

_fb = MagicMock()
_fb._apps = {"default": MagicMock()}  # truthy → skips init block in scrape_news
sys.modules.setdefault("firebase_admin", _fb)
sys.modules.setdefault("firebase_admin.credentials", MagicMock())
sys.modules.setdefault("firebase_admin.firestore", MagicMock())
