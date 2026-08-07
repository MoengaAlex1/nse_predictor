# Firebase security posture

## Realtime Database

RTDB stores one thing: `prices/{TICKER}/{YYYY-MM-DD}` OHLCV nodes.

### The rules

```json
{
  "rules": {
    ".read": false,
    ".write": false,
    "prices": { "$ticker": { ".read": true, ".write": false } }
  }
}
```

RTDB rules **cascade downward**: a grant at a shallower path applies to
everything beneath it, and there is no way to revoke it lower down. That is
what made the previous rules dangerous, and it is what makes these safe.

| Request | Result | Why |
|---|---|---|
| `GET /prices/SCOM.json` | allowed | `prices/$ticker` grants read |
| `GET /prices.json` | **denied** | no grant at `prices`; root is `false` |
| `GET /.json` | **denied** | root is `false` |
| any write from any client | **denied** | `.write` is `false` everywhere |

### Why `.write: false` does not break the pipeline

Every writer authenticates with a **service account** via
`credentials.Certificate(...)` in `pipeline/scripts/firebase_client.py`. The
Firebase **Admin SDK bypasses security rules entirely** — rules govern client
SDKs and the REST API, never admin credentials. So the pipeline keeps writing
with all client writes denied.

### What the previous rules did wrong

```json
{ "prices": { ".read": true, ".write": "auth != null" },
  ".read": "auth != null", ".write": "auth != null" }
```

`auth != null` means *any* signed-in account, not a trusted one. If any sign-in
method is enabled, anyone could register and then read **and overwrite or delete
the entire database**. That is what Firebase flagged.

## "Let people view the data but not download it"

**This is not fully achievable, and it is important to be clear about why.**

The browser has to receive the data in order to draw the chart. Anything on
screen is already on the visitor's machine and visible in the Network tab.
Security rules cannot tell "render this" apart from "save this" — it is the
same request. Client-side measures (disabling right-click, obfuscating the
bundle) stop nobody and are not worth the code.

What the rules above *do* achieve:

- **The one-request full export is gone.** `GET /prices.json` returned
  **22.4 MB — the entire price history, to anyone, with no credentials.** That
  now returns permission denied.
- **Ticker enumeration is gone.** `?shallow=true` on `prices` used to list every
  ticker. Now a scraper must already know the symbols.
- **Tampering is gone.** No client can write, so nobody can corrupt or delete
  prices.

What remains possible: someone who knows the tickers can still fetch them one
at a time. This is friction, not prevention — roughly 61 requests instead of 1.

### If scraping needs to actually stop

**Firebase App Check** is the real control. It attests that requests come from
your genuine web app (via reCAPTCHA Enterprise) and rejects everything else —
curl, scripts, bots. Rules answer *who may read what*; App Check answers *what
software may ask at all*. It needs console configuration plus a few lines in
`frontend/src/lib/firebase.ts`, and it is the only thing here that meaningfully
blocks automated bulk collection.

## Firestore

Firestore rules live in `firestore.rules` and are deliberately public-read for
the collections the site renders (`companies`, `market_overview`, `events`),
with `snapshots`, `technicals`, `financials` and `macro` behind
`request.auth != null`. Every collection is `allow write: if false` — writes
come from the Admin SDK only.

> **Known gap:** `firebase.json` declares only the `database` target. It does
> **not** reference `firestore.rules` or any index file, so `firebase deploy`
> never ships them. The live Firestore rules are whatever was last set by hand
> in the console and may have drifted from the copy in this repo. Reconcile the
> two before wiring Firestore into `firebase.json`, or a deploy will silently
> overwrite live rules with a stale file.

## Deploying and verifying

```sh
firebase deploy --only database     # ships database.rules.json
./scripts/verify-rtdb-rules.sh      # asserts the result from outside
```

The verifier checks both directions: that bulk export and writes are blocked,
**and** that the per-ticker reads the site depends on still work. Run it after
every rules change.
