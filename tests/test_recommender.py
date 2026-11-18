"""Serving behaviour: what gets recommended, in what order, and what happens
when nothing qualifies."""

from __future__ import annotations

import pytest

from crosssell.service.recommender import (
    SOURCE_FALLBACK,
    SOURCE_RULE,
    Recommender,
    UnknownProductError,
)


def test_recommends_rule_consequents(recommender):
    recs = recommender.recommend(["A"])
    assert {r.stock_code for r in recs} == {"B", "C"}
    assert all(r.source == SOURCE_RULE for r in recs)


def test_never_recommends_a_product_already_in_the_basket(recommender):
    recs = recommender.recommend(["A", "B"])
    codes = {r.stock_code for r in recs}
    assert "A" not in codes and "B" not in codes


def test_multi_item_antecedent_fires_only_when_fully_contained(recommender):
    assert "D" not in {r.stock_code for r in recommender.recommend(["A"])}
    assert "D" in {r.stock_code for r in recommender.recommend(["A", "B"])}


def test_default_ranking_is_confidence_first(recommender):
    recs = recommender.recommend(["A"])
    assert [r.stock_code for r in recs] == ["B", "C"]  # confidence 0.80 > 0.40
    assert recs[0].rank == 1 and recs[1].rank == 2


def test_lift_first_ranking_is_configurable(lift_first_recommender):
    recs = lift_first_recommender.recommend(["A"])
    assert [r.stock_code for r in recs] == ["C", "B"]  # lift 8.0 > 4.0


def test_top_k_limits_results(recommender):
    assert len(recommender.recommend(["A"], top_k=1)) == 1


def test_serving_thresholds_filter_without_remining(recommender):
    assert {r.stock_code for r in recommender.recommend(["A"], min_confidence=0.5)} == {"B"}
    assert {r.stock_code for r in recommender.recommend(["A"], min_lift=5.0)} == {"C"}


def test_unknown_product_raises(recommender):
    with pytest.raises(UnknownProductError, match="ZZZZ"):
        recommender.recommend(["ZZZZ"])


def test_empty_basket_raises(recommender):
    with pytest.raises(ValueError):
        recommender.recommend([])


def test_popularity_fallback_when_no_rule_fires(recommender):
    recs = recommender.recommend(["E"])  # E appears in no rule
    assert recs and all(r.source == SOURCE_FALLBACK for r in recs)


def test_fallback_never_fabricates_rule_metrics(recommender):
    rec = recommender.recommend(["E"])[0]
    assert rec.confidence is None and rec.lift is None and rec.support is None
    assert rec.popularity_support is not None
    assert "fallback" in rec.explanation.lower()


def test_fallback_can_be_disabled(recommender):
    assert recommender.recommend(["E"], allow_fallback=False) == []


def test_fallback_excludes_basket_items(recommender):
    recs = recommender.recommend(["E"])
    assert "E" not in {r.stock_code for r in recs}


def test_every_rule_recommendation_carries_its_evidence(recommender):
    for rec in recommender.recommend(["A"]):
        assert rec.rule_id and rec.antecedents
        assert rec.support_count and rec.antecedent_count
        assert "%" in rec.explanation and "invoices" in rec.explanation


def test_best_rule_wins_per_consequent(toy_rules, toy_catalog, toy_popularity):
    """Two rules recommending the same product: the stronger one must be kept."""
    duplicated = toy_rules.copy()
    weaker = duplicated.iloc[0].copy()
    weaker["rule_id"] = "R000099"
    weaker["confidence"] = 0.10
    weaker["lift"] = 1.1
    duplicated.loc[len(duplicated)] = weaker
    rec = Recommender(duplicated, toy_catalog, toy_popularity, ruleset_version="toy")
    chosen = next(r for r in rec.recommend(["A"]) if r.stock_code == "B")
    assert chosen.rule_id == "R000001"


def test_rules_for_product_by_role(recommender):
    assert len(recommender.rules_for("A", role="antecedent")) == 3
    assert len(recommender.rules_for("B", role="consequent")) == 1
    with pytest.raises(ValueError):
        recommender.rules_for("A", role="nonsense")


def test_coverage_counts_products_with_rules(recommender):
    """Only "A" fires a rule on its own: ("A","B") -> D needs both items present."""
    coverage = recommender.coverage()
    assert coverage["products_tested"] == 5
    assert coverage["products_with_recommendation"] == 1
    assert coverage["coverage"] == pytest.approx(1 / 5)


def test_candidate_rules_requires_full_antecedent_containment(recommender):
    assert len(recommender.candidate_rules({"A"})) == 2
    assert len(recommender.candidate_rules({"A", "B"})) == 3
    assert recommender.candidate_rules({"E"}) == []


# ------------------------------------------------- per-request rank order --
def test_rank_by_override_reproduces_lift_first_ordering(recommender, lift_first_recommender):
    """A request may reorder without re-mining.

    The default recommender ranks confidence-first; asking it for lift-first
    must produce exactly what a lift-first-configured recommender produces.
    That is what lets the dashboard show the PRD's ordering beside the tuned
    one without shipping two rule sets.
    """
    default = [r.stock_code for r in recommender.recommend(["A"])]
    overridden = [
        r.stock_code
        for r in recommender.recommend(["A"], rank_by=["lift", "confidence", "support"])
    ]
    configured = [r.stock_code for r in lift_first_recommender.recommend(["A"])]

    assert overridden == configured
    assert overridden != default, "fixture no longer distinguishes the two orderings"


def test_rank_by_override_does_not_leak_into_later_calls(recommender):
    before = [r.stock_code for r in recommender.recommend(["A"])]
    recommender.recommend(["A"], rank_by=["lift"])
    assert [r.stock_code for r in recommender.recommend(["A"])] == before


def test_score_follows_the_ranking_metric_actually_used(recommender):
    by_lift = recommender.recommend(["A"], rank_by=["lift"])
    assert by_lift[0].score == pytest.approx(by_lift[0].lift)

    by_confidence = recommender.recommend(["A"], rank_by=["confidence"])
    assert by_confidence[0].score == pytest.approx(by_confidence[0].confidence)


@pytest.mark.parametrize("bad", [["nonsense"], ["lift", "lift"], ["Lift", "lift"]])
def test_invalid_rank_by_is_rejected(recommender, bad):
    with pytest.raises(ValueError):
        recommender.recommend(["A"], rank_by=bad)


def test_empty_rank_by_falls_back_to_the_configured_order(recommender):
    assert [r.stock_code for r in recommender.recommend(["A"], rank_by=[])] == [
        r.stock_code for r in recommender.recommend(["A"])
    ]


# ------------------------------------------------------ product economics --
def test_recommendations_carry_price_and_category(recommender):
    """The product cards need a price and a category, not just metrics."""
    rec = recommender.recommend(["A"])[0]
    assert rec.median_unit_price == pytest.approx(2.5)
    assert rec.invoice_count is not None and rec.invoice_count > 0
    assert rec.category  # derived from the name, never blank


def test_fallback_recommendations_also_carry_product_details(recommender):
    """A fallback is still a product; it just has no rule metrics."""
    recs = recommender.recommend(["E"], allow_fallback=True)
    assert recs and recs[0].source == "fallback_popularity"
    assert recs[0].median_unit_price is not None
    assert recs[0].category
    assert recs[0].confidence is None and recs[0].lift is None
