"""Documented, auditable cleaning policy (PRD FR-02, "Data quality rules").

Every stage records how many rows it removed. The resulting audit table is
persisted with the rule set so any number in the final report can be traced
back to a transformation.

Design rule: *nothing is dropped silently*. If you change the policy, the audit
table and the manifest change with it.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import pandas as pd

from crosssell.config import PreprocessingConfig

log = logging.getLogger(__name__)


@dataclass
class CleaningResult:
    """Cleaned transaction lines plus the audit trail that produced them."""

    frame: pd.DataFrame
    audit: pd.DataFrame
    excluded: dict[str, int] = field(default_factory=dict)

    @property
    def retention(self) -> float:
        start = int(self.audit["rows_remaining"].iloc[0]) if len(self.audit) else 0
        return float(len(self.frame) / start) if start else 0.0

    def summary(self) -> dict[str, object]:
        return {
            "rows_in": int(self.audit["rows_remaining"].iloc[0]) if len(self.audit) else 0,
            "rows_out": int(len(self.frame)),
            "retention": round(self.retention, 4),
            "invoices": int(self.frame["InvoiceNo"].nunique()) if len(self.frame) else 0,
            "products": int(self.frame["StockCode"].nunique()) if len(self.frame) else 0,
            "customers": int(self.frame["CustomerID"].nunique()) if len(self.frame) else 0,
            "date_min": (
                str(self.frame["InvoiceDate"].min()) if len(self.frame) else None
            ),
            "date_max": (
                str(self.frame["InvoiceDate"].max()) if len(self.frame) else None
            ),
            "stages": self.audit.to_dict(orient="records"),
        }


def _coerce_types(df: pd.DataFrame) -> pd.DataFrame:
    """Identifiers become trimmed strings; measures become numeric; dates parsed."""
    df = df.copy()
    for col in ("InvoiceNo", "StockCode", "Description", "Country"):
        df[col] = df[col].astype("string").str.strip()
    df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"], errors="coerce")
    df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce")
    df["UnitPrice"] = pd.to_numeric(df["UnitPrice"], errors="coerce")
    # CustomerID is an identifier, not a measurement: keep it as a clean string.
    cust = pd.to_numeric(df["CustomerID"], errors="coerce")
    df["CustomerID"] = (
        cust.astype("Int64").astype("string")
        if cust.notna().any()
        else df["CustomerID"].astype("string").str.strip()
    )
    return df


def is_cancellation(invoice_no: pd.Series) -> pd.Series:
    """Invoice ids prefixed with ``C`` are cancellations in this dataset."""
    return invoice_no.astype("string").str.upper().str.startswith("C", na=False)


def non_product_mask(stock_code: pd.Series, cfg: PreprocessingConfig) -> pd.Series:
    """Flag service lines (postage, fees, manual adjustments) that are not products.

    These codes co-occur with almost everything, so leaving them in produces
    high-support but commercially meaningless rules such as "buy X -> buy POST".
    """
    codes = stock_code.astype("string").str.strip()
    deny = {c.strip().upper() for c in cfg.non_product_stock_codes}
    mask = codes.str.upper().isin(deny).fillna(False)
    for pattern in cfg.non_product_code_patterns:
        mask |= codes.str.contains(re.compile(pattern, re.IGNORECASE), na=False)
    return mask


def clean_transactions(df: pd.DataFrame, cfg: PreprocessingConfig) -> CleaningResult:
    """Apply the cleaning policy, returning the cleaned frame and its audit trail.

    Stages (each configurable):

    1. type coercion
    2. drop exact duplicate rows
    3. exclude cancellation invoices (``C`` prefix)
    4. require invoice / product / date / quantity / price
    5. keep positive quantities
    6. keep positive unit prices
    7. drop non-product service codes
    8. optional country filter
    9. optional "customer id required" filter
    """
    audit: list[dict[str, object]] = []
    excluded: dict[str, int] = {}

    work = _coerce_types(df)
    audit.append({"stage": "raw input", "rows_remaining": len(work), "rows_removed": 0})

    def step(name: str, mask_keep: pd.Series | None, new: pd.DataFrame | None = None) -> None:
        nonlocal work
        before = len(work)
        work = new if new is not None else work.loc[mask_keep].copy()
        removed = before - len(work)
        audit.append({"stage": name, "rows_remaining": len(work), "rows_removed": removed})
        if removed:
            excluded[name] = removed

    if cfg.drop_exact_duplicates:
        step("drop exact duplicate rows", None, work.drop_duplicates())

    if cfg.exclude_cancellations:
        step("exclude cancellation invoices (C prefix)", ~is_cancellation(work["InvoiceNo"]))

    required = ["InvoiceNo", "StockCode", "InvoiceDate", "Quantity", "UnitPrice"]
    present = work[required].notna().all(axis=1)
    present &= work["InvoiceNo"].str.len().gt(0).fillna(False)
    present &= work["StockCode"].str.len().gt(0).fillna(False)
    step("require invoice/product/date/quantity/price", present)

    if cfg.require_positive_quantity:
        step("keep positive quantities", work["Quantity"] > 0)

    if cfg.require_positive_unit_price:
        step("keep positive unit prices", work["UnitPrice"] > 0)

    if cfg.drop_non_product_codes:
        step("drop non-product service codes", ~non_product_mask(work["StockCode"], cfg))

    if cfg.country:
        step(f"keep country == {cfg.country!r}", work["Country"].eq(cfg.country).fillna(False))

    if cfg.drop_missing_customer_id:
        step("require CustomerID", work["CustomerID"].notna())

    work = work.copy()
    work["LineRevenue"] = work["Quantity"] * work["UnitPrice"]
    work["Description"] = work["Description"].fillna("")

    audit_df = pd.DataFrame(audit)
    log.info(
        "Cleaning kept %s/%s rows (%.1f%%), %s invoices, %s products",
        f"{len(work):,}",
        f"{len(df):,}",
        100 * len(work) / max(len(df), 1),
        f"{work['InvoiceNo'].nunique():,}",
        f"{work['StockCode'].nunique():,}",
    )
    return CleaningResult(frame=work, audit=audit_df, excluded=excluded)


def validate_clean(frame: pd.DataFrame, cfg: PreprocessingConfig) -> dict[str, bool]:
    """Post-conditions the rest of the pipeline relies on."""
    checks = {
        "no missing InvoiceNo": bool(frame["InvoiceNo"].notna().all()),
        "no missing StockCode": bool(frame["StockCode"].notna().all()),
        "no missing InvoiceDate": bool(frame["InvoiceDate"].notna().all()),
        "no exact duplicate rows": bool(not frame.duplicated().any()),
        "LineRevenue == Quantity * UnitPrice": bool(
            ((frame["LineRevenue"] - frame["Quantity"] * frame["UnitPrice"]).abs() < 1e-6).all()
        ),
    }
    if cfg.require_positive_quantity:
        checks["all quantities positive"] = bool((frame["Quantity"] > 0).all())
    if cfg.require_positive_unit_price:
        checks["all unit prices positive"] = bool((frame["UnitPrice"] > 0).all())
    if cfg.exclude_cancellations:
        checks["no cancellation invoices"] = bool(not is_cancellation(frame["InvoiceNo"]).any())
    if cfg.drop_non_product_codes:
        checks["no non-product service codes"] = bool(
            not non_product_mask(frame["StockCode"], cfg).any()
        )
    return checks
