"""Apriori and rule metrics.

The decisive test is :func:`test_builtin_engine_matches_mlxtend`: the built-in
miner is trustworthy precisely because it reproduces an independent reference
implementation exactly, itemset for itemset and rule for rule.
"""

from __future__ import annotations

import math
import random

import pandas as pd
import pytest

from crosssell.mining.apriori import _apriori_gen, apriori, min_support_count
from crosssell.mining.rules import generate_rules, rule_metrics

mlxtend = pytest.importorskip("mlxtend.frequent_patterns")


def _transactions(seed: int = 3, n: int = 500) -> list[frozenset[str]]:
    rng = random.Random(seed)
    items = [f"P{i}" for i in range(22)]
    out = []
    for _ in range(n):
        basket = set(rng.sample(items, rng.randint(2, 7)))
        if "P0" in basket and rng.random() < 0.75:
            basket.add("P1")
        if "P2" in basket and rng.random() < 0.65:
            basket |= {"P3", "P4"}
        out.append(frozenset(basket))
    return out


def test_min_support_count_rounds_up():
    assert min_support_count(100, 0.05) == 5
    assert min_support_count(1000, 0.0015) == 2
    assert min_support_count(13, 0.1) == 2     # 1.3 -> 2
    assert min_support_count(0, 0.1) == 0


def test_apriori_counts_a_hand_checked_example():
    transactions = [
        frozenset({"A", "B"}),
        frozenset({"A", "B", "C"}),
        frozenset({"A", "C"}),
        frozenset({"B"}),
    ]
    frequent = apriori(transactions, min_support=0.5, max_len=3)
    assert frequent[frozenset({"A"})] == 3
    assert frequent[frozenset({"B"})] == 3
    assert frequent[frozenset({"C"})] == 2
    assert frequent[frozenset({"A", "B"})] == 2
    assert frequent[frozenset({"A", "C"})] == 2
    assert frozenset({"B", "C"}) not in frequent      # support 1/4 < 0.5
    assert frozenset({"A", "B", "C"}) not in frequent


def test_downward_closure_holds():
    frequent = apriori(_transactions(), min_support=0.04, max_len=3)
    for itemset in frequent:
        for item in itemset:
            subset = itemset - {item}
            if subset:
                assert subset in frequent, f"{subset} must be frequent if {itemset} is"
                assert frequent[subset] >= frequent[itemset]


def test_apriori_gen_prunes_candidates_with_infrequent_subsets():
    # ABC survives (AB, AC, BC all present); ABD dies (BD missing)
    level = [("A", "B"), ("A", "C"), ("A", "D"), ("B", "C")]
    assert _apriori_gen(level, 3) == [("A", "B", "C")]


def test_max_len_is_respected():
    frequent = apriori(_transactions(), min_support=0.03, max_len=2)
    assert max(len(s) for s in frequent) == 2


def test_empty_input_returns_nothing():
    assert apriori([], min_support=0.1) == {}


def test_builtin_engine_matches_mlxtend():
    transactions = _transactions()
    min_support = 0.03
    mine = apriori(transactions, min_support=min_support, max_len=3)

    columns = sorted({i for t in transactions for i in t})
    matrix = pd.DataFrame([[c in t for c in columns] for t in transactions], columns=columns)
    reference = mlxtend.apriori(matrix, min_support=min_support, use_colnames=True, max_len=3)
    expected = {
        frozenset(row.itemsets): round(row.support * len(transactions))
        for row in reference.itertuples(index=False)
    }

    assert set(mine) == set(expected), "frequent itemsets differ from mlxtend"
    assert mine == expected, "support counts differ from mlxtend"


def test_generated_rules_match_mlxtend():
    transactions = _transactions()
    frequent = apriori(transactions, min_support=0.03, max_len=3)
    mine = generate_rules(frequent, len(transactions), min_confidence=0.3, min_lift=1.0)

    columns = sorted({i for t in transactions for i in t})
    matrix = pd.DataFrame([[c in t for c in columns] for t in transactions], columns=columns)
    itemsets = mlxtend.apriori(matrix, min_support=0.03, use_colnames=True, max_len=3)
    reference = mlxtend.association_rules(itemsets, metric="confidence", min_threshold=0.3)
    reference = reference[(reference["lift"] >= 1.0) & (reference["consequents"].map(len) == 1)]

    mine_keys = {(a, c) for a, c in zip(mine["antecedents"], mine["consequents"], strict=True)}
    ref_keys = {
        (tuple(sorted(a)), tuple(sorted(c)))
        for a, c in zip(reference["antecedents"], reference["consequents"], strict=True)
    }
    assert mine_keys == ref_keys

    ref_lookup = {
        (tuple(sorted(a)), tuple(sorted(c))): (s, conf, lift)
        for a, c, s, conf, lift in zip(
            reference["antecedents"], reference["consequents"], reference["support"],
            reference["confidence"], reference["lift"], strict=True,
        )
    }
    for row in mine.itertuples(index=False):
        support, confidence, lift = ref_lookup[(row.antecedents, row.consequents)]
        assert math.isclose(row.support, support, rel_tol=1e-9)
        assert math.isclose(row.confidence, confidence, rel_tol=1e-9)
        assert math.isclose(row.lift, lift, rel_tol=1e-9)


def test_rule_metric_formulas():
    m = rule_metrics(support_ab=0.2, support_a=0.25, support_b=0.20)
    assert m["confidence"] == pytest.approx(0.8)
    assert m["lift"] == pytest.approx(4.0)
    assert m["leverage"] == pytest.approx(0.2 - 0.25 * 0.20)
    assert m["conviction"] == pytest.approx((1 - 0.20) / (1 - 0.8))


def test_conviction_is_infinite_for_a_perfect_rule():
    assert rule_metrics(0.25, 0.25, 0.5)["conviction"] == math.inf


def test_rule_metrics_rejects_zero_support():
    with pytest.raises(ValueError):
        rule_metrics(0.1, 0.0, 0.2)


def test_lift_above_one_means_positive_association():
    # A and B independent -> lift exactly 1
    assert rule_metrics(0.25, 0.5, 0.5)["lift"] == pytest.approx(1.0)


def test_thresholds_filter_rules():
    frequent = apriori(_transactions(), min_support=0.03, max_len=2)
    loose = generate_rules(frequent, 500, min_confidence=0.0, min_lift=1.0)
    strict = generate_rules(frequent, 500, min_confidence=0.6, min_lift=2.0)
    assert len(strict) < len(loose)
    assert (strict["confidence"] >= 0.6).all()
    assert (strict["lift"] >= 2.0).all()


def test_min_antecedent_count_filters_thin_evidence():
    frequent = apriori(_transactions(), min_support=0.03, max_len=3)
    rules = generate_rules(frequent, 500, min_antecedent_count=100)
    assert (rules["antecedent_count"] >= 100).all()


def test_consequent_size_is_capped():
    frequent = apriori(_transactions(), min_support=0.03, max_len=3)
    rules = generate_rules(frequent, 500, max_consequent_size=1)
    assert (rules["consequent_len"] == 1).all()


def test_rules_are_sorted_and_identified():
    frequent = apriori(_transactions(), min_support=0.03, max_len=2)
    rules = generate_rules(frequent, 500)
    assert rules["lift"].is_monotonic_decreasing
    assert rules["rule_id"].is_unique


def test_no_rules_returns_empty_frame_with_schema():
    rules = generate_rules({frozenset({"A"}): 10}, 100)
    assert rules.empty
    assert "confidence" in rules.columns
