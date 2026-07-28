import os, json, sys, runpy
from pathlib import Path

key = json.load(open(Path(__file__).parent / "temp_sa_key.json"))
os.environ["FIREBASE_SERVICE_ACCOUNT_JSON"] = json.dumps(key)
os.environ["FIREBASE_RTDB_URL"] = "https://nse-market-dashboard-default-rtdb.firebaseio.com"
os.environ["FIREBASE_STORAGE_BUCKET"] = "nse-market-dashboard.firebasestorage.app"

sys.argv = ["nse_price_cleaner.py", "--force-push-rtdb"]
runpy.run_path("pipeline/scripts/nse_price_cleaner.py", run_name="__main__")
