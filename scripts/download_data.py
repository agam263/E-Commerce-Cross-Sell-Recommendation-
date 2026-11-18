#!/usr/bin/env python3
"""Fetch the Online Retail dataset into ``data/raw/``.

The project brief points at Kaggle, which requires an account and an API token.
The same dataset is published by its original source, the UCI Machine Learning
Repository, as a plain download -- that is what this script uses, so a fresh
clone can be set up with no credentials.

    python scripts/download_data.py                 # download if missing
    python scripts/download_data.py --force         # re-download

If you prefer Kaggle (``kaggle datasets download -d carrie1/ecommerce-data``),
just place the resulting ``.xlsx``/``.csv`` at data/raw/ and point
``paths.raw_data`` in config/config.yaml at it. The pipeline hashes whatever
file it is given, so the manifest always records exactly which copy was used.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
URL = "https://archive.ics.uci.edu/static/public/352/online+retail.zip"
TARGET_DIR = REPO_ROOT / "data" / "raw"
EXPECTED_NAME = "Online Retail.xlsx"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="re-download even if present")
    parser.add_argument("--url", default=URL)
    args = parser.parse_args()

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    target = TARGET_DIR / EXPECTED_NAME
    if target.exists() and not args.force:
        print(f"Already present: {target} ({target.stat().st_size / 1e6:.1f} MB)")
        print(f"sha256 {sha256(target)}")
        return 0

    print(f"Downloading {args.url} …")
    try:
        with urllib.request.urlopen(args.url, timeout=300) as response:  # noqa: S310
            payload = response.read()
    except Exception as exc:  # pragma: no cover - network failure path
        print(f"Download failed: {exc}", file=sys.stderr)
        print(
            "\nManual alternative:\n"
            "  1. https://archive.ics.uci.edu/dataset/352/online+retail  (or Kaggle)\n"
            f"  2. save the spreadsheet as {target}\n",
            file=sys.stderr,
        )
        return 1

    if args.url.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = [n for n in archive.namelist() if n.lower().endswith((".xlsx", ".xls", ".csv"))]
            if not names:
                print(f"No dataset file inside the archive: {archive.namelist()}", file=sys.stderr)
                return 1
            name = names[0]
            target = TARGET_DIR / Path(name).name
            target.write_bytes(archive.read(name))
    else:
        target.write_bytes(payload)

    print(f"Saved {target} ({target.stat().st_size / 1e6:.1f} MB)")
    print(f"sha256 {sha256(target)}")
    print("\nNext:  make train")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
