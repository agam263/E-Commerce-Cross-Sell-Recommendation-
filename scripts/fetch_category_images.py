#!/usr/bin/env python3
"""Download one representative photograph per derived product category.

Why this exists
---------------
The Online Retail dataset is invoice lines. It has no product photography, no
image URLs and no category column, so there is no such thing as "the picture of
StockCode 85123A". Searching a photo library for the actual SKU names returns
nothing at all -- "white hanging heart t-light holder", "jumbo bag red
retrospot" and "regency cakestand 3 tier" each return zero results -- and
loosening the query returns the wrong object entirely.

So the dashboard shows one photograph per *category*, chosen once by hand, and
labels it as representative of that category rather than a photograph of the
product. That is a claim the data supports; "here is your SKU" is not.

How the images are chosen
-------------------------
Each entry below is pinned to an exact Wikimedia Commons file title that was
reviewed by eye before being added. Nothing here searches at run time, so
re-running this script a year from now fetches the same twelve images rather
than whatever a search happens to rank first that day -- the same
reproducibility standard the rule set itself is held to.

Licensing: every pinned file is Public Domain, CC0, CC BY or CC BY-SA. No
non-commercial (NC) licences. Attribution for each image is written to
``attribution.json`` next to the files and rendered in the dashboard's
Documentation screen, which is what the BY and BY-SA terms require.

Usage
-----
    python scripts/fetch_category_images.py           # skip files already present
    python scripts/fetch_category_images.py --force   # re-download everything
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://commons.wikimedia.org/w/api.php"

# A descriptive, non-personal User-Agent. Wikimedia asks automated clients to
# identify themselves; it deliberately carries no information about whoever is
# running the script.
USER_AGENT = "crosssell-dashboard/1.0 (educational cross-sell analytics project)"

# Commons rate-limits on-the-fly thumbnail generation. 800 is one of the
# standard pre-rendered widths, so these come straight from cache instead of
# being rendered per request -- which is what was triggering HTTP 429.
THUMB_WIDTH = 800

#: category -> exact Commons file title, each reviewed before pinning.
PINNED: dict[str, str] = {
    "Christmas & Seasonal": "File:Weihnachtsbaumkugeln -- 2021 -- 9195.jpg",
    "Party & Celebration": "File:Balloon arch.jpg",
    "Bags & Totes": "File:Canvas two-tone tote Navy and Natural7 (9038437258).jpg",
    "Candles & Lighting": "File:Heart-shaped tea-light candle holder, Himalayan salt.jpg",
    "Kitchen & Dining": "File:Set of frog mugs.jpg",
    "Storage & Containers": "File:Thye Hong Biscuit Tin (front view).jpg",
    "Stationery & Paper": (
        "File:Working on a planning session with stationery items, "
        "notebook, and colorful pencils on a wooden desk.jpg"
    ),
    "Jewellery & Accessories": (
        "File:02023 Bead necklace, glass, amber, Wielbark Culture jewellery.jpg"
    ),
    "Toys & Games": "File:Handy wooden toys for kids.jpg",
    "Garden & Outdoor": "File:Trowel.JPG",
    "Home Decor": "File:Blaue Rispe nach Riemerschmid Vase 10cm.JPG",
    "Textiles & Soft Goods": "File:Dark blue tea towel stack.jpg",
}

# "Uncategorised" deliberately has no image. A product we could not classify
# gets the neutral icon tile instead of a photograph implying we know what it
# is.

OUT_DIR = Path(__file__).resolve().parent.parent / "frontend" / "public" / "category-images"


def slug(category: str) -> str:
    """Stable file-safe name for a category."""
    return re.sub(r"[^a-z0-9]+", "-", category.lower()).strip("-")


def strip_html(value: str | None) -> str:
    """Commons returns artist/licence fields as HTML fragments.

    Some entries nest the same name in two elements, which naively yields
    "Unknown author Unknown author"; an exact doubling is collapsed.
    """
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    half, remainder = divmod(len(text), 2)
    if remainder == 1 and text[:half] == text[half + 1:] and text[half] == " ":
        return text[:half]
    return text


def _open(url: str, timeout: int, attempts: int = 6):  # noqa: D417
    """Open a URL, backing off on HTTP 429.

    Commons rate-limits bursts, and a dozen sequential requests is enough to
    trip it. Retrying with a widening delay is the documented way to behave.
    """
    delay = 8.0
    last: Exception | None = None
    for attempt in range(attempts):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code not in (429, 503):
                raise
            if attempt < attempts - 1:
                print(f"      rate-limited, waiting {delay:.0f}s")
                time.sleep(delay)
                delay *= 2
    raise RuntimeError(f"gave up after {attempts} attempts: {last}")


def request_json(params: dict[str, str], attempts: int = 6) -> dict:
    url = API + "?" + urllib.parse.urlencode(params)
    with _open(url, timeout=45, attempts=attempts) as response:
        return json.load(response)


def fetch_metadata(title: str, attempts: int = 6) -> dict:
    data = request_json(attempts=attempts, params={
        "action": "query",
        "format": "json",
        "titles": title,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata|mime",
        "iiurlwidth": str(THUMB_WIDTH),
    })
    pages = (data.get("query") or {}).get("pages") or {}
    page = next(iter(pages.values()), {})
    if "imageinfo" not in page:
        raise RuntimeError(f"{title}: not found on Commons (was it renamed or deleted?)")
    info = page["imageinfo"][0]
    meta = info.get("extmetadata", {})
    artist = strip_html(meta.get("Artist", {}).get("value")) or "Unknown author"
    return {
        "commons_title": title,
        "thumb_url": info.get("thumburl") or info.get("url"),
        "source_page": info.get("descriptionurl", ""),
        "author": artist,
        "license": strip_html(meta.get("LicenseShortName", {}).get("value")) or "see source page",
        "license_url": meta.get("LicenseUrl", {}).get("value", ""),
    }


def download(url: str, destination: Path, attempts: int = 6) -> int:
    with _open(url, timeout=90, attempts=attempts) as response:
        payload = response.read()
    destination.write_bytes(payload)
    return len(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="re-download images already present")
    parser.add_argument(
        "--attempts",
        type=int,
        default=6,
        help=(
            "retries per request before giving up (default 6, with widening backoff). "
            "Use 1 to fail fast when Commons is rate-limiting and you only want to "
            "refresh the manifest for images already on disk."
        ),
    )
    args = parser.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    attribution: dict[str, dict] = {}
    failures: list[str] = []

    for category, title in PINNED.items():
        name = slug(category)
        target = OUT_DIR / f"{name}.jpg"
        try:
            meta = fetch_metadata(title, attempts=args.attempts)
        except (urllib.error.URLError, RuntimeError, TimeoutError) as exc:
            print(f"  {category:26s} FAILED  {exc}", file=sys.stderr)
            failures.append(category)
            continue

        if target.exists() and not args.force:
            size = target.stat().st_size
            print(f"  {category:26s} kept    {target.name} ({size // 1024} KB)")
        else:
            try:
                size = download(meta["thumb_url"], target, attempts=args.attempts)
            except (urllib.error.URLError, RuntimeError, TimeoutError) as exc:
                print(f"  {category:26s} FAILED  {exc}", file=sys.stderr)
                failures.append(category)
                continue
            print(f"  {category:26s} fetched {target.name} ({size // 1024} KB)")

        attribution[category] = {
            "file": f"{name}.jpg",
            "commons_title": meta["commons_title"],
            "author": meta["author"],
            "license": meta["license"],
            "license_url": meta["license_url"],
            "source_page": meta["source_page"],
        }
        time.sleep(4.0)  # be a polite API client

    if attribution:
        # sort_keys so the manifest is byte-stable across runs
        (OUT_DIR / "attribution.json").write_text(
            json.dumps(attribution, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        )
        print(f"\nwrote {OUT_DIR / 'attribution.json'} ({len(attribution)} images)")

    if failures:
        print(f"\n{len(failures)} categories failed: {failures}", file=sys.stderr)
        print("The dashboard falls back to icon tiles for those.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
