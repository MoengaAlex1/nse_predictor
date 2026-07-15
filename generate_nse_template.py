"""
generate_nse_template.py
------------------------
Generates blank NSE archive CSV template files for years not yet in the archive.

Usage:
    python generate_nse_template.py              # fills 2000-2006 (pre-existing archive)
    python generate_nse_template.py --start 1990 # fill from an earlier year
    python generate_nse_template.py --list       # show which years are missing

Each output file:
    C:/Users/moeng/Downloads/archive/NSE_data_all_stocks_YYYY.csv

Column order matches the NSE daily pricing sheet exactly:
    Date, Code, Name, 12m Low, 12m High, Day Low, Day High,
    Day Price, Previous, Change, Change%, Volume, Adjusted Price

How to fill in the data
-----------------------
1. Open the generated CSV in Excel.
2. Each row represents ONE company on ONE trading day.
3. Fill in real prices using NSE historical records, newspaper archives,
   or any other reliable source.
4. Save as CSV (UTF-8) with the same filename — do NOT rename.
5. The Data Explorer tab will automatically pick up the file on next load.

Date format: use DD/MM/YYYY (e.g. 15/07/2003) or M/D/YYYY (e.g. 7/15/2003).
             Both are accepted by the loader.

Prediction pipeline compatibility
----------------------------------
The LSTM/XGBoost/ARIMA models consume the 'Close' price mapped from 'Day Price'.
30 years of data (2000-2026) will substantially improve long-range forecasts.
Minimum recommended data per company: 252 trading days (~1 year).
"""

import argparse
import csv
from pathlib import Path

ARCHIVE_DIR = Path(r"C:\Users\moeng\Downloads\archive")

NSE_COLS = [
    "Date", "Code", "Name",
    "12m Low", "12m High",
    "Day Low", "Day High", "Day Price",
    "Previous", "Change", "Change%",
    "Volume", "Adjusted Price",
]

ALL_NSE_CODES = [
    ("ABSA",  "ABSA Bank Kenya Plc"),
    ("ALP",   "Alpharama Ltd"),
    ("AMAC",  "Athi River Mining Cement"),
    ("BAT",   "British American Tobacco Kenya Plc"),
    ("BKG",   "BK Group Plc"),
    ("BOC",   "BOC Kenya Plc"),
    ("BRIT",  "Britam Holdings Plc"),
    ("CARB",  "Carbacid Investments Plc"),
    ("CGEN",  "Centum Generation Ltd"),
    ("CIC",   "CIC Insurance Group Plc"),
    ("COOP",  "Co-operative Bank of Kenya Ltd"),
    ("CRWN",  "Crown Paints Kenya Plc"),
    ("CTUM",  "Cavendish Mgt Plc"),
    ("DTK",   "Diamond Trust Bank Kenya Ltd"),
    ("EABL",  "East African Breweries Ltd"),
    ("EGAD",  "East African Portland Cement Co Ltd"),
    ("EQTY",  "Equity Group Holdings Plc"),
    ("EVRD",  "Eveready East Africa Plc"),
    ("FMLY",  "Family Bank Ltd"),
    ("FTGH",  "Fahari I-REIT"),
    ("GLD",   "Gold Coin Kenya Ltd"),
    ("HAFR",  "Home Afrika Ltd"),
    ("HFCK",  "HF Group Plc"),
    ("IMH",   "I&M Holdings Plc"),
    ("JUB",   "Jubilee Holdings Ltd"),
    ("KAPC",  "KAPS Medical International Ltd"),
    ("KCB",   "KCB Group Plc"),
    ("KEGN",  "KenGen Co Ltd"),
    ("KNRE",  "Kenya Reinsurance Corporation Ltd"),
    ("KPC",   "Kenya Power and Lighting Co Ltd"),
    ("KPLC",  "Kenya Power and Lighting Co Ltd Pref"),
    ("KQ",    "Kenya Airways Ltd"),
    ("KUKZ",  "Kakuzi Plc"),
    ("KURV",  "Kurwitu Ventures Ltd"),
    ("LBTY",  "Liberty Kenya Holdings Ltd"),
    ("LIMT",  "Limuru Tea Co Ltd"),
    ("LKL",   "Longhorn Publishers Plc"),
    ("NBV",   "Nairobi Business Ventures Ltd"),
    ("NCBA",  "NCBA Group Plc"),
    ("NMG",   "Nation Media Group Plc"),
    ("NSE",   "Nairobi Securities Exchange Plc"),
    ("OCH",   "Olympia Capital Holdings Ltd"),
    ("PORT",  "East African Portland Cement Co"),
    ("SASN",  "Sasini Ltd"),
    ("SBIC",  "SBM Holdings Kenya Ltd"),
    ("SCAN",  "Scangroup Plc"),
    ("SCBK",  "Standard Chartered Bank Kenya Ltd"),
    ("SCOM",  "Safaricom Plc"),
    ("SGL",   "Standard Group Plc"),
    ("SKL",   "Stanbic Kenya Ltd"),
    ("SLAM",  "Sanlam Kenya Plc"),
    ("SMER",  "Sameer Africa Plc"),
    ("SMWF",  "Stanlib Fahari REIT"),
    ("TOTL",  "TotalEnergies EP Kenya Ltd"),
    ("TPSE",  "TransCentury Plc"),
    ("TRFC",  "TransAfrica Radio and Communications"),
    ("UCHM",  "Unga Group Plc"),
    ("UMME",  "Umeme Ltd"),
    ("UNGA",  "Unga Group Plc"),
    ("WTK",   "Williamson Tea Kenya Ltd"),
    ("XPRS",  "Express Kenya Ltd"),
]


