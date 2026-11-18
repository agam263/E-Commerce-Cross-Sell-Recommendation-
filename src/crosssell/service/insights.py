"""Derive business insights from a mined rule set.

Everything here is computed from the rule table and the product catalog that
the pipeline already produced. Each insight carries the numbers it was derived
from and the rows that back it, so the dashboard never states something the
reader cannot check.

Rules for what may be generated:

* no claim beyond what the counts support -- these describe historical
  co-occurrence in one dataset, never causation or predicted uplift;
* every sentence is a template with measured values substituted in, so new data
  changes the numbers but can never invent a new claim;
* when the data does not support an insight (no rules, no cohorts, an empty
  category), it is omitted rather than padded.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd

from crosssell.service.categories import UNCATEGORISED, categorise

#: How an insight should be read: an action, a gap, a caution, or an observation.
KINDS = ("opportunity", "coverage", "risk", "pattern")


@dataclass
class Insight:
    id: str
    kind: str
    title: str
    body: str
    metric_label: str
    metric_value: float
    metric_format: str = "number"  # number | percent | multiple | currency
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _pair_key(row: dict[str, Any]) -> frozenset[str]:
    return frozenset(tuple(row["antecedents"]) + tuple(row["consequents"]))


def _dedupe_mirrors(frame: pd.DataFrame) -> pd.DataFrame:
    """Keep one direction per product pair -- the higher-confidence one.

    A strongly co-occurring pair always yields both A->B and B->A with identical
    lift, so an undeduplicated "top pairs" list is half redundant.
    """
    if frame.empty:
        return frame
    ordered = frame.sort_values(["lift", "confidence"], ascending=False, kind="stable")
    seen: set[frozenset[str]] = set()
    keep: list[int] = []
    for idx, row in zip(ordered.index, ordered.to_dict(orient="records"), strict=True):
        key = _pair_key(row)
        if key in seen:
            continue
        seen.add(key)
        keep.append(idx)
    return ordered.loc[keep]


def _name(names: dict[str, str], code: str) -> str:
    return names.get(code, "Unknown product")


def strongest_pairs(frame: pd.DataFrame, names: dict[str, str], limit: int = 5) -> Insight | None:
    """The highest-lift product pairs, one direction each."""
    pairs = _dedupe_mirrors(frame).head(limit)
    if pairs.empty:
        return None
    rows = pairs.to_dict(orient="records")
    top = rows[0]
    a, b = top["antecedents"][0], top["consequents"][0]
    return Insight(
        id="strongest-pairs",
        kind="opportunity",
        title="Strongest product pairings",
        body=(
            f"{_name(names, a)} and {_name(names, b)} appear together "
            f"{top['lift']:.0f}x more often than their individual popularity would predict "
            f"({int(top['support_count']):,} shared invoices). These are the pairings with the "
            "clearest historical evidence for placing side by side."
        ),
        metric_label="Top pair lift",
        metric_value=float(top["lift"]),
        metric_format="multiple",
        evidence=[
            {
                "rule_id": str(r.get("rule_id", "")),
                "antecedent": r["antecedents"][0],
                "antecedent_name": _name(names, r["antecedents"][0]),
                "consequent": r["consequents"][0],
                "consequent_name": _name(names, r["consequents"][0]),
                "lift": float(r["lift"]),
                "confidence": float(r["confidence"]),
                "support_count": int(r["support_count"]),
            }
            for r in rows
        ],
    )


def cross_sell_hubs(frame: pd.DataFrame, names: dict[str, str], limit: int = 5) -> Insight | None:
    """Products that trigger the most rules -- the best places to put a widget."""
    if frame.empty:
        return None
    singles = frame.loc[frame["antecedent_len"] == 1]
    if singles.empty:
        return None
    codes = singles["antecedents"].map(lambda a: a[0])
    counts = codes.value_counts()
    if counts.empty:
        return None
    rows = [
        {
            "stock_code": code,
            "product_name": _name(names, code),
            "rule_count": int(n),
            "max_lift": float(singles.loc[codes == code, "lift"].max()),
        }
        for code, n in counts.head(limit).items()
    ]
    best = rows[0]
    return Insight(
        id="cross-sell-hubs",
        kind="opportunity",
        title="Best cross-sell anchors",
        body=(
            f"{best['product_name']} triggers {best['rule_count']:,} association rules, more than "
            "any other product. Anchoring a cross-sell widget on products like these gives the "
            "engine the most to work with, because a rule only fires when its whole 'if' side is "
            "already in the basket."
        ),
        metric_label="Rules triggered",
        metric_value=float(best["rule_count"]),
        evidence=rows,
    )


def thin_coverage(frame: pd.DataFrame, names: dict[str, str], limit: int = 5) -> Insight | None:
    """Products whose recommendations rest on a single rule."""
    if frame.empty:
        return None
    singles = frame.loc[frame["antecedent_len"] == 1]
    if singles.empty:
        return None
    codes = singles["antecedents"].map(lambda a: a[0])
    counts = codes.value_counts()
    fragile = counts[counts == 1]
    if fragile.empty:
        return None
    rows = []
    for code in list(fragile.index)[:limit]:
        rule = singles.loc[codes == code].iloc[0]
        rows.append(
            {
                "stock_code": code,
                "product_name": _name(names, code),
                "rule_count": 1,
                "consequent_name": _name(names, rule["consequents"][0]),
                "support_count": int(rule["support_count"]),
            }
        )
    return Insight(
        id="thin-coverage",
        kind="risk",
        title="Recommendations resting on one rule",
        body=(
            f"{len(fragile):,} products have exactly one association rule. Their recommendation "
            "has no second opinion behind it, so a change in buying behaviour or a tighter "
            "threshold would drop them straight to the popularity fallback. Treat these as the "
            "weakest part of the rule set."
        ),
        metric_label="Products with one rule",
        metric_value=float(len(fragile)),
        evidence=rows,
    )


def category_mix(frame: pd.DataFrame, names: dict[str, str]) -> Insight | None:
    """How often a rule crosses a derived product category."""
    if frame.empty:
        return None
    pairs = _dedupe_mirrors(frame)
    if pairs.empty:
        return None
    categories = {code: categorise(name) for code, name in names.items()}

    def _cross(row: dict[str, Any]) -> bool | None:
        a = categories.get(row["antecedents"][0], UNCATEGORISED)
        b = categories.get(row["consequents"][0], UNCATEGORISED)
        if UNCATEGORISED in (a, b):
            return None  # unknown on either side -- do not count it either way
        return a != b

    flags = [f for f in (_cross(r) for r in pairs.to_dict(orient="records")) if f is not None]
    if not flags:
        return None
    cross = sum(flags)
    share = cross / len(flags)
    return Insight(
        id="category-mix",
        kind="pattern",
        title="Most pairings stay inside a category"
        if share < 0.5
        else "Most pairings cross categories",
        body=(
            f"{share:.0%} of product pairs link two different derived categories "
            f"({cross:,} of {len(flags):,} pairs where both sides could be categorised). "
            + (
                "Within-category pairing usually means customers are buying ranges -- colour or "
                "size variants of the same item -- which is a reason to merchandise the range "
                "together rather than treat the rule as a true cross-sell."
                if share < 0.5
                else "Cross-category pairing is the more valuable kind of cross-sell: it moves a "
                "customer into a part of the catalog they were not already shopping."
            )
        ),
        metric_label="Cross-category pairs",
        metric_value=float(share),
        metric_format="percent",
        evidence=[],
    )


def coverage_summary(
    triggerable: int, catalog_size: int, basket_coverage: float | None
) -> Insight | None:
    """What share of the catalog the engine can actually say something about."""
    if not catalog_size:
        return None
    share = triggerable / catalog_size
    body = (
        f"{triggerable:,} of {catalog_size:,} products ({share:.0%}) can fire at least one "
        "association rule. The rest fall back to best-sellers, which is a labelled, honest "
        "default rather than a fabricated recommendation."
    )
    if basket_coverage is not None:
        body += (
            f" In the hold-out window {basket_coverage:.0%} of invoices still received at least "
            "one rule-based recommendation, because the products that do have rules are the ones "
            "customers actually buy."
        )
    return Insight(
        id="catalog-coverage",
        kind="coverage",
        title="Catalog the engine can speak for",
        body=body,
        metric_label="Catalog coverage",
        metric_value=float(share),
        metric_format="percent",
        evidence=[],
    )


def build_insights(
    rules: pd.DataFrame,
    names: dict[str, str],
    triggerable: int,
    catalog_size: int,
    basket_coverage: float | None = None,
) -> list[Insight]:
    """All insights the current rule set supports, strongest first."""
    candidates = [
        strongest_pairs(rules, names),
        cross_sell_hubs(rules, names),
        coverage_summary(triggerable, catalog_size, basket_coverage),
        category_mix(rules, names),
        thin_coverage(rules, names),
    ]
    return [i for i in candidates if i is not None]
