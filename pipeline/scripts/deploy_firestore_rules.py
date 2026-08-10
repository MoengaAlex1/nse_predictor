"""
Deploy firestore.rules via the Firebase Rules REST API.

Bypasses `firebase deploy`'s pre-flight serviceusage.googleapis.com API
check, which requires an IAM role our pipeline service account doesn't
have (serviceusage.serviceUsageConsumer). Uploads the ruleset and
attaches it to the cloud.firestore release in two REST calls.

Usage:  python pipeline/scripts/deploy_firestore_rules.py
Env:    FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_PROJECT_ID
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
RULES_FILE = REPO_ROOT / "firestore.rules"

SCOPES = ["https://www.googleapis.com/auth/firebase"]


def get_access_token() -> str:
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request

    sa_raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
    if not sa_raw:
        raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON env var is empty")
    sa_info = json.loads(sa_raw) if sa_raw.startswith("{") else json.load(open(sa_raw))
    creds = service_account.Credentials.from_service_account_info(sa_info, scopes=SCOPES)
    creds.refresh(Request())
    return creds.token


def project_id_from_env(sa_raw: str) -> str:
    override = os.environ.get("FIREBASE_PROJECT_ID", "").strip()
    if override:
        return override
    return json.loads(sa_raw)["project_id"]


def main() -> None:
    import requests

    if not RULES_FILE.exists():
        raise SystemExit(f"Missing {RULES_FILE}")
    rules_text = RULES_FILE.read_text(encoding="utf-8")

    sa_raw = os.environ["FIREBASE_SERVICE_ACCOUNT_JSON"].strip()
    project_id = project_id_from_env(sa_raw)
    token = get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    base = "https://firebaserules.googleapis.com/v1"

    print(f"→ Creating ruleset for project '{project_id}'")
    create_url = f"{base}/projects/{project_id}/rulesets"
    body = {
        "source": {
            "files": [
                {"name": "firestore.rules", "content": rules_text},
            ]
        }
    }
    r = requests.post(create_url, headers=headers, json=body, timeout=30)
    if r.status_code >= 400:
        raise SystemExit(f"Ruleset create failed {r.status_code}: {r.text}")
    ruleset_name = r.json().get("name")
    if not ruleset_name:
        raise SystemExit(f"Ruleset create returned no name: {r.text}")
    print(f"  ← {ruleset_name}")

    # Attach ruleset to the cloud.firestore release. Since the release
    # already exists (the console created it on project setup), we PATCH.
    # Key details the API is picky about:
    #  - URL uses the FULL resource name: /v1/projects/{id}/releases/cloud.firestore
    #  - updateMask is REQUIRED (POST/upsert requires an extra IAM role
    #    our SA doesn't have; PATCH via updateRelease only needs
    #    firebase.rules.write)
    #  - updateMask uses proto snake_case field name: "ruleset_name"
    #  - Body must NOT include a "name" field — the resource name lives
    #    entirely in the URL. Sending it in the body gets rejected
    #    with "Unknown name" errors from the protobuf JSON parser.
    release_id = f"projects/{project_id}/releases/cloud.firestore"
    print(f"→ Publishing release '{release_id}'")
    patch_url = f"{base}/{release_id}?updateMask=ruleset_name"
    patch_body = {"rulesetName": ruleset_name}
    r = requests.patch(patch_url, headers=headers, json=patch_body, timeout=30)
    if r.status_code >= 400:
        raise SystemExit(f"Release PATCH failed {r.status_code}: {r.text}")
    print(f"  ← published, ruleset now live")

    print("\n=== Firestore rules deployed ===")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