def existing_years():
    return {
        int(p.stem.split("_")[-1])
        for p in ARCHIVE_DIR.glob("NSE_data_all_stocks_????.csv")
        if p.stem.split("_")[-1].isdigit()
    }


def generate_template(year: int, overwrite: bool = False) -> Path:
    path = ARCHIVE_DIR / f"NSE_data_all_stocks_{year}.csv"
    if path.exists() and not overwrite:
        print(f"  SKIP  {path.name}  (already exists — use --overwrite to replace)")
        return path

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(NSE_COLS)
        # One placeholder row per company so users know the expected format
        writer.writerow([
            f"01/01/{year}", "CODE", "Company Name",
            "", "", "", "", "", "", "", "", "", "",
        ])
        for code, name in ALL_NSE_CODES:
            writer.writerow([
                f"01/01/{year}", code, name,
                "", "", "", "", "", "", "", "", "", "",
            ])

    print(f"  WROTE {path.name}  ({len(ALL_NSE_CODES) + 1} template rows)")
    return path


def main():
    parser = argparse.ArgumentParser(description="Generate blank NSE CSV templates.")
    parser.add_argument("--start", type=int, default=2000,
                        help="First year to generate (default: 2000)")
    parser.add_argument("--end", type=int, default=2006,
                        help="Last year to generate (default: 2006)")
    parser.add_argument("--overwrite", action="store_true",
                        help="Overwrite existing files")
    parser.add_argument("--list", action="store_true",
                        help="List years present and missing, then exit")
    args = parser.parse_args()

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    if args.list:
        present = existing_years()
        all_years = set(range(args.start, 2027))
        missing = sorted(all_years - present)
        print(f"Archive: {ARCHIVE_DIR}")
        print(f"Present years: {sorted(present)}")
        print(f"Missing years ({args.start}–2026): {missing}")
        return

    print(f"Generating templates for {args.start}–{args.end} in:")
    print(f"  {ARCHIVE_DIR}\n")

    for year in range(args.start, args.end + 1):
        generate_template(year, overwrite=args.overwrite)

    print(f"\nDone. Open the CSV files in Excel, fill in real prices, and save.")
    print("The Data Explorer will load them automatically on next query.")


if __name__ == "__main__":
    main()
