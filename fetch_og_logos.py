"""Fetch company logos from og:image meta tags on official websites."""
import re
import time
import requests
from pathlib import Path
from urllib.parse import urljoin

LOGOS_DIR = Path("frontend/public/logos")
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
})

TARGETS = {
    "KCB_NR":   "https://kcbgroup.com",
    "ABSA_NR":  "https://www.absa.co.ke",
    "BRIT_NR":  "https://www.britam.com",
    "JUB_NR":   "https://www.jubileeholdings.co.ke",
    "NCBA_NR":  "https://www.ncbagroup.com",
    "NMG_NR":   "https://www.nationmedia.com",
    "TOTL_NR":  "https://www.totalenergies.co.ke",
    "SBIC_NR":  "https://www.stanbicbank.co.ke",
    "TPSE_NR":  "https://www.serenahotels.com",
    "HFCK_NR":  "https://www.hfgroup.co.ke",
    "IMH_NR":   "https://www.imbank.co.ke",
    "EVRD_NR":  "https://www.eveready.co.ke",
    "BOC_NR":   "https://www.boc.co.ke",
    "EGAD_NR":  "https://www.eapcc.co.ke",
    "TRFC_NR":  "https://www.transcentury.co.ke",
    "UCHM_NR":  "https://www.uchumi.com",
    "NBV_NR":   "https://www.nbvplc.com",
    "ALP_NR":   "https://africawarehouses.com",
}

OG_PAT = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']'
    r'|<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
    re.I
)


def get_og_image(url: str) -> str | None:
    try:
        r = session.get(url, timeout=12, allow_redirects=True)
        m = OG_PAT.search(r.text)
        if m:
            return m.group(1) or m.group(2)
    except Exception as e:
        print(f"    fetch error: {e}")
    return None


for ticker, base_url in TARGETS.items():
    dest = LOGOS_DIR / f"{ticker}.png"
    if dest.exists() and dest.stat().st_size > 500:
        print(f"  {ticker:<12} already exists")
        continue

    og = get_og_image(base_url)
    if og:
        if not og.startswith("http"):
            og = urljoin(base_url, og)
        try:
            ir = session.get(og, timeout=12)
            if ir.status_code == 200 and len(ir.content) > 500:
                dest.write_bytes(ir.content)
                print(f"  {ticker:<12} OK  {og[:70]}")
                time.sleep(0.3)
                continue
        except Exception:
            pass
    print(f"  {ticker:<12} --  no usable og:image from {base_url}")
    time.sleep(0.3)

print("\nDone.")
