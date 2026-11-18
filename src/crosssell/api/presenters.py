"""Conversion helpers between pipeline objects and API response models."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from crosssell.api.schemas import ProductOut, RecommendationOut, RuleOut
from crosssell.service.categories import categorise
from crosssell.service.recommender import Recommendation
from crosssell.service.store import RuleStore


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isinf(number) or math.isnan(number) else number


def rule_to_out(row: dict[str, Any], names: dict[str, str]) -> RuleOut:
    antecedents = list(row["antecedents"])
    consequents = list(row["consequents"])
    return RuleOut(
        rule_id=str(row.get("rule_id") or ""),
        antecedents=antecedents,
        antecedent_names=[names.get(i, "Unknown product") for i in antecedents],
        antecedent_categories=[categorise(names.get(i)) for i in antecedents],
        consequents=consequents,
        consequent_names=[names.get(i, "Unknown product") for i in consequents],
        consequent_categories=[categorise(names.get(i)) for i in consequents],
        antecedent_len=int(row["antecedent_len"]),
        support=float(row["support"]),
        confidence=float(row["confidence"]),
        lift=float(row["lift"]),
        leverage=float(row["leverage"]),
        conviction=_finite(row.get("conviction")),
        support_count=int(row["support_count"]),
        antecedent_count=int(row["antecedent_count"]),
        consequent_count=int(row["consequent_count"]),
    )


def rules_to_out(frame: pd.DataFrame, names: dict[str, str]) -> list[RuleOut]:
    return [rule_to_out(row, names) for row in frame.to_dict(orient="records")]


def product_to_out(
    row: dict[str, Any], popularity: pd.Series, triggerable: frozenset[str]
) -> ProductOut:
    code = str(row["StockCode"])
    return ProductOut(
        stock_code=code,
        product_name=str(row.get("ProductName") or "Unknown product"),
        invoice_count=int(row.get("invoice_count") or 0),
        support=float(popularity.get(code, 0.0)),
        total_quantity=float(row.get("total_quantity") or 0.0),
        total_revenue=float(row.get("total_revenue") or 0.0),
        median_unit_price=float(row.get("median_unit_price") or 0.0),
        avg_line_revenue=float(row.get("avg_line_revenue") or 0.0),
        has_rules=code in triggerable,
        category=categorise(row.get("ProductName")),
    )


def products_to_out(frame: pd.DataFrame, store: RuleStore) -> list[ProductOut]:
    triggerable = store.triggerable_products
    popularity = store.artifacts.popularity
    return [
        product_to_out(row, popularity, triggerable)
        for row in frame.to_dict(orient="records")
    ]


def recommendation_to_out(rec: Recommendation) -> RecommendationOut:
    return RecommendationOut(**rec.to_dict())


def histogram(values: pd.Series, bins: int = 20, clip_quantile: float = 0.99) -> dict[str, Any]:
    """Binned counts for the dashboard charts, with the long tail clipped."""
    series = pd.Series(values).replace([np.inf, -np.inf], np.nan).dropna().astype(float)
    if series.empty:
        return {"bins": [], "counts": [], "clipped_at": None}
    upper = float(series.quantile(clip_quantile))
    lower = float(series.min())
    if upper <= lower:
        upper = lower + 1e-9
    counts, edges = np.histogram(series.clip(upper=upper), bins=bins, range=(lower, upper))
    return {
        "bins": [
            {"start": float(edges[i]), "end": float(edges[i + 1]), "count": int(counts[i])}
            for i in range(len(counts))
        ],
        "counts": [int(c) for c in counts],
        "clipped_at": upper,
        "min": lower,
        "max": float(series.max()),
    }
