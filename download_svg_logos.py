"""
download_svg_logos.py

Downloads SVG logos from Wikimedia for companies that returned 400 on thumbnail URLs.
Uses the Wikimedia REST API to fetch proper thumbnail URLs.
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

LOGOS_DIR = Path("frontend/public/logos")

# Map ticker → Wikimedia Commons filename (exact case matters)
WIKI_SVG_FILES = {
    "ABSA_NR":  ("commons", "ABSA_Group_Limited_Logo.svg"),
    "SCOM_NR":  ("en",      "Safaricom_logo.svg"),
    "KQ_NR":    ("commons", "Kenya_Airways_Logo.svg"),
    "TOTL_NR":  ("en",      "TotalEnergies_logo.svg"),
    "SCBK_NR":  ("commons", "Standard_Chartered_(2021).svg"),
    "BAT_NR":   ("commons", "Bat_logo20.svg"),
    "DTK_NR":   ("commons", "Diamond_Trust_Bank_Kenya_logo.svg"),
    "NMG_NR":   ("en",      "Nation_Media_Group_Logo.svg"),
    "LIMT_NR":  ("commons", "Unilever.svg"),
}

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept": "image/png,image/*,*/*",
})


def get_wikimedia_thumbnail(wiki: str, filename: str, width: int = 400) -> bytes | None:
    """Use Wikimedia REST API to get a rendered thumbnail of an SVG."""
    # REST API endpoint
    api_url = f"https://api.wikimedia.org/core/v1/{'commons' if wiki == 'commons' else 'wikipedia/en'}/file/{filename}"
    try:
        r = session.get(api_url, timeout=15)
        if r.status_code == 200:
            data = r.json()
            # preferred_rendering has the right thumbnail
            rendering = data.get("preferred", {})
            url = rendering.get("url") or data.get("file_description_url")
            # Try to get a width-specific thumbnail
            thumbs = data.get("thumbnails", [])
            if thumbs:
                # Pick the largest available thumbnail
                best = max(thumbs, key=lambda t: t.get("width", 0))
                url = best.get("url", url)
            if url:
                ir = session.get(url, timeout=15)
                if ir.status_code == 200 and len(ir.content) > 500:
                    return ir.content
    except Exception as e:
        print(f"    REST API error: {e}")
    return None


def get_wikimedia_action_api(wiki: str, filename: str, width: int = 400) -> bytes | None:
    """Use the MediaWiki action API to get thumb URL."""
    base = "https://commons.wikimedia.org" if wiki == "commons" else "https://en.wikipedia.org"
    api_url = (
        f"{base}/w/api.php?action=query&titles=File:{filename}"
        f"&prop=imageinfo&iiprop=url&iiurlwidth={width}&format=json"
    )
    try:
        r = session.get(api_url, timeout=15)
        if r.status_code == 200:
            pages = r.json().get("query", {}).get("pages", {})
            for page in pages.values():
                info = page.get("imageinfo", [{}])[0]
                thumb_url = info.get("thumburl") or info.get("url")
                if thumb_url:
                    ir = session.get(thumb_url, timeout=15, headers={"Referer": base})
                    if ir.status_code == 200 and len(ir.content) > 500:
                        return ir.content
    except Exception as e:
        print(f"    Action API error: {e}")
    return None


def save_png(raw: bytes, dest: Path) -> None:
    if HAS_PIL:
        try:
            img = Image.open(io.BytesIO(raw)).convert("RGBA")
            img.save(dest, "PNG", optimize=True)
            return
        except Exception:
            pass
    dest.write_bytes(raw)


ok = failed = 0
for ticker, (wiki, filename) in WIKI_SVG_FILES.items():
    dest = LOGOS_DIR / f"{ticker}.png"

    # Try REST API first, then action API
    raw = get_wikimedia_thumbnail(wiki, filename) or get_wikimedia_action_api(wiki, filename)

    if raw:
        save_png(raw, dest)
        print(f"  {ticker:<12} OK  {dest.stat().st_size / 1024:.1f} KB  ({filename})")
        ok += 1
    else:
        print(f"  {ticker:<12} FAILED  ({filename})")
        failed += 1

    time.sleep(0.5)

print(f"\nDone: {ok} OK, {failed} failed.")
