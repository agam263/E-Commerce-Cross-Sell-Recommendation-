"""Invoice-level basket construction, product catalog and chronological splits.

For Apriori the unit of analysis is the *transaction* (one invoice), and an item
is *present or absent* -- buying ten of something is still one co-occurrence
(PRD: "binary presence for core basket mining", FR-03).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from crosssell.config import CohortConfig, PreprocessingConfig, SplitConfig

log = logging.getLogger(__name__)

COHORT_NEW = "new"
COHORT_REPEAT = "repeat"
COHORT_UNKNOWN = "unknown"


@dataclass
class TransactionSet:
    """An ordered collection of baskets plus per-invoice metadata.

    ``itemsets[i]`` holds the distinct ``StockCode`` values of ``invoice_ids[i]``.
    """

    invoice_ids: list[str]
    itemsets: list[frozenset[str]]
    meta: pd.DataFrame  # indexed by InvoiceNo

    def __len__(self) -> int:
        return len(self.itemsets)

    def __iter__(self):
        return iter(self.itemsets)

    @property
    def n_items(self) -> int:
        return len(self.item_counts())

    def item_counts(self) -> pd.Series:
        """Number of invoices containing each product, descending."""
        counts: dict[str, int] = {}
        for items in self.itemsets:
            for item in items:
                counts[item] = counts.get(item, 0) + 1
        return (
            pd.Series(counts, dtype="int64", name="invoice_count")
            .sort_values(ascending=False)
            .rename_axis("StockCode")
        )

    def item_support(self) -> pd.Series:
        return (self.item_counts() / max(len(self), 1)).rename("support")

    def subset(self, invoice_ids: Iterable[str]) -> TransactionSet:
        wanted = set(invoice_ids)
        keep = [i for i, inv in enumerate(self.invoice_ids) if inv in wanted]
        ids = [self.invoice_ids[i] for i in keep]
        return TransactionSet(
            invoice_ids=ids,
            itemsets=[self.itemsets[i] for i in keep],
            meta=self.meta.loc[ids],
        )

    def restrict_products(
        self, products: Iterable[str], min_basket_size: int = 1
    ) -> TransactionSet:
        """Keep only ``products``; drop baskets that fall below ``min_basket_size``."""
        allowed = set(products)
        ids: list[str] = []
        sets: list[frozenset[str]] = []
        for inv, items in zip(self.invoice_ids, self.itemsets, strict=True):
            kept = items & allowed
            if len(kept) >= min_basket_size:
                ids.append(inv)
                sets.append(frozenset(kept))
        meta = self.meta.loc[ids].copy()
        meta["n_items"] = [len(s) for s in sets]
        return TransactionSet(invoice_ids=ids, itemsets=sets, meta=meta)

    def by_cohort(self, cohort: str) -> TransactionSet:
        ids = self.meta.index[self.meta["cohort"] == cohort]
        return self.subset(ids)

    def to_bool_frame(self, products: Sequence[str] | None = None) -> pd.DataFrame:
        """One-hot (boolean) invoice x product matrix -- the mlxtend input format.

        Dense and memory hungry; the built-in miner does not need it.
        """
        cols = list(products) if products is not None else sorted(self.item_counts().index)
        index = {c: j for j, c in enumerate(cols)}
        mat = np.zeros((len(self), len(cols)), dtype=bool)
        for i, items in enumerate(self.itemsets):
            for item in items:
                j = index.get(item)
                if j is not None:
                    mat[i, j] = True
        return pd.DataFrame(mat, index=pd.Index(self.invoice_ids, name="InvoiceNo"), columns=cols)

    def describe(self) -> dict[str, object]:
        sizes = np.array([len(s) for s in self.itemsets]) if len(self) else np.array([0])
        return {
            "invoices": len(self),
            "products": self.n_items,
            "mean_basket_size": float(sizes.mean()),
            "median_basket_size": float(np.median(sizes)),
            "p95_basket_size": float(np.percentile(sizes, 95)),
            "max_basket_size": int(sizes.max()),
            "date_min": str(self.meta["InvoiceDate"].min()) if len(self) else None,
            "date_max": str(self.meta["InvoiceDate"].max()) if len(self) else None,
        }


def assign_cohorts(clean: pd.DataFrame, cfg: CohortConfig) -> pd.Series:
    """Label each invoice ``new`` / ``repeat`` / ``unknown`` (stretch goal US-009).

    The label is assigned from the customer's invoice *sequence number at the
    time of that invoice*, so it never uses information from the future.
    """
    inv = (
        clean.groupby("InvoiceNo", observed=True)
        .agg(InvoiceDate=("InvoiceDate", "min"), CustomerID=("CustomerID", "first"))
        .sort_values(["CustomerID", "InvoiceDate"])
    )
    seq = inv.groupby("CustomerID", dropna=True, observed=True).cumcount() + 1
    cohort = pd.Series(COHORT_UNKNOWN, index=inv.index, dtype="object")
    known = inv["CustomerID"].notna()
    cohort[known & (seq < cfg.repeat_min_invoices)] = COHORT_NEW
    cohort[known & (seq >= cfg.repeat_min_invoices)] = COHORT_REPEAT
    return cohort.rename("cohort")


def build_transactions(
    clean: pd.DataFrame,
    prep: PreprocessingConfig,
    cohorts: CohortConfig | None = None,
) -> TransactionSet:
    """Collapse cleaned product lines into one binary basket per invoice."""
    pairs = (
        clean.groupby(["InvoiceNo", "StockCode"], observed=True)
        .agg(Quantity=("Quantity", "sum"), LineRevenue=("LineRevenue", "sum"))
        .reset_index()
    )
    grouped = pairs.groupby("InvoiceNo", observed=True)["StockCode"].apply(frozenset)

    meta = (
        clean.groupby("InvoiceNo", observed=True)
        .agg(
            InvoiceDate=("InvoiceDate", "min"),
            revenue=("LineRevenue", "sum"),
            CustomerID=("CustomerID", "first"),
            Country=("Country", "first"),
        )
        .join(grouped.map(len).rename("n_items"))
    )
    if cohorts is not None and cohorts.enabled:
        meta = meta.join(assign_cohorts(clean, cohorts))
    else:
        meta["cohort"] = COHORT_UNKNOWN

    meta = meta.sort_values("InvoiceDate")
    keep = meta.index[meta["n_items"] >= prep.min_basket_size]
    meta = meta.loc[keep]

    ids = list(meta.index)
    ts = TransactionSet(
        invoice_ids=ids,
        itemsets=[grouped[i] for i in ids],
        meta=meta,
    )
    log.info(
        "Built %s baskets (>=%s distinct products) covering %s products",
        f"{len(ts):,}",
        prep.min_basket_size,
        f"{ts.n_items:,}",
    )
    return ts


def build_product_catalog(clean: pd.DataFrame) -> pd.DataFrame:
    """Per-product display name and commercial aggregates.

    ``avg_line_revenue`` is the average value of one purchase of the product and
    is the default "average order value" used by the revenue simulator.
    """
    described = clean.loc[clean["Description"].astype("string").str.len() > 0]

    def _mode(series: pd.Series) -> str:
        modes = series.mode()
        return str(modes.iloc[0]) if len(modes) else "Unknown product"

    names = (
        described.groupby("StockCode", observed=True)["Description"].agg(_mode)
        if len(described)
        else pd.Series(dtype="object")
    )

    catalog = (
        clean.groupby("StockCode", observed=True)
        .agg(
            invoice_count=("InvoiceNo", "nunique"),
            lines=("InvoiceNo", "size"),
            total_quantity=("Quantity", "sum"),
            total_revenue=("LineRevenue", "sum"),
            median_unit_price=("UnitPrice", "median"),
            avg_line_revenue=("LineRevenue", "mean"),
            first_seen=("InvoiceDate", "min"),
            last_seen=("InvoiceDate", "max"),
        )
        .join(names.rename("ProductName"))
        .reset_index()
    )
    catalog["ProductName"] = catalog["ProductName"].fillna("Unknown product")
    catalog = catalog[
        [
            "StockCode", "ProductName", "invoice_count", "lines", "total_quantity",
            "total_revenue", "median_unit_price", "avg_line_revenue", "first_seen", "last_seen",
        ]
    ].sort_values("invoice_count", ascending=False, ignore_index=True)
    return catalog


def split_transactions(
    ts: TransactionSet, cfg: SplitConfig, seed: int = 42
) -> dict[str, TransactionSet]:
    """Split baskets into ``train`` / ``validation`` / ``test``.

    ``temporal`` (default) mimics deployment: mine on the past, evaluate on the
    future. The test slice stays untouched while thresholds are tuned on
    validation (PRD product principle).
    """
    if cfg.strategy == "temporal":
        order = list(ts.meta.sort_values("InvoiceDate").index)
    else:
        rng = np.random.default_rng(seed)
        order = list(np.array(ts.invoice_ids)[rng.permutation(len(ts))])

    n = len(order)
    n_train = int(round(n * cfg.train_fraction))
    n_val = int(round(n * cfg.validation_fraction))
    bounds = {
        "train": order[:n_train],
        "validation": order[n_train : n_train + n_val],
        "test": order[n_train + n_val :],
    }
    splits = {name: ts.subset(ids) for name, ids in bounds.items()}
    for name, part in splits.items():
        log.info(
            "split %-10s %7s baskets  %s -> %s",
            name,
            f"{len(part):,}",
            part.meta["InvoiceDate"].min() if len(part) else "-",
            part.meta["InvoiceDate"].max() if len(part) else "-",
        )
    return splits
