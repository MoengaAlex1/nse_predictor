"""
Deploy firestore.rules (and optionally storage.rules) via the Firebase
Rules REST API.

Bypasses `firebase deploy`'s pre-flight serviceusage.googleapis.com API
check, which requires an IAM role our pipeline service account doesn't
have (serviceusage.serviceUsageConsumer). Uploads the ruleset and
attaches it to the appropriate release in two REST calls per surface.

Usage:  python pipeline/scripts/deploy_firestore_rules.py [--storage-only|--firestore-only]
Env:    FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_PROJECT_ID,
        FIREBASE_STORAGE_BUCKET (required if deploying storage rules)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
FIRESTORE_RULES_FILE = REPO_ROOT / "firestore.rules"
STORAGE_RULES_FILE   = REPO_ROOT / "storage.rules"

# Backward-compat alias — nothing external should be using it, but keep
# defined in case a caller still expects the old name.
RULES_FILE = FIRESTORE_RULES_FILE

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


def _deploy_ruleset(
    *, surface: str, rules_path: Path, release_id: str,
    project_id: str, headers: dict, base: str, filename_hint: str,
) -> None:
    """Upload one ruleset and attach it to one release."""
    import requests

    if not rules_path.exists():
        raise SystemExit(f"Missing {rules_path}")
    rules_text = rules_path.read_text(encoding="utf-8")

    print(f"\n→ [{surface}] Creating ruleset for project '{project_id}'")
    create_url = f"{base}/projects/{project_id}/rulesets"
    body = {"source": {"files": [{"name": filename_hint, "content": rules_text}]}}
    r = requests.post(create_url, headers=headers, json=body, timeout=30)
    if r.status_code >= 400:
        raise SystemExit(f"[{surface}] Ruleset create failed {r.status_code}: {r.text}")
    ruleset_name = r.json().get("name")
    if not ruleset_name:
        raise SystemExit(f"[{surface}] Ruleset create returned no name: {r.text}")
    print(f"  ← {ruleset_name}")

    print(f"→ [{surface}] Publishing release '{release_id}'")
    patch_url = f"{base}/{release_id}"
    patch_body = {
        "release":    {"name": release_id, "rulesetName": ruleset_name},
        "updateMask": "ruleset_name",
    }
    r = requests.patch(patch_url, headers=headers, json=patch_body, timeout=30)
    if r.status_code >= 400:
        raise SystemExit(f"[{surface}] Release PATCH failed {r.status_code}: {r.text}")
    print(f"  ← published, ruleset now live")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--firestore-only", action="store_true",
                        help="Deploy only firestore.rules")
    parser.add_argument("--storage-only", action="store_true",
                        help="Deploy only storage.rules")
    args = parser.parse_args()
    do_firestore = not args.storage_only
    do_storage   = not args.firestore_only

    sa_raw = os.environ["FIREBASE_SERVICE_ACCOUNT_JSON"].strip()
    project_id = project_id_from_env(sa_raw)
    token = get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }
    base = "https://firebaserules.googleapis.com/v1"

    # ── Firestore ─────────────────────────────────────────────────────────
    # The PATCH endpoint's request type is UpdateReleaseRequest (per the
    # discovery doc), NOT a bare Release — the body must wrap the Release
    # under a "release" key and include updateMask INSIDE the body:
    #   { "release": { name, rulesetName }, "updateMask": "ruleset_name" }
    # Earlier attempts with a bare Release body were rejected because
    # protobuf JSON parsing on the server looked for top-level fields
    # named "release"/"updateMask" and reported "rulesetName" as unknown.
    if do_firestore:
        _deploy_ruleset(
            surface="firestore",
            rules_path=FIRESTORE_RULES_FILE,
            release_id=f"projects/{project_id}/releases/cloud.firestore",
            project_id=project_id, headers=headers, base=base,
            filename_hint="firestore.rules",
        )

    # ── Storage ───────────────────────────────────────────────────────────
    # Storage releases are per-bucket. FIREBASE_STORAGE_BUCKET is the
    # canonical bucket (e.g. "nse-market-dashboard.firebasestorage.app").
    if do_storage:
        bucket = os.environ.get("FIREBASE_STORAGE_BUCKET", "").strip()
        if not bucket:
            raise SystemExit("FIREBASE_STORAGE_BUCKET env var is required for storage rules")
        _deploy_ruleset(
            surface="storage",
            rules_path=STORAGE_RULES_FILE,
            release_id=f"projects/{project_id}/releases/firebase.storage/{bucket}",
            project_id=project_id, headers=headers, base=base,
            filename_hint="storage.rules",
        )

    print("\n=== Rules deployed ===")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
