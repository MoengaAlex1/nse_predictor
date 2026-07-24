# GitHub Actions Secrets Required

The following secrets must be configured in the GitHub repository (Settings → Secrets and variables → Actions) for CI/CD workflows to function correctly.

## Secrets

- `FIREBASE_SERVICE_ACCOUNT_JSON` — Firebase service account JSON (used by 10 workflows for Firestore/Storage access)
- `FIREBASE_STORAGE_BUCKET` — Firebase Storage bucket name (e.g. `your-project.appspot.com`)
- `FIREBASE_RTDB_URL` ← NEW: Firebase Realtime Database URL (e.g. `https://your-project-default-rtdb.firebaseio.com`)
- `ANTHROPIC_API_KEY` ← NEW: For Claude AI features (F4 AI Insights, F5 Prediction Engine)

## Workflows referencing FIREBASE_SERVICE_ACCOUNT_JSON

- `.github/workflows/daily_update.yml`
- `.github/workflows/fix_csv_data.yml`
- `.github/workflows/push_from_storage.yml`
- `.github/workflows/price_scrape.yml`
- `.github/workflows/migrate_company_keys.yml`
- `.github/workflows/seed_companies.yml`
- `.github/workflows/apply_pdf_backfill.yml`
- `.github/workflows/pdf_price_backfill.yml`
- `.github/workflows/weekly_training.yml`
- `.github/workflows/daily_price_update.yml`

## Frontend environment variables

Copy `frontend/.env.example` to `frontend/.env` and fill in real values. The `VITE_FIREBASE_DATABASE_URL` variable is required for Realtime Database features.
