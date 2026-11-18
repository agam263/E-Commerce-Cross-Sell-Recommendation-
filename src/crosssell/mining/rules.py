"""Association-rule generation and interest metrics.

For a rule ``A -> B`` over transactions ``T``:

===========  =======================================================  ============================
metric       definition                                                reading
===========  =======================================================  ============================
support      ``|A u B| / |T|``                                         how common the combination is
confidence   ``support(A u B) / support(A)``                           P(B | A)
lift         ``confidence / support(B)``                               strength vs B's popularity
leverage     ``support(A u B) - support(A) * support(B)``              absolute excess co-occurrence
conviction   ``(1 - support(B)) / (1 - confidence)``                   how wrong the rule would be
===========  =======================================================  ============================

``lift > 1`` means A and B occur together more often than independence would
predict -- the minimum bar for calling something a cross-sell signal.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from itertools import combinations

import pandas as pd

log = logging.getLogger(__name__)

RULE_COLUMNS = [
    "antecedents",
    "consequents",
    "antecedent_len",
    "consequent_len",
    "support",
    "confidence",
    "lift",
    "leverage",
    "conviction",
    "antecedent_support",
    "consequent_support",
    "support_count",
    "antecedent_count",
    "consequent_count",
]


def rule_metrics(
    support_ab: float, support_a: float, support_b: float
) -> dict[str, float]:
    """Interest metrics for a single rule from the three support values."""
    if support_a <= 0 or support_b <= 0:
        raise ValueError("antecedent and consequent support must be positive")
    confidence = support_ab / support_a
    lift = confidence / support_b
    leverage = support_ab - support_a * support_b
    conviction = (
        math.inf if confidence >= 1.0 else (1.0 - support_b) / (1.0 - confidence)
    )
    return {
        "support": support_ab,
        "confidence": confidence,
        "lift": lift,
        "leverage": leverage,
        "conviction": conviction,
    }


def generate_rules(
    frequent: dict[frozenset[str], int],
    n_transactions: int,
    min_confidence: float = 0.0,
    min_lift: float = 1.0,
    min_antecedent_count: int = 1,
    max_consequent_size: int = 1,
) -> pd.DataFrame:
    """Turn frequent itemsets into filtered, ranked association rules.

    Only itemsets of size >= 2 can produce a rule. Every candidate antecedent
    and consequent is itself frequent (downward closure), so its support is read
    straight out of ``frequent``.
    """
    if n_transactions <= 0 or not frequent:
        return pd.DataFrame(columns=RULE_COLUMNS)

    rows: list[dict[str, object]] = []
    for itemset, count_ab in frequent.items():
        if len(itemset) < 2:
            continue
        support_ab = count_ab / n_transactions
        max_c = min(max_consequent_size, len(itemset) - 1)
        for c_size in range(1, max_c + 1):
            for consequent in combinations(sorted(itemset), c_size):
                cons = frozenset(consequent)
                ante = itemset - cons
                count_a = frequent.get(ante)
                count_b = frequent.get(cons)
                if count_a is None or count_b is None:
                    continue  # can only happen if `frequent` was filtered externally
                if count_a < min_antecedent_count:
                    continue
                m = rule_metrics(
                    support_ab, count_a / n_transactions, count_b / n_transactions
                )
                if m["confidence"] < min_confidence or m["lift"] < min_lift:
                    continue
                rows.append(
                    {
                        "antecedents": tuple(sorted(ante)),
                        "consequents": tuple(sorted(cons)),
                        "antecedent_len": len(ante),
                        "consequent_len": len(cons),
                        **m,
                        "antecedent_support": count_a / n_transactions,
                        "consequent_support": count_b / n_transactions,
                        "support_count": count_ab,
                        "antecedent_count": count_a,
                        "consequent_count": count_b,
                    }
                )

    if not rows:
        return pd.DataFrame(columns=RULE_COLUMNS)

    rules = pd.DataFrame(rows)[RULE_COLUMNS]
    rules = rules.sort_values(
        ["lift", "confidence", "support"], ascending=False, ignore_index=True
    )
    rules.insert(0, "rule_id", [f"R{i:06d}" for i in range(1, len(rules) + 1)])
    log.info("Generated %s rules passing the thresholds", f"{len(rules):,}")
    return rules


def rules_from_transactions(
    transactions: Sequence[frozenset[str]],
    min_support: float,
    max_itemset_size: int = 3,
    **rule_kwargs: object,
) -> pd.DataFrame:
    """Mine and generate rules in one call (used by tests and notebooks)."""
    from crosssell.mining.apriori import apriori

    frequent = apriori(transactions, min_support=min_support, max_len=max_itemset_size)
    return generate_rules(frequent, len(transactions), **rule_kwargs)  # type: ignore[arg-type]
