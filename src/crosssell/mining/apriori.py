"""Apriori frequent-itemset mining.

Implementation of the algorithm described in

    R. Agrawal and R. Srikant, *Fast Algorithms for Mining Association Rules in
    Large Databases*, VLDB 1994.

Structure of the algorithm (as in the paper):

``L1``          frequent 1-itemsets by a single pass over the database.
``apriori-gen`` candidates ``Ck`` are built by joining ``L(k-1)`` with itself on
                the shared ``k-2`` prefix, then pruned using the downward-closure
                property: *every subset of a frequent itemset is frequent*.
counting        support of surviving candidates.

Two counting strategies are used, both exact:

* ``k = 2`` -- co-occurring pairs are counted directly while scanning each
  basket. This is the paper's observation that the number of candidate pairs is
  large while the number of pairs that actually occur is small.
* ``k >= 3`` -- vertical *tid-lists*: the transaction-id set of a candidate is
  the intersection of the tid-list of its ``(k-1)``-prefix with that of its last
  item, so support is obtained without re-scanning the database.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from itertools import combinations

import pandas as pd

log = logging.getLogger(__name__)

Itemset = tuple[str, ...]


def min_support_count(n_transactions: int, min_support: float) -> int:
    """Absolute count corresponding to a relative support threshold."""
    if n_transactions <= 0:
        return 0
    return max(1, math.ceil(min_support * n_transactions - 1e-9))


def _apriori_gen(prev_level: list[Itemset], k: int) -> list[Itemset]:
    """``apriori-gen``: join step followed by the subset-pruning step."""
    prev_set = set(prev_level)
    candidates: list[Itemset] = []
    n = len(prev_level)
    for i in range(n):
        a = prev_level[i]
        prefix = a[: k - 2]
        for j in range(i + 1, n):
            b = prev_level[j]
            if b[: k - 2] != prefix:
                break  # sorted order: no further item shares this prefix
            candidate = (*a, b[-1])
            # prune: all (k-1)-subsets must be frequent
            if all(sub in prev_set for sub in combinations(candidate, k - 1)):
                candidates.append(candidate)
    return candidates


def apriori(
    transactions: Sequence[frozenset[str]],
    min_support: float,
    max_len: int = 3,
    verbose: bool = False,
) -> dict[frozenset[str], int]:
    """Return ``{itemset: support_count}`` for every frequent itemset.

    Parameters
    ----------
    transactions:
        One ``frozenset`` of item ids per transaction (invoice).
    min_support:
        Minimum relative support in ``(0, 1]``.
    max_len:
        Largest itemset size to mine. ``3`` is plenty for cross-sell and keeps
        the candidate space small.
    """
    n = len(transactions)
    if n == 0:
        return {}
    threshold = min_support_count(n, min_support)

    # ---- L1: single pass over the database --------------------------------
    counts1: dict[str, int] = {}
    for items in transactions:
        for item in items:
            counts1[item] = counts1.get(item, 0) + 1
    frequent: dict[frozenset[str], int] = {
        frozenset((item,)): c for item, c in counts1.items() if c >= threshold
    }
    level: list[Itemset] = sorted((item,) for item, c in counts1.items() if c >= threshold)
    if verbose:
        log.info("L1: %s/%s items frequent (min count %s)", len(level), len(counts1), threshold)
    if max_len < 2 or not level:
        return frequent

    # ---- L2: count co-occurring pairs directly ----------------------------
    frequent_items = {item for (item,) in level}
    pair_counts: dict[Itemset, int] = {}
    for items in transactions:
        present = sorted(items & frequent_items)
        for a, b in combinations(present, 2):
            key = (a, b)
            pair_counts[key] = pair_counts.get(key, 0) + 1
    level = sorted(pair for pair, c in pair_counts.items() if c >= threshold)
    for pair in level:
        frequent[frozenset(pair)] = pair_counts[pair]
    if verbose:
        log.info("L2: %s/%s candidate pairs frequent", len(level), len(pair_counts))

    # ---- Lk, k >= 3: candidate generation + tid-list intersection ---------
    tids: dict[str, set[int]] = {item: set() for item in frequent_items}
    for tid, items in enumerate(transactions):
        for item in items & frequent_items:
            tids[item].add(tid)
    level_tids: dict[Itemset, set[int]] = {
        pair: tids[pair[0]] & tids[pair[1]] for pair in level
    }

    k = 3
    while level and k <= max_len:
        candidates = _apriori_gen(level, k)
        next_level: list[Itemset] = []
        next_tids: dict[Itemset, set[int]] = {}
        for cand in candidates:
            tidset = level_tids[cand[:-1]] & tids[cand[-1]]
            if len(tidset) >= threshold:
                next_level.append(cand)
                next_tids[cand] = tidset
                frequent[frozenset(cand)] = len(tidset)
        if verbose:
            log.info("L%s: %s/%s candidates frequent", k, len(next_level), len(candidates))
        level, level_tids = next_level, next_tids
        k += 1

    return frequent


def support_counts_to_frame(
    counts: dict[frozenset[str], int], n_transactions: int
) -> pd.DataFrame:
    """Tidy frame of frequent itemsets ordered by support."""
    if not counts:
        return pd.DataFrame(columns=["itemset", "length", "support_count", "support"])
    rows = [
        {
            "itemset": tuple(sorted(itemset)),
            "length": len(itemset),
            "support_count": count,
            "support": count / n_transactions,
        }
        for itemset, count in counts.items()
    ]
    return (
        pd.DataFrame(rows)
        .sort_values(["length", "support"], ascending=[True, False], ignore_index=True)
    )


def frequent_itemsets_frame(
    transactions: Sequence[frozenset[str]], min_support: float, max_len: int = 3
) -> pd.DataFrame:
    """Convenience wrapper: mine and return the tidy itemset frame."""
    counts = apriori(transactions, min_support=min_support, max_len=max_len)
    return support_counts_to_frame(counts, len(transactions))
