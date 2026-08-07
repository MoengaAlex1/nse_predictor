#!/usr/bin/env bash
# Verify the deployed Realtime Database security rules.
#
# Run this AFTER `firebase deploy --only database`. It makes unauthenticated
# requests exactly as an anonymous visitor (or a scraper) would, and asserts
# which ones are allowed.
#
#   ./scripts/verify-rtdb-rules.sh
#
# Exits non-zero if any expectation fails.
#
# LIMITATION: every request here is unauthenticated. The Firebase alert was
# about what a *logged-in* user could reach, and the old rules
# (".read"/".write": "auth != null") denied anonymous access while granting
# any signed-in account full read AND write over the whole database. So the
# root checks below passed even under the insecure rules — see the "write to
# root" line. Under the new rules the grant is `false` rather than
# `auth != null`, which no account can satisfy, so anonymous testing is
# sufficient to prove the hole is closed. Confirm in the Firebase console's
# Rules Playground with an authenticated UID if you want belt and braces.

set -uo pipefail

DB="${FIREBASE_RTDB_URL:-https://nse-market-dashboard-default-rtdb.firebaseio.com}"
TICKER="${1:-SCOM}"
fails=0

# check <description> <expect: allow|deny> <url>
check() {
  local desc="$1" expect="$2" url="$3"
  local body
  body=$(curl -s --max-time 30 "$url")

  local actual="allow"
  case "$body" in
    *'"error"'*'Permission denied'*) actual="deny" ;;
  esac

  if [ "$actual" = "$expect" ]; then
    printf '  PASS  %-52s (%s)\n' "$desc" "$actual"
  else
    printf '  FAIL  %-52s expected %s, got %s\n' "$desc" "$expect" "$actual"
    fails=$((fails + 1))
  fi
}

echo "Verifying RTDB rules at $DB"
echo

echo "Must be BLOCKED — these are the bulk-export and tampering vectors:"
check "read entire database"            deny "$DB/.json?shallow=true"
check "dump every ticker in one request" deny "$DB/prices.json"
check "list all ticker names"            deny "$DB/prices.json?shallow=true"
check "write to root"                    deny "$DB/.json?print=silent"
echo

echo "Must still WORK — the public site depends on these:"
check "read one ticker ($TICKER)"        allow "$DB/prices/$TICKER.json?orderBy=%22%24key%22&limitToLast=1"
check "date-range query ($TICKER)"       allow "$DB/prices/$TICKER.json?orderBy=%22%24key%22&startAt=%222026-01-01%22&endAt=%222026-12-31%22"
echo

if [ "$fails" -eq 0 ]; then
  echo "All checks passed."
else
  echo "$fails check(s) failed."
fi
exit "$fails"
