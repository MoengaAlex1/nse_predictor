"""
download_wiki_logos.py

Downloads high-quality company logos from Wikipedia/Wikimedia and official
websites, converts everything to PNG, saves to frontend/public/logos/.

Run from repo root:  python download_wiki_logos.py
"""
import io
import time
import requests
from pathlib import Path

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("WARNING: Pillow not installed — will save raw bytes (may not be proper PNG).")
    print("Run: pip install Pillow")

LOGOS_DIR = Path("frontend/public/logos")
LOGOS_DIR.mkdir(parents=True, exist_ok=True)

LOGO_URLS = {
    # ── Wikipedia / Wikimedia Commons (already PNG or SVG→PNG thumbnails) ──────
    "ABSA_NR":  "https://upload.wikimedia.org/wikipedia/commons/thumb/d/de/ABSA_Group_Limited_Logo.svg/400px-ABSA_Group_Limited_Logo.svg.png",
    "KCB_NR":   "https://upload.wikimedia.org/wikipedia/en/d/de/KCB_Bank_Kenya_Limited_logo.png",
    "JUB_NR":   "https://upload.wikimedia.org/wikipedia/en/d/d3/Jubilee_Insurance_Company_Limited_logo.png",
    "NCBA_NR":  "https://upload.wikimedia.org/wikipedia/commons/a/a0/NCBA_LOGO_2.jpg",
    "EABL_NR":  "https://upload.wikimedia.org/wikipedia/commons/1/1b/East_African_Breweries_EABL_2022_Logo.png",
    "EQTY_NR":  "https://upload.wikimedia.org/wikipedia/commons/1/15/Equity_Group_Logo.png",
    "SCOM_NR":  "https://upload.wikimedia.org/wikipedia/en/thumb/e/eb/Safaricom_logo.svg/400px-Safaricom_logo.svg.png",
    "KQ_NR":    "https://upload.wikimedia.org/wikipedia/commons/thumb/7/75/Kenya_Airways_Logo.svg/400px-Kenya_Airways_Logo.svg.png",
    "TOTL_NR":  "https://upload.wikimedia.org/wikipedia/en/thumb/5/54/TotalEnergies_logo.svg/400px-TotalEnergies_logo.svg.png",
    "CARB_NR":  "https://upload.wikimedia.org/wikipedia/en/c/ce/Carbacid_Investments_Limited_Logo.png",
    "IMH_NR":   "https://upload.wikimedia.org/wikipedia/commons/c/c7/Imbank-logo.webp",
    "KPLC_NR":  "https://upload.wikimedia.org/wikipedia/en/3/36/Kenya_Power_logo.jpeg",
    "KEGN_NR":  "https://upload.wikimedia.org/wikipedia/en/1/12/Kenya_Electricity_Generating_Company_logo.png",
    "COOP_NR":  "https://upload.wikimedia.org/wikipedia/commons/d/d7/Coopbanklogo.jpg",
    "SCBK_NR":  "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0c/Standard_Chartered_%282021%29.svg/400px-Standard_Chartered_%282021%29.svg.png",
    "BAT_NR":   "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b0/Bat_logo20.svg/400px-Bat_logo20.svg.png",
    "BOC_NR":   "https://upload.wikimedia.org/wikipedia/commons/6/6f/Linde_plc_logo.png",
    "EVRD_NR":  "https://upload.wikimedia.org/wikipedia/commons/3/3e/Eveready_east_africa_ltd_logo.png",
    "SBIC_NR":  "https://upload.wikimedia.org/wikipedia/en/3/38/CfC_Stanbic_Holdings_Logo.png",
    "UCHM_NR":  "https://upload.wikimedia.org/wikipedia/commons/e/e0/Logo-Uchumi.png",
    "DTK_NR":   "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e5/Diamond_Trust_Bank_Kenya_logo.svg/400px-Diamond_Trust_Bank_Kenya_logo.svg.png",
    # ── Official websites ────────────────────────────────────────────────────────
    "BRIT_NR":  "https://www.britam.com/templates/cassiopeia/images/logo.png",
    "NMG_NR":   "https://upload.wikimedia.org/wikipedia/en/thumb/8/8f/Nation_Media_Group_Logo.svg/400px-Nation_Media_Group_Logo.svg.png",
    "HFCK_NR":  "https://upload.wikimedia.org/wikipedia/en/a/a5/HF_Group_Logo.png",
    # ── Extra quality upgrades for companies already in logos/ ──────────────────
    "LIMT_NR":  "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f9/Unilever_logo.svg/400px-Unilever_logo.svg.png",
}

session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (compatible; NSE-logo-downloader/1.0; "
        "+https://github.com/MoengaAlex1/nse_predictor)"
    ),
    "Referer": "https://en.wikipedia.org/",
})


def save_as_png(raw: bytes, dest: Path) -> bool:
    if not HAS_PIL:
        dest.write_bytes(raw)
        return True
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGBA")
        img.save(dest, "PNG", optimize=True)
        return True
    except Exception as e:
        print(f"    PIL convert failed ({e}), saving raw bytes")
        dest.write_bytes(raw)
        return True


ok = skipped = failed = 0

for ticker, url in LOGO_URLS.items():
    dest = LOGOS_DIR / f"{ticker}.png"

    try:
        r = session.get(url, timeout=20, allow_redirects=True)
        if r.status_code != 200:
            print(f"  {ticker:<12} HTTP {r.status_code}  {url[:70]}")
            failed += 1
            continue

        content = r.content
        if len(content) < 500:
            print(f"  {ticker:<12} too small ({len(content)}b)  {url[:70]}")
            failed += 1
            continue

        # Check for SVG (we can't display SVG-saved-as-.png without conversion)
        if content.lstrip()[:5] in (b"<?xml", b"<svg "):
            print(f"  {ticker:<12} SVG but no converter — skipping  {url[:70]}")
            failed += 1
            continue

        save_as_png(content, dest)
        size_kb = dest.stat().st_size / 1024
        print(f"  {ticker:<12} OK  {size_kb:.1f} KB  {url[:60]}")
        ok += 1

    except Exception as e:
        print(f"  {ticker:<12} ERROR: {e}")
        failed += 1

    time.sleep(0.4)

print(f"\nDone: {ok} downloaded, {skipped} skipped, {failed} failed.")
