"""Mining entry point: runs the configured engine and returns itemsets + rules.

``builtin``  -- the implementation in :mod:`crosssell.mining.apriori`.
``mlxtend``  -- ``mlxtend.frequent_patterns.apriori`` on a one-hot matrix, kept
                as an independent reference implementation. The test-suite
                asserts the two engines agree, which is what makes the built-in
                miner trustworthy (PRD research foundation).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pandas as pd

from crosssell.config import MiningConfig
from crosssell.mining.apriori import apriori, min_support_count, support_counts_to_frame
from crosssell.mining.rules import generate_rules

if TYPE_CHECKING:  # pragma: no cover
    from crosssell.data.baskets import TransactionSet

log = logging.getLogger(__name__)


@dataclass
class MiningResult:
    itemsets: pd.DataFrame
    rules: pd.DataFrame
    n_transactions: int
    engine: str
    elapsed_seconds: float
    stats: dict[str, object] = field(default_factory=dict)


def _mine_mlxtend(ts: TransactionSet, cfg: MiningConfig) -> dict[frozenset[str], int]:
    from mlxtend.frequent_patterns import apriori as mlx_apriori

    frame = ts.to_bool_frame()
    found = mlx_apriori(
        frame, min_support=cfg.min_support, use_colnames=True, max_len=cfg.max_itemset_size
    )
    n = len(ts)
    return {
        frozenset(row.itemsets): int(round(row.support * n))
        for row in found.itertuples(index=False)
    }


def mine(ts: TransactionSet, cfg: MiningConfig) -> MiningResult:
    """Mine frequent itemsets and association rules from a transaction set."""
    start = time.perf_counter()
    if cfg.engine == "mlxtend":
        frequent = _mine_mlxtend(ts, cfg)
    else:
        frequent = apriori(
            ts.itemsets, min_support=cfg.min_support, max_len=cfg.max_itemset_size, verbose=True
        )

    itemsets = support_counts_to_frame(frequent, len(ts))
    rules = generate_rules(
        frequent,
        n_transactions=len(ts),
        min_confidence=cfg.min_confidence,
        min_lift=cfg.min_lift,
        min_antecedent_count=cfg.min_antecedent_count,
        max_consequent_size=cfg.max_consequent_size,
    )
    elapsed = time.perf_counter() - start

    by_len = itemsets["length"].value_counts().sort_index().to_dict() if len(itemsets) else {}
    stats = {
        "min_support_count": min_support_count(len(ts), cfg.min_support),
        "frequent_itemsets": int(len(itemsets)),
        "frequent_itemsets_by_length": {int(k): int(v) for k, v in by_len.items()},
        "rules": int(len(rules)),
        "items_in_rules": int(
            pd.unique(
                pd.Series(
                    [i for r in rules["antecedents"] for i in r]
                    + [i for r in rules["consequents"] for i in r]
                )
            ).size
        )
        if len(rules)
        else 0,
    }
    log.info(
        "Mining finished in %.1fs: %s frequent itemsets, %s rules",
        elapsed,
        f"{len(itemsets):,}",
        f"{len(rules):,}",
    )
    return MiningResult(
        itemsets=itemsets,
        rules=rules,
        n_transactions=len(ts),
        engine=cfg.engine,
        elapsed_seconds=elapsed,
        stats=stats,
    )
