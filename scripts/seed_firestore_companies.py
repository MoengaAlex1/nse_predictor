"""
Seed Firestore companies collection with NSE Kenya company metadata.
Run once after creating your Firebase project.

Usage:
    export FIREBASE_SERVICE_ACCOUNT_JSON='{"type":"service_account",...}'
    export FIREBASE_STORAGE_BUCKET='your-project.appspot.com'
    python scripts/seed_firestore_companies.py
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

COMPANIES = [
    ("ABSA_NR",  "ABSA Bank Kenya",              "Banking",                          "#38bdf8"),
    ("BAT_NR",   "BAT Kenya",                    "Manufacturing and Allied",          "#a78bfa"),
    ("BKG_NR",   "BK Group",                     "Banking",                          "#f472b6"),
    ("BOC_NR",   "BOC Kenya",                    "Energy and Petroleum",             "#fb923c"),
    ("BRIT_NR",  "Britam Holdings",              "Insurance",                        "#34d399"),
    ("CARB_NR",  "Carbacid Investments",         "Construction and Allied",          "#f59e0b"),
    ("CGEN_NR",  "Centum Generation",            "Investment",                       "#60a5fa"),
    ("CIC_NR",   "CIC Insurance Group",          "Insurance",                        "#e879f9"),
    ("COOP_NR",  "Co-operative Bank",            "Banking",                          "#4ade80"),
    ("CRWN_NR",  "Crown Paints Kenya",           "Construction and Allied",          "#fbbf24"),
    ("CTUM_NR",  "Cavendish Management",         "Commercial and Services",          "#c084fc"),
    ("DTK_NR",   "Diamond Trust Bank",           "Banking",                          "#818cf8"),
    ("EABL_NR",  "East African Breweries",       "Manufacturing and Allied",         "#f87171"),
    ("EGAD_NR",  "East African Portland Cement", "Investment",                       "#2dd4bf"),
    ("EQTY_NR",  "Equity Group Holdings",        "Banking",                          "#facc15"),
    ("EVRD_NR",  "Eveready East Africa",         "Commercial and Services",          "#94a3b8"),
    ("FTGH_NR",  "Fahari I-REIT",               "Real Estate Investment Trust",     "#06b6d4"),
    ("GLD_NR",   "Gold Coin Kenya",              "Commercial and Services",          "#8b5cf6"),
    ("HAFR_NR",  "Home Afrika",                  "Commercial and Services",          "#ec4899"),
    ("HFCK_NR",  "HF Group",                     "Banking",                          "#84cc16"),
    ("IMH_NR",   "I&M Holdings",                 "Banking",                          "#38bdf8"),
    ("JUB_NR",   "Jubilee Holdings",             "Insurance",                        "#a78bfa"),
    ("KAPC_NR",  "KAPS Medical International",   "Commercial and Services",          "#f472b6"),
    ("KCB_NR",   "KCB Group",                    "Banking",                          "#fb923c"),
    ("KEGN_NR",  "KenGen",                       "Energy and Petroleum",             "#34d399"),
    ("KNRE_NR",  "Kenya Reinsurance",            "Insurance",                        "#f59e0b"),
    ("KPLC_NR",  "Kenya Power (Pref)",           "Energy and Petroleum",             "#60a5fa"),
    ("KQ_NR",    "Kenya Airways",               "Transport and Storage",             "#e879f9"),
    ("KUKZ_NR",  "Kakuzi",                       "Agricultural",                     "#4ade80"),
    ("LBTY_NR",  "Liberty Kenya Holdings",       "Insurance",                        "#fbbf24"),
    ("LKL_NR",   "Longhorn Publishers",          "Commercial and Services",          "#c084fc"),
    ("NBV_NR",   "Nairobi Business Ventures",    "Commercial and Services",          "#818cf8"),
    ("NCBA_NR",  "NCBA Group",                   "Banking",                          "#f87171"),
    ("NMG_NR",   "Nation Media Group",           "Media",                            "#2dd4bf"),
    ("NSE_NR",   "Nairobi Securities Exchange",  "Investment",                       "#facc15"),
    ("OCH_NR",   "Orchid Hotel",                 "Commercial and Services",          "#94a3b8"),
    ("PORT_NR",  "Kenya Ports Authority",        "Transport and Storage",            "#06b6d4"),
    ("SASN_NR",  "Sasini",                       "Agricultural",                     "#8b5cf6"),
    ("SBIC_NR",  "Stanbic Holdings",             "Banking",                          "#ec4899"),
    ("SCAN_NR",  "Scangroup",                    "Commercial and Services",          "#84cc16"),
    ("SCBK_NR",  "Standard Chartered Kenya",     "Banking",                          "#38bdf8"),
    ("SCOM_NR",  "Safaricom",                    "Telecommunication and Technology", "#a78bfa"),
    ("SGL_NR",   "Sanlam Kenya",                 "Insurance",                        "#f472b6"),
    ("SLAM_NR",  "Sameer Africa",                "Automobiles and Accessories",      "#fb923c"),
    ("SMER_NR",  "Stima Sacco",                  "Investment",                       "#34d399"),
    ("TOTL_NR",  "Total Energies Marketing",     "Energy and Petroleum",             "#f59e0b"),
    ("TPSE_NR",  "TPS Eastern Africa",           "Commercial and Services",          "#60a5fa"),
    ("UCHM_NR",  "Uchumi Supermarkets",          "Commercial and Services",          "#e879f9"),
    ("UMME_NR",  "Umeme",                        "Energy and Petroleum",             "#4ade80"),
    ("UNGA_NR",  "Unga Group",                   "Manufacturing and Allied",         "#fbbf24"),
    ("WTK_NR",   "Williamson Tea Kenya",         "Agricultural",                     "#c084fc"),
    ("XPRS_NR",  "Express Kenya",               "Transport and Storage",             "#818cf8"),
]


def get_db():
    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        sa_raw = os.environ["FIREBASE_SERVICE_ACCOUNT_JSON"]
        sa_dict = json.loads(sa_raw) if sa_raw.strip().startswith("{") else json.loads(open(sa_raw).read())
        cred = credentials.Certificate(sa_dict)
        firebase_admin.initialize_app(cred, {
            "storageBucket": os.environ["FIREBASE_STORAGE_BUCKET"]
        })
    return firestore.client()


def main():
    db = get_db()
    batch = db.batch()
    count = 0

    for ticker, name, sector, color in COMPANIES:
        short = ticker.split("_")[0]
        ref = db.collection("companies").document(ticker)
        batch.set(ref, {
            "ticker": ticker,
            "short": short,
            "name": name,
            "sector": sector,
            "color": color,
            "signal": "HOLD",
            "current_price": 0.0,
            "change_pct_today": 0.0,
            "price_preview": [],
            "last_updated": "never",
        }, merge=True)
        count += 1
        if count % 499 == 0:
            batch.commit()
            batch = db.batch()

    batch.commit()
    print(f"Seeded {count} companies to Firestore.")


if __name__ == "__main__":
    main()
