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

# (ticker, name, NSE sector, color) — verified against nse.co.ke/listed-companies/ (2026-07-28)
COMPANIES = [
    ("ABSA_NR",  "Absa Bank Kenya",              "Banking",                          "#38bdf8"),
    ("ALP_NR",   "ALP Industrial REIT",          "Real Estate Investment Trust",     "#f87171"),
    ("AMAC_NR",  "Africa Mega Agricorp",         "Manufacturing and Allied",         "#2dd4bf"),
    ("BAT_NR",   "BAT Kenya",                    "Manufacturing and Allied",          "#a78bfa"),
    ("BKG_NR",   "BK Group",                     "Banking",                          "#f472b6"),
    ("BOC_NR",   "BOC Kenya",                    "Manufacturing and Allied",         "#fb923c"),
    ("BRIT_NR",  "Britam Holdings",              "Insurance",                        "#34d399"),
    ("CARB_NR",  "Carbacid Investments",         "Manufacturing and Allied",         "#f59e0b"),
    ("CGEN_NR",  "Car and General (K)",          "Automobiles and Accessories",      "#60a5fa"),
    ("CIC_NR",   "CIC Insurance Group",          "Insurance",                        "#e879f9"),
    ("COOP_NR",  "Co-operative Bank",            "Banking",                          "#4ade80"),
    ("CRWN_NR",  "Crown Paints Kenya",           "Construction and Allied",          "#fbbf24"),
    ("CTUM_NR",  "Centum Investment",            "Investment",                       "#c084fc"),
    ("DTK_NR",   "Diamond Trust Bank",           "Banking",                          "#818cf8"),
    ("EABL_NR",  "East African Breweries",       "Manufacturing and Allied",         "#f87171"),
    ("EGAD_NR",  "Eaagads",                      "Agricultural",                     "#2dd4bf"),
    ("EQTY_NR",  "Equity Group Holdings",        "Banking",                          "#facc15"),
    ("EVRD_NR",  "Eveready East Africa",         "Manufacturing and Allied",         "#94a3b8"),
    ("FMLY_NR",  "Family Bank",                  "Banking",                          "#facc15"),
    ("FTGH_NR",  "Flame Tree Group Holdings",    "Manufacturing and Allied",         "#06b6d4"),
    ("GLD_NR",   "New Gold Issuer (ETF)",        "Exchange Traded Funds",            "#8b5cf6"),
    ("HAFR_NR",  "Home Afrika",                  "Investment",                       "#ec4899"),
    ("HFCK_NR",  "HF Group",                     "Banking",                          "#84cc16"),
    ("IMH_NR",   "I&M Holdings",                 "Banking",                          "#38bdf8"),
    ("JUB_NR",   "Jubilee Holdings",             "Insurance",                        "#a78bfa"),
    ("KAPC_NR",  "Kapchorua Tea",                "Agricultural",                     "#f472b6"),
    ("KCB_NR",   "KCB Group",                    "Banking",                          "#fb923c"),
    ("KEGN_NR",  "KenGen",                       "Energy and Petroleum",             "#34d399"),
    ("KNRE_NR",  "Kenya Reinsurance",            "Insurance",                        "#f59e0b"),
    ("KPC_NR",   "Kenya Pipeline Company",       "Energy and Petroleum",             "#94a3b8"),
    ("KPLC_NR",  "Kenya Power & Lighting",       "Energy and Petroleum",             "#60a5fa"),
    ("KQ_NR",    "Kenya Airways",               "Commercial and Services",           "#e879f9"),
    ("KUKZ_NR",  "Kakuzi",                       "Agricultural",                     "#4ade80"),
    ("KURV_NR",  "Kurwitu Ventures",             "Investment",                       "#06b6d4"),
    ("LBTY_NR",  "Liberty Kenya Holdings",       "Insurance",                        "#fbbf24"),
    ("LIMT_NR",  "Limuru Tea",                   "Agricultural",                     "#8b5cf6"),
    ("LKL_NR",   "Longhorn Publishers",          "Commercial and Services",          "#c084fc"),
    ("NBV_NR",   "Nairobi Business Ventures",    "Commercial and Services",          "#818cf8"),
    ("NCBA_NR",  "NCBA Group",                   "Banking",                          "#f87171"),
    ("NMG_NR",   "Nation Media Group",           "Commercial and Services",          "#2dd4bf"),
    ("NSE_NR",   "Nairobi Securities Exchange",  "Investment Services",              "#facc15"),
    ("OCH_NR",   "Olympia Capital Holdings",     "Investment",                       "#94a3b8"),
    ("PORT_NR",  "East African Portland Cement", "Construction and Allied",          "#06b6d4"),
    ("SASN_NR",  "Sasini",                       "Agricultural",                     "#8b5cf6"),
    ("SBIC_NR",  "Stanbic Holdings",             "Banking",                          "#ec4899"),
    ("SCAN_NR",  "Scangroup",                    "Commercial and Services",          "#84cc16"),
    ("SCBK_NR",  "Standard Chartered Bank Kenya","Banking",                          "#38bdf8"),
    ("SCOM_NR",  "Safaricom",                    "Telecommunication and Technology", "#a78bfa"),
    ("SGL_NR",   "Standard Group",               "Commercial and Services",          "#f472b6"),
    ("SHKL_NR",  "Shri Krishana Overseas",       "Manufacturing and Allied",         "#ec4899"),
    ("SLAM_NR",  "Sanlam Allianz Holdings",      "Insurance",                        "#fb923c"),
    ("SMER_NR",  "Sameer Africa",               "Commercial and Services",           "#34d399"),
    ("SMWF_NR",  "Satrix MSCI World Feeder ETF", "Exchange Traded Funds",            "#84cc16"),
    ("TOTL_NR",  "Total Kenya",                  "Energy and Petroleum",             "#f59e0b"),
    ("TPSE_NR",  "TPS Eastern Africa (Serena)",  "Commercial and Services",          "#60a5fa"),
    ("TRFC_NR",  "TRIFIC Green USD I-REIT",      "Real Estate Investment Trust",     "#38bdf8"),
    ("UCHM_NR",  "Uchumi Supermarket",           "Commercial and Services",          "#e879f9"),
    ("UMME_NR",  "Umeme",                        "Energy and Petroleum",             "#4ade80"),
    ("UNGA_NR",  "Unga Group",                   "Manufacturing and Allied",         "#fbbf24"),
    ("WTK_NR",   "Williamson Tea Kenya",         "Agricultural",                     "#c084fc"),
    ("XPRS_NR",  "Express Kenya",               "Commercial and Services",           "#818cf8"),
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
