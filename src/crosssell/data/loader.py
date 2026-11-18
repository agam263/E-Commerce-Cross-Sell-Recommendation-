"""Raw dataset ingestion for the UCI / Kaggle *Online Retail* dataset.

The raw file is treated as immutable: nothing in this module writes to it.
Only column naming is normalised here -- all row-level policy lives in
:mod:`crosssell.data.preprocessing` so that it can be audited in one place.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

#: Canonical schema expected by the pipeline (PRD "Dataset & Data Contract").
SCHEMA: dict[str, str] = {
    "InvoiceNo": "transaction identifier / basket key",
    "StockCode": "product identifier (canonical item id for mining)",
    "Description": "human-readable product name (display only)",
    "Quantity": "units purchased",
    "InvoiceDate": "transaction timestamp",
    "UnitPrice": "unit selling price",
    "CustomerID": "customer identifier (optional)",
    "Country": "customer geography (optional)",
}

REQUIRED_COLUMNS = ("InvoiceNo", "StockCode", "Quantity", "InvoiceDate", "UnitPrice")
OPTIONAL_COLUMNS = ("Description", "CustomerID", "Country")

#: Accepted spellings seen across Kaggle/UCI re-uploads of the same dataset.
_ALIASES: dict[str, str] = {
    "invoiceno": "InvoiceNo",
    "invoice": "InvoiceNo",
    "invoicenumber": "InvoiceNo",
    "stockcode": "StockCode",
    "productcode": "StockCode",
    "description": "Description",
    "productname": "Description",
    "quantity": "Quantity",
    "qty": "Quantity",
    "invoicedate": "InvoiceDate",
    "date": "InvoiceDate",
    "unitprice": "UnitPrice",
    "price": "UnitPrice",
    "customerid": "CustomerID",
    "customer": "CustomerID",
    "country": "Country",
}


def _normalise_key(name: str) -> str:
    return str(name).strip().lower().replace(" ", "").replace("_", "").replace("-", "")


def standardise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Trim/rename columns to the canonical schema and verify required fields."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    rename = {c: _ALIASES[_normalise_key(c)] for c in df.columns if _normalise_key(c) in _ALIASES}
    df = df.rename(columns=rename)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            "Input file does not match the Online Retail schema. "
            f"Missing required column(s): {missing}. Found: {list(df.columns)}"
        )
    for col in OPTIONAL_COLUMNS:
        if col not in df.columns:
            log.warning("Optional column %r absent; created as empty.", col)
            df[col] = pd.NA
    return df[list(REQUIRED_COLUMNS) + list(OPTIONAL_COLUMNS)]


def file_fingerprint(path: str | Path) -> dict[str, object]:
    """Content hash + size of the raw dataset, recorded in the rule-set manifest."""
    path = Path(path)
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return {
        "name": path.name,
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }


def load_raw(path: str | Path) -> pd.DataFrame:
    """Read the Online Retail dataset from ``.xlsx``, ``.xls``, ``.csv`` or ``.parquet``."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Dataset not found at {path}.\n"
            "Download the Online Retail dataset first:  python scripts/download_data.py"
        )

    suffix = path.suffix.lower()
    log.info("Reading raw dataset from %s (%.1f MB)", path, path.stat().st_size / 1e6)
    if suffix in {".xlsx", ".xls"}:
        df = pd.read_excel(path, dtype={"InvoiceNo": str, "StockCode": str})
    elif suffix == ".csv":
        df = pd.read_csv(
            path,
            dtype={"InvoiceNo": str, "StockCode": str},
            encoding="ISO-8859-1",
            encoding_errors="replace",
        )
    elif suffix == ".parquet":
        df = pd.read_parquet(path)
    else:
        raise ValueError(f"Unsupported file type {suffix!r}: use .xlsx, .xls, .csv or .parquet")

    df = standardise_columns(df)
    log.info("Loaded %s rows x %s columns", f"{len(df):,}", df.shape[1])
    return df
