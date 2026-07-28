"""
finalize_logos.py

1. Fetch remaining missing logos (DTK, NMG, HFCK, BRIT fallback)
2. Resize any logo > 200KB to max 400px wide (keeps file sizes web-friendly)
3. Report final state of logos/
"""
import io
import time
import requests
from pathlib import Path
from PIL import Image

LOGOS_DIR = Path("frontend/public/logos")
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept": "image/*,*/*",
})


def fetch(url: str) -> bytes | None:
    try:
        r = session.get(url, timeout=15, allow_redirects=True)
        if r.status_code == 200 and len(r.content) > 500:
            return r.content
    except Exception as e:
        print(f"    fetch error: {e}")
    return None


def save_png(raw: bytes, dest: Path, max_w: int = 400) -> None:
    img = Image.open(io.BytesIO(raw)).convert("RGBA")
    if img.width > max_w:
        ratio = max_w / img.width
        img = img.resize((max_w, int(img.height * ratio)), Image.LANCZOS)
    img.save(dest, "PNG", optimize=True)


# ── 1. Fetch remaining missing logos ─────────────────────────────────────────
REMAINING = {
    # Diamond Trust Bank — try their own site
    "DTK_NR": [
        "https://dtbafrica.com/wp-content/uploads/2023/01/dtb-logo.png",
        "https://www.dtbafrica.com/wp-content/themes/dtb/images/logo.png",
        "https://upload.wikimedia.org/wikipedia/commons/a/a9/Diamond_Trust_Bank.png",
    ],
    # Nation Media Group
    "NMG_NR": [
        "https://www.nationmedia.com/wp-content/themes/nmg2024/images/nmg-logo.png",
        "https://www.nationmedia.com/wp-content/uploads/2016/09/nmg-logo.png",
        "https://nation.africa/resource/image/1354406/landscape_ratio3x2/800/533/bab74a04c32ac79da2d10d1cda50d3bc/HK/nation-africa-logo.png",
    ],
    # HF Group Kenya
    "HFCK_NR": [
        "https://www.hfgroup.co.ke/wp-content/uploads/2022/03/hf-group-logo.png",
        "https://hfgroup.co.ke/wp-content/themes/hfgroup/images/logo.png",
        "https://upload.wikimedia.org/wikipedia/commons/2/28/HF_Group_Logo.png",
    ],
    # Britam — try higher quality
    "BRIT_NR": [
        "https://www.britam.com/images/logo.png",
        "https://britam.com/wp-content/uploads/2022/britam-logo.png",
        "https://upload.wikimedia.org/wikipedia/commons/d/d0/Britam_Holdings_Logo.png",
    ],
}

for ticker, urls in REMAINING.items():
    dest = LOGOS_DIR / f"{ticker}.png"
    existing_size = dest.stat().st_size if dest.exists() else 0

    got = False
    for url in urls:
        raw = fetch(url)
        if raw:
            try:
                save_png(raw, dest)
                size_kb = dest.stat().st_size / 1024
                print(f"  {ticker:<12} OK  {size_kb:.1f} KB  {url[:60]}")
                got = True
                break
            except Exception as e:
                print(f"    convert error: {e}")
        time.sleep(0.3)

    if not got:
        if existing_size > 0:
            print(f"  {ticker:<12} no better source (keeping {existing_size/1024:.1f} KB existing)")
        else:
            print(f"  {ticker:<12} MISSING — will use emoji fallback")


# ── 2. Resize oversized files ─────────────────────────────────────────────────
print("\nResizing oversized logos...")
MAX_KB = 150
MAX_W  = 400

for f in sorted(LOGOS_DIR.glob("*.png")):
    size_kb = f.stat().st_size / 1024
    if size_kb > MAX_KB:
        try:
            raw = f.read_bytes()
            img = Image.open(io.BytesIO(raw)).convert("RGBA")
            if img.width > MAX_W:
                ratio = MAX_W / img.width
                img = img.resize((MAX_W, int(img.height * ratio)), Image.LANCZOS)
            out = io.BytesIO()
            img.save(out, "PNG", optimize=True)
            new_bytes = out.getvalue()
            f.write_bytes(new_bytes)
            new_kb = f.stat().st_size / 1024
            print(f"  {f.name:<22} {size_kb:.0f} KB -> {new_kb:.0f} KB")
        except Exception as e:
            print(f"  {f.name:<22} resize error: {e}")


# ── 3. Final report ───────────────────────────────────────────────────────────
print("\nFinal logos inventory:")
logos = sorted(LOGOS_DIR.glob("*.png"))
print(f"  {len(logos)} files")
for f in logos:
    print(f"  {f.stem:<14}  {f.stat().st_size/1024:6.1f} KB")
