"""Rule-based cross-sell recommendation ranking.

Serving contract (PRD "Recommendation Engine Requirements"):

* input is one ``StockCode`` or a basket of them;
* a rule fires only when its whole antecedent is contained in the basket;
* products already in the basket are never recommended back;
* each recommendation carries the rule and the metrics that produced it;
* when no rule clears the thresholds the engine returns a clearly-labelled
  popularity fallback -- never a fabricated confidence value.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field

import pandas as pd

from crosssell.config import RecommendationConfig
from crosssell.service.categories import UNCATEGORISED, categorise

log = logging.getLogger(__name__)

SOURCE_RULE = "association_rule"
SOURCE_FALLBACK = "fallback_popularity"

#: Metrics a caller may rank on. Restricted so a request cannot sort by an
#: arbitrary column, and so the ordering stays explainable in the UI.
RANKABLE: tuple[str, ...] = ("confidence", "lift", "support", "leverage")


def normalise_rank_by(rank_by: Sequence[str] | None) -> tuple[str, ...] | None:
    """Validate a caller-supplied ranking order.

    Returns ``None`` when nothing was supplied, so the configured default
    applies. Raises ``ValueError`` on an unknown or duplicated metric.
    """
    if not rank_by:
        return None
    order = tuple(str(m).strip().lower() for m in rank_by)
    unknown = [m for m in order if m not in RANKABLE]
    if unknown:
        raise ValueError(f"cannot rank by {unknown}; choose from {list(RANKABLE)}")
    if len(set(order)) != len(order):
        raise ValueError(f"duplicate metric in rank_by: {list(order)}")
    return order


class UnknownProductError(KeyError):
    """Raised when a requested product id is not part of the trained catalog."""


@dataclass
class Recommendation:
    """One ranked cross-sell suggestion plus the evidence behind it."""

    stock_code: str
    product_name: str
    rank: int
    score: float
    source: str
    explanation: str
    support: float | None = None
    confidence: float | None = None
    lift: float | None = None
    leverage: float | None = None
    conviction: float | None = None
    rule_id: str | None = None
    antecedents: list[str] = field(default_factory=list)
    antecedent_count: int | None = None
    support_count: int | None = None
    popularity_support: float | None = None
    avg_line_revenue: float | None = None
    median_unit_price: float | None = None
    invoice_count: int | None = None
    category: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _fmt_items(items: Sequence[str], names: dict[str, str]) -> str:
    labels = [f"{names.get(i, i)} ({i})" for i in items]
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + " and " + labels[-1]


class Recommender:
    """Serves ranked recommendations from a mined rule set.

    The rule set is indexed once at construction time:
    ``item -> rule rows whose antecedent contains that item``. Lookups then only
    test the few rules that could possibly fire for a basket.
    """

    def __init__(
        self,
        rules: pd.DataFrame,
        catalog: pd.DataFrame,
        popularity: pd.Series,
        cfg: RecommendationConfig | None = None,
        ruleset_version: str = "unversioned",
    ) -> None:
        self.cfg = cfg or RecommendationConfig()
        self.ruleset_version = ruleset_version
        self.rules = rules.reset_index(drop=True)
        self.catalog = catalog.set_index("StockCode", drop=False)
        self.popularity = popularity.astype(float).sort_values(ascending=False)
        self.names: dict[str, str] = self.catalog["ProductName"].astype(str).to_dict()
        self._avg_revenue: dict[str, float] = self._numeric_column("avg_line_revenue")
        self._unit_price: dict[str, float] = self._numeric_column("median_unit_price")
        self._invoice_count: dict[str, float] = self._numeric_column("invoice_count")
        self._category: dict[str, str] = {
            code: categorise(name) for code, name in self.names.items()
        }
        self._records: list[dict] = self.rules.to_dict(orient="records")
        for rec in self._records:
            rec["antecedents"] = tuple(rec["antecedents"])
            rec["consequents"] = tuple(rec["consequents"])
            rec["_antecedent_set"] = frozenset(rec["antecedents"])
        self._by_item: dict[str, list[int]] = {}
        for idx, rec in enumerate(self._records):
            for item in rec["_antecedent_set"]:
                self._by_item.setdefault(item, []).append(idx)

    @staticmethod
    def _int_or_none(value: float | None) -> int | None:
        return None if value is None else int(value)

    def _numeric_column(self, column: str) -> dict[str, float]:
        """Catalog column as a {stock_code: value} map, or {} when absent."""
        if column not in self.catalog.columns:
            return {}
        return self.catalog[column].astype(float).to_dict()

    def product_category(self, stock_code: str) -> str:
        """Derived category -- see :mod:`crosssell.service.categories`."""
        return self._category.get(stock_code, UNCATEGORISED)

    # -- introspection ------------------------------------------------------
    def __len__(self) -> int:
        return len(self._records)

    @property
    def products(self) -> list[str]:
        return list(self.catalog["StockCode"])

    def knows_product(self, stock_code: str) -> bool:
        return stock_code in self.catalog.index

    def product_name(self, stock_code: str) -> str:
        return self.names.get(stock_code, "Unknown product")

    # -- ranking ------------------------------------------------------------
    def _rank_key(self, rec: dict, rank_by: Sequence[str] | None = None) -> tuple:
        return tuple(float(rec[m]) for m in (rank_by or self.cfg.rank_by))

    def _explain(self, rec: dict) -> str:
        ante = _fmt_items(rec["antecedents"], self.names)
        cons = _fmt_items(rec["consequents"], self.names)
        return (
            f"In the training window, {rec['confidence']:.0%} of the "
            f"{int(rec['antecedent_count']):,} invoices containing {ante} also contained "
            f"{cons} ({int(rec['support_count']):,} invoices, support {rec['support']:.3f}). "
            f"That is {rec['lift']:.2f}x more often than this product's overall purchase "
            f"rate, so the pairing is {'stronger' if rec['lift'] >= 1 else 'weaker'} "
            f"than chance."
        )

    def recommend(
        self,
        basket: Iterable[str],
        top_k: int | None = None,
        min_confidence: float | None = None,
        min_lift: float | None = None,
        allow_fallback: bool | None = None,
        validate: bool = True,
        rank_by: Sequence[str] | None = None,
    ) -> list[Recommendation]:
        """Return up to ``top_k`` ranked recommendations for ``basket``.

        ``rank_by`` overrides the configured ranking order for this call only,
        which lets the dashboard show the configured ordering alongside the
        PRD's lift-first ordering without re-mining anything.
        """
        order = normalise_rank_by(rank_by)
        basket_set = {str(p).strip() for p in basket if str(p).strip()}
        if not basket_set:
            raise ValueError("basket must contain at least one product id")
        if validate:
            unknown = sorted(p for p in basket_set if not self.knows_product(p))
            if unknown:
                raise UnknownProductError(
                    f"Unknown product id(s) for rule set {self.ruleset_version}: {unknown}"
                )

        k = top_k or self.cfg.top_k
        use_fallback = (
            self.cfg.fallback == "popularity" if allow_fallback is None else allow_fallback
        )

        candidates = self.candidate_rules(basket_set)
        ordered = self.rank_candidates(
            candidates,
            basket_set,
            top_k=k,
            min_confidence=min_confidence,
            min_lift=min_lift,
            rank_by=order,
        )
        out: list[Recommendation] = [
            Recommendation(
                stock_code=code,
                product_name=self.product_name(code),
                rank=i + 1,
                score=float(rec[(order or self.cfg.rank_by)[0]]),
                source=SOURCE_RULE,
                explanation=self._explain(rec),
                support=float(rec["support"]),
                confidence=float(rec["confidence"]),
                lift=float(rec["lift"]),
                leverage=float(rec["leverage"]),
                conviction=(
                    None if rec["conviction"] in (float("inf"), None) else float(rec["conviction"])
                ),
                rule_id=str(rec.get("rule_id", "")) or None,
                antecedents=list(rec["antecedents"]),
                antecedent_count=int(rec["antecedent_count"]),
                support_count=int(rec["support_count"]),
                popularity_support=float(self.popularity.get(code, 0.0)),
                avg_line_revenue=self._avg_revenue.get(code),
                median_unit_price=self._unit_price.get(code),
                invoice_count=self._int_or_none(self._invoice_count.get(code)),
                category=self.product_category(code),
            )
            for i, (code, rec) in enumerate(ordered)
        ]

        if out or not use_fallback:
            return out
        return self._popularity_fallback(basket_set, k)

    def candidate_rules(self, basket: set[str]) -> list[dict]:
        """Rules whose entire antecedent is contained in ``basket``.

        This is the expensive half of serving, so it is separated from ranking:
        a threshold sweep finds the candidates once per basket and then re-ranks
        them cheaply for every threshold combination.
        """
        candidate_ids: set[int] = set()
        for item in basket:
            candidate_ids.update(self._by_item.get(item, ()))
        out: list[dict] = []
        for idx in candidate_ids:
            rec = self._records[idx]
            if rec["_antecedent_set"] <= basket:
                out.append(rec)
        return out

    def rank_candidates(
        self,
        candidates: list[dict],
        basket: set[str],
        top_k: int,
        min_confidence: float | None = None,
        min_lift: float | None = None,
        rank_by: Sequence[str] | None = None,
    ) -> list[tuple[str, dict]]:
        """Best rule per consequent, filtered and ranked, excluding the basket."""
        order = normalise_rank_by(rank_by)
        best: dict[str, dict] = {}
        for rec in candidates:
            if min_confidence is not None and rec["confidence"] < min_confidence:
                continue
            if min_lift is not None and rec["lift"] < min_lift:
                continue
            for consequent in rec["consequents"]:
                if consequent in basket:  # never recommend what is already there
                    continue
                current = best.get(consequent)
                if current is None or self._rank_key(rec, order) > self._rank_key(current, order):
                    best[consequent] = rec
        return sorted(
            best.items(), key=lambda kv: self._rank_key(kv[1], order), reverse=True
        )[:top_k]

    def _popularity_fallback(self, basket: set[str], k: int) -> list[Recommendation]:
        """Documented no-rule behaviour: most popular products, no fake metrics."""
        limit = min(k, self.cfg.fallback_size)
        picks = [c for c in self.popularity.index if c not in basket][:limit]
        return [
            Recommendation(
                stock_code=code,
                product_name=self.product_name(code),
                rank=i + 1,
                score=float(self.popularity.get(code, 0.0)),
                source=SOURCE_FALLBACK,
                explanation=(
                    "No association rule for this product cleared the configured thresholds. "
                    f"Showing an overall best-seller instead: it appears in "
                    f"{self.popularity.get(code, 0.0):.1%} of training invoices. "
                    "This is a popularity fallback, not an association rule."
                ),
                popularity_support=float(self.popularity.get(code, 0.0)),
                avg_line_revenue=self._avg_revenue.get(code),
                median_unit_price=self._unit_price.get(code),
                invoice_count=self._int_or_none(self._invoice_count.get(code)),
                category=self.product_category(code),
            )
            for i, code in enumerate(picks)
        ]

    def rules_for(self, stock_code: str, role: str = "antecedent") -> pd.DataFrame:
        """All rules where ``stock_code`` appears as antecedent or consequent."""
        if role == "antecedent":
            mask = self.rules["antecedents"].map(lambda a: stock_code in a)
        elif role == "consequent":
            mask = self.rules["consequents"].map(lambda c: stock_code in c)
        else:
            raise ValueError("role must be 'antecedent' or 'consequent'")
        return self.rules.loc[mask]

    def coverage(self, products: Iterable[str] | None = None, **kwargs) -> dict[str, object]:
        """Share of products with at least one rule-based recommendation."""
        items = list(products) if products is not None else self.products
        covered = 0
        for p in items:
            recs = self.recommend([p], allow_fallback=False, validate=False, **kwargs)
            covered += bool(recs)
        return {
            "products_tested": len(items),
            "products_with_recommendation": covered,
            "coverage": covered / len(items) if items else 0.0,
        }
