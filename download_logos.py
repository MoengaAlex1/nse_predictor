"""
download_logos.py

Downloads company logos from Clearbit Logo API and saves to
frontend/public/logos/{safe_ticker}.png

Run from repo root:
  python download_logos.py
"""
import time
import requests
from pathlib import Path

LOGOS_DIR = Path("frontend/public/logos")
LOGOS_DIR.mkdir(parents=True, exist_ok=True)

DOMAIN_MAP = {
    "ABSA":  "absa.co.ke",
    "ALP":   "africawarehouses.com",
    "AMAC":  "amacplc.com",
    "BAT":   "bat.com",
    "BKG":   "bkgroup.rw",
    "BOC":   "boc.co.ke",
    "BRIT":  "britam.com",
    "CARB":  "carbacid.com",
    "CGEN":  "cargen.com",
    "CIC":   "cicinsurancegroup.com",
    "COOP":  "co-opbank.co.ke",
    "CRWN":  "crownpaints.co.ke",
    "CTUM":  "centum.co.ke",
    "DTK":   "dtbafrica.com",
    "EABL":  "eabl.com",
    "EGAD":  "eaagads.co.ke",
    "EQTY":  "equitygroupholdings.com",
    "EVRD":  "eveready.co.ke",
    "FMLY":  "familybank.co.ke",
    "FTGH":  "flametreegroup.com",
    "GLD":   None,
    "HAFR":  "homeafrika.com",
    "HFCK":  "hfgroup.co.ke",
    "IMH":   "imhkenya.com",
    "JUB":   "jubileeholdings.co.ke",
    "KAPC":  None,
    "KCB":   "kcbgroup.com",
    "KEGN":  "kengen.co.ke",
    "KNRE":  "kenyare.co.ke",
    "KPC":   "kpc.co.ke",
    "KPLC":  "kplc.co.ke",
    "KQ":    "kenya-airways.com",
    "KUKZ":  "kakuzi.co.ke",
    "KURV":  "kurwituventures.com",
    "LBTY":  "libertykenya.co.ke",
    "LIMT":  "limuruteaplc.com",
    "LKL":   "longhornpublishers.com",
    "NBV":   "nbvplc.com",
    "NCBA":  "ncbagroup.com",
    "NMG":   "nationmedia.com",
    "NSE":   "nse.co.ke",
    "OCH":   "ochl.co.ke",
    "PORT":  "eapcc.co.ke",
    "SASN":  "sasini.co.ke",
    "SBIC":  "stanbicbank.co.ke",
    "SCAN":  "wpp-scangroup.com",
    "SCBK":  "sc.com",
    "SCOM":  "safaricom.co.ke",
    "SGL":   "standardmedia.co.ke",
    "SHKL":  "shrikrishnaoverseas.com",
    "SLAM":  "sanlam.co.ke",
    "SMER":  "sameerafrica.com",
    "SMWF":  "satrix.co.za",
    "TOTL":  "totalenergies.co.ke",
    "TPSE":  "serenahotels.com",
    "TRFC":  "trific.co.ke",
    "UCHM":  "uchumi.com",
    "UMME":  "umeme.co.ug",
    "UNGA":  "unga-group.com",
    "WTK":   "williamsontea.com",
    "XPRS":  "expresskenya.co.ke",
}

# Fallback domains to try when the primary fails
FALLBACK_DOMAINS = {
    "ABSA":  ["absa.africa", "absakenya.co.ke"],
    "BOC":   ["linde.com", "boc.com"],
    "COOP":  ["co-opbank.co.ke", "cooperative-bank.co.ke"],
    "EQTY":  ["equitybank.co.ke"],
    "FMLY":  ["familybank.co.ke"],
    "HFCK":  ["hf-kenya.com"],
    "IMH":   ["imbank.co.ke", "im-bank.com"],
    "JUB":   ["jubilee-insurance.com"],
    "KPLC":  ["kplc.co.ke"],
    "KQ":    ["kq.com"],
    "NCBA":  ["ncba.co.ke"],
    "PORT":  ["lafarge.co.ke", "holcim.com"],
    "SBIC":  ["standardbank.co.za"],
    "SCAN":  ["scangroup.co.ke"],
    "SCBK":  ["standardchartered.com", "sc.com/en"],
    "SCOM":  ["safaricom.co.ke"],
    "SGL":   ["standardmedia.co.ke"],
    "TPSE":  ["tpsea.com"],
    "TOTL":  ["totalenergies.com", "total.co.ke"],
    "UNGA":  ["ungagroup.com"],
    "UCHM":  ["uchumisupermarkets.co.ke"],
}

session = requests.Session()
session.headers["User-Agent"] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/125 Safari/537.36"
)


def try_clearbit(domain: str) -> bytes | None:
    url = f"https://logo.clearbit.com/{domain}"
    try:
        r = session.get(url, timeout=10)
        if r.status_code == 200 and len(r.content) > 500:
            return r.content
    except Exception:
        pass
    return None


def download_logo(ticker: str, domain: str | None) -> bool:
    dest = LOGOS_DIR / f"{ticker}.png"
    if dest.exists() and dest.stat().st_size > 500:
        print(f"  {ticker:<12} -- already exists, skipping")
        return True

    if domain is None:
        print(f"  {ticker:<12} -- no domain (will use emoji fallback)")
        return False

    # Try primary domain
    data = try_clearbit(domain)
    if data:
        dest.write_bytes(data)
        print(f"  {ticker:<12} OK  {domain}")
        return True

    # Try fallbacks
    for fallback in FALLBACK_DOMAINS.get(ticker, []):
        data = try_clearbit(fallback)
        if data:
            dest.write_bytes(data)
            print(f"  {ticker:<12} OK  {fallback} (fallback)")
            return True

    # Try Google favicon as last resort (higher quality than expected)
    try:
        gurl = f"https://www.google.com/s2/favicons?domain={domain}&sz=128"
        r = session.get(gurl, timeout=10)
        if r.status_code == 200 and len(r.content) > 200:
            dest.write_bytes(r.content)
            print(f"  {ticker:<12} ~   favicon from {domain}")
            return True
    except Exception:
        pass

    print(f"  {ticker:<12} --  failed for {domain}")
    return False


ok = failed = 0
for ticker, domain in DOMAIN_MAP.items():
    success = download_logo(ticker, domain)
    if success:
        ok += 1
    else:
        failed += 1
    time.sleep(0.3)  # be polite to Clearbit

print(f"\nDone: {ok} logos downloaded, {failed} missing (will use emoji).")
print(f"Logos saved to: {LOGOS_DIR.resolve()}")
