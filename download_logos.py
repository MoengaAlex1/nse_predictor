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
    "ABSA_NR":  "absa.co.ke",
    "ALP_NR":   "africawarehouses.com",
    "AMAC_NR":  "amacplc.com",
    "BAT_NR":   "bat.com",
    "BKG_NR":   "bkgroup.rw",
    "BOC_NR":   "boc.co.ke",
    "BRIT_NR":  "britam.com",
    "CARB_NR":  "carbacid.com",
    "CGEN_NR":  "cargen.com",
    "CIC_NR":   "cicinsurancegroup.com",
    "COOP_NR":  "co-opbank.co.ke",
    "CRWN_NR":  "crownpaints.co.ke",
    "CTUM_NR":  "centum.co.ke",
    "DTK_NR":   "dtbafrica.com",
    "EABL_NR":  "eabl.com",
    "EGAD_NR":  "eapcc.co.ke",
    "EQTY_NR":  "equitygroupholdings.com",
    "EVRD_NR":  "eveready.co.ke",
    "FMLY_NR":  "familybank.co.ke",
    "FTGH_NR":  "stanlib.com",
    "GLD_NR":   None,
    "HAFR_NR":  "homeafrika.com",
    "HFCK_NR":  "hfgroup.co.ke",
    "IMH_NR":   "imhkenya.com",
    "JUB_NR":   "jubileeholdings.co.ke",
    "KAPC_NR":  "williamsontea.com",
    "KCB_NR":   "kcbgroup.com",
    "KEGN_NR":  "kengen.co.ke",
    "KNRE_NR":  "kenyare.co.ke",
    "KPC_NR":   "kpc.co.ke",
    "KPLC_NR":  "kplc.co.ke",
    "KQ_NR":    "kenya-airways.com",
    "KUKZ_NR":  "kakuzi.co.ke",
    "KURV_NR":  "kurwituventures.com",
    "LBTY_NR":  "libertykenya.co.ke",
    "LIMT_NR":  "limuruteaplc.com",
    "LKL_NR":   "longhornpublishers.com",
    "NBV_NR":   "national-bank.co.ke",
    "NCBA_NR":  "ncbagroup.com",
    "NMG_NR":   "nationmedia.com",
    "NSE_NR":   "nse.co.ke",
    "OCH_NR":   "ochl.co.ke",
    "PORT_NR":  "reavipingo.com",
    "SASN_NR":  "sasini.co.ke",
    "SBIC_NR":  "stanbicbank.co.ke",
    "SCAN_NR":  "wpp-scangroup.com",
    "SCBK_NR":  "sc.com",
    "SCOM_NR":  "safaricom.co.ke",
    "SGL_NR":   "flametreegroup.com",
    "SKL_NR":   "sanlam.co.ke",
    "SLAM_NR":  "sanlam.co.ke",
    "SMER_NR":  "sameerafrica.com",
    "SMWF_NR":  "satrix.co.za",
    "TOTL_NR":  "totalenergies.co.ke",
    "TPSE_NR":  "serenahotels.com",
    "TRFC_NR":  "transcentury.co.ke",
    "UCHM_NR":  "uchumi.com",
    "UMME_NR":  "umeme.co.ug",
    "UNGA_NR":  "unga-group.com",
    "WTK_NR":   "williamsontea.com",
    "XPRS_NR":  "expresskenya.co.ke",
}

# Fallback domains to try when the primary fails
FALLBACK_DOMAINS = {
    "ABSA_NR":  ["absa.africa", "absakenya.co.ke"],
    "BOC_NR":   ["linde.com", "boc.com"],
    "COOP_NR":  ["co-opbank.co.ke", "cooperative-bank.co.ke"],
    "EGAD_NR":  ["lafarge.co.ke", "holcim.com"],
    "EQTY_NR":  ["equitybank.co.ke"],
    "FMLY_NR":  ["familybank.co.ke"],
    "FTGH_NR":  ["fahari.co.ke", "stanlib.co.ke"],
    "HFCK_NR":  ["hf-kenya.com"],
    "IMH_NR":   ["imbank.co.ke", "im-bank.com"],
    "JUB_NR":   ["jubilee-insurance.com"],
    "KPLC_NR":  ["kplc.co.ke"],
    "KQ_NR":    ["kq.com"],
    "NCBA_NR":  ["ncba.co.ke"],
    "SBIC_NR":  ["standardbank.co.za"],
    "SCAN_NR":  ["scangroup.co.ke"],
    "SCBK_NR":  ["standardchartered.com", "sc.com/en"],
    "SCOM_NR":  ["safaricom.co.ke"],
    "TPSE_NR":  ["tpsea.com"],
    "TOTL_NR":  ["totalenergies.com", "total.co.ke"],
    "UNGA_NR":  ["ungagroup.com"],
    "UCHM_NR":  ["uchumisupermarkets.co.ke"],
    "NBV_NR":   ["nbvplc.com"],
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
