"""Offline evaluation of a mined rule set (PRD "Evaluation & Success Metrics").

Two complementary views:

**Rule-population view** -- distributions of support, confidence and lift over
the generated rules. Answers "are these rules built on enough evidence?".

**Serving view** -- a leave-one-out replay on hold-out invoices the miner never
saw. For every hold-out basket one product is hidden, the engine recommends
from the rest, and we check whether the hidden product comes back in the top-K:

* ``hit_rate@k``  share of baskets where the hidden product was recommended
* ``mrr@k``       mean reciprocal rank of the hidden product
* ``coverage``    share of baskets for which any rule fired at all
* ``popularity_baseline_hit_rate`` the same replay using "recommend the overall
  best-sellers" -- the honest baseline an association-rule engine must beat.

The hidden product is chosen with a fixed seed, so the evaluation is reproducible.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from crosssell.service.recommender import Recommender

if TYPE_CHECKING:  # pragma: no cover
    from crosssell.data.baskets import TransactionSet

log = logging.getLogger(__name__)


def rule_metric_summary(rules: pd.DataFrame) -> dict[str, Any]:
    """Distribution of the interest metrics over the whole rule population."""
    if rules.empty:
        return {"rules": 0}
    out: dict[str, Any] = {
        "rules": int(len(rules)),
        "rules_by_antecedent_size": {
            int(k): int(v) for k, v in rules["antecedent_len"].value_counts().sort_index().items()
        },
        "distinct_antecedent_products": int(
            len({i for a in rules["antecedents"] for i in a})
        ),
        "distinct_consequent_products": int(
            len({i for c in rules["consequents"] for i in c})
        ),
    }
    for metric in ("support", "confidence", "lift", "leverage"):
        if metric not in rules.columns:
            continue
        series = rules[metric].replace([np.inf, -np.inf], np.nan).dropna()
        if series.empty:
            continue
        out[metric] = {
            "min": float(series.min()),
            "p25": float(series.quantile(0.25)),
            "median": float(series.median()),
            "mean": float(series.mean()),
            "p75": float(series.quantile(0.75)),
            "p95": float(series.quantile(0.95)),
            "max": float(series.max()),
        }
    return out


def _sample_baskets(ts: TransactionSet, max_baskets: int, seed: int) -> list[frozenset[str]]:
    eligible = [s for s in ts.itemsets if len(s) >= 2]
    if max_baskets and len(eligible) > max_baskets:
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(eligible), size=max_baskets, replace=False)
        eligible = [eligible[i] for i in sorted(idx)]
    return eligible


def leave_one_out_replay(
    recommender: Recommender,
    holdout: TransactionSet,
    k: int = 5,
    seed: int = 42,
    max_baskets: int = 20000,
    min_confidence: float | None = None,
    min_lift: float | None = None,
) -> dict[str, Any]:
    """Replay hold-out baskets and measure top-K retrieval of a hidden product."""
    baskets = _sample_baskets(holdout, max_baskets, seed)
    if not baskets:
        return {"baskets_evaluated": 0, "note": "no hold-out basket had 2+ products"}

    rng = np.random.default_rng(seed)
    popular = [c for c in recommender.popularity.index]

    hits = served = reciprocal = 0.0
    baseline_hits = 0
    evaluated = 0
    hidden_seen: set[str] = set()
    hidden_hit: set[str] = set()

    for basket in baskets:
        items = sorted(basket)
        hidden = items[int(rng.integers(len(items)))]
        context = set(items) - {hidden}
        if not context:
            continue
        evaluated += 1
        hidden_seen.add(hidden)

        recs = recommender.recommend(
            context,
            top_k=k,
            allow_fallback=False,
            validate=False,
            min_confidence=min_confidence,
            min_lift=min_lift,
        )
        if recs:
            served += 1
            codes = [r.stock_code for r in recs]
            if hidden in codes:
                hits += 1
                hidden_hit.add(hidden)
                reciprocal += 1.0 / (codes.index(hidden) + 1)

        baseline = [c for c in popular if c not in context][:k]
        if hidden in baseline:
            baseline_hits += 1

    hit_rate = hits / evaluated if evaluated else 0.0
    baseline_rate = baseline_hits / evaluated if evaluated else 0.0
    return {
        "k": k,
        "baskets_evaluated": evaluated,
        "baskets_with_recommendation": int(served),
        "basket_coverage": served / evaluated if evaluated else 0.0,
        "hit_rate_at_k": hit_rate,
        "hit_rate_at_k_when_served": hits / served if served else 0.0,
        "mrr_at_k": reciprocal / evaluated if evaluated else 0.0,
        "popularity_baseline_hit_rate": baseline_rate,
        "uplift_vs_popularity": (hit_rate / baseline_rate) if baseline_rate else None,
        "distinct_hidden_products": len(hidden_seen),
        "distinct_hidden_products_recovered": len(hidden_hit),
        "seed": seed,
    }


def product_coverage(
    recommender: Recommender, products: list[str] | None = None, k: int = 5
) -> dict[str, Any]:
    """Share of catalog products with at least one rule-based recommendation."""
    return recommender.coverage(products, top_k=k)


def evaluate(
    recommender: Recommender,
    rules: pd.DataFrame,
    holdout: TransactionSet,
    k: int = 5,
    seed: int = 42,
    max_baskets: int = 20000,
    label: str = "test",
) -> dict[str, Any]:
    """Full evaluation bundle for one hold-out split."""
    holdout_products = sorted({i for s in holdout.itemsets for i in s})
    result = {
        "split": label,
        "holdout_invoices": len(holdout),
        "holdout_products": len(holdout_products),
        "rule_population": rule_metric_summary(rules),
        "replay": leave_one_out_replay(
            recommender, holdout, k=k, seed=seed, max_baskets=max_baskets
        ),
        "catalog_coverage": product_coverage(recommender, k=k),
        "holdout_product_coverage": product_coverage(recommender, holdout_products, k=k),
    }
    log.info(
        "[%s] hit@%s=%.3f (popularity baseline %.3f), basket coverage %.1f%%",
        label,
        k,
        result["replay"].get("hit_rate_at_k", 0.0),
        result["replay"].get("popularity_baseline_hit_rate", 0.0),
        100 * result["replay"].get("basket_coverage", 0.0),
    )
    return result


def threshold_sweep(
    recommender: Recommender,
    validation: TransactionSet,
    confidences: list[float],
    lifts: list[float],
    k: int = 5,
    seed: int = 42,
    max_baskets: int = 4000,
) -> pd.DataFrame:
    """Grid-search serving thresholds on the *validation* split only.

    The test split is never touched here -- that is what keeps the final
    reported numbers honest (PRD: "do not tune final thresholds on the same
    hold-out used for final reporting").

    Every combination is scored in a single pass over the baskets: matching
    rules are found once per basket and then re-ranked per threshold pair,
    which is what makes a full grid affordable.
    """
    baskets = _sample_baskets(validation, max_baskets, seed)
    combos = [(c, lift) for c in confidences for lift in lifts]
    tally = {combo: {"hits": 0, "served": 0, "rr": 0.0} for combo in combos}
    rng = np.random.default_rng(seed)
    evaluated = 0

    for basket in baskets:
        items = sorted(basket)
        hidden = items[int(rng.integers(len(items)))]
        context = set(items) - {hidden}
        if not context:
            continue
        evaluated += 1
        candidates = recommender.candidate_rules(context)
        for combo in combos:
            min_conf, min_lift = combo
            ranked = recommender.rank_candidates(
                candidates, context, top_k=k, min_confidence=min_conf, min_lift=min_lift
            )
            if not ranked:
                continue
            cell = tally[combo]
            cell["served"] += 1
            codes = [code for code, _ in ranked]
            if hidden in codes:
                cell["hits"] += 1
                cell["rr"] += 1.0 / (codes.index(hidden) + 1)

    rows = [
        {
            "min_confidence": combo[0],
            "min_lift": combo[1],
            "hit_rate_at_k": cell["hits"] / evaluated if evaluated else 0.0,
            "basket_coverage": cell["served"] / evaluated if evaluated else 0.0,
            "mrr_at_k": cell["rr"] / evaluated if evaluated else 0.0,
            "precision_when_served": cell["hits"] / cell["served"] if cell["served"] else 0.0,
            "baskets_evaluated": evaluated,
        }
        for combo, cell in tally.items()
    ]
    return pd.DataFrame(rows).sort_values("hit_rate_at_k", ascending=False, ignore_index=True)
