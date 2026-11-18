"""Derived business insights.

The point of these tests is that an insight can never state something the data
does not support: the numbers in the prose must come from the rule table, and
an insight with no evidence must be omitted rather than padded.
"""

from __future__ import annotations

import pandas as pd

from crosssell.service.insights import (
    build_insights,
    category_mix,
    cross_sell_hubs,
    strongest_pairs,
    thin_coverage,
)


def _names() -> dict[str, str]:
    return {
        "A": "JUMBO BAG RED RETROSPOT",
        "B": "LUNCH BAG RED RETROSPOT",
        "C": "WHITE HANGING HEART T-LIGHT HOLDER",
        "D": "REGENCY CAKESTAND 3 TIER",
    }


def _mirrored_rules() -> pd.DataFrame:
    """A->B and B->A (same pair), plus two unrelated one-way rules."""
    return pd.DataFrame(
        [
            {"rule_id": "R1", "antecedents": ("A",), "consequents": ("B",), "antecedent_len": 1,
             "support": 0.20, "confidence": 0.80, "lift": 9.0, "support_count": 20},
            {"rule_id": "R2", "antecedents": ("B",), "consequents": ("A",), "antecedent_len": 1,
             "support": 0.20, "confidence": 0.60, "lift": 9.0, "support_count": 20},
            {"rule_id": "R3", "antecedents": ("A",), "consequents": ("C",), "antecedent_len": 1,
             "support": 0.10, "confidence": 0.40, "lift": 4.0, "support_count": 10},
            {"rule_id": "R4", "antecedents": ("D",), "consequents": ("C",), "antecedent_len": 1,
             "support": 0.05, "confidence": 0.30, "lift": 2.0, "support_count": 5},
        ]
    )


def test_strongest_pairs_keeps_one_direction_per_pair():
    insight = strongest_pairs(_mirrored_rules(), _names())
    pairs = {frozenset((e["antecedent"], e["consequent"])) for e in insight.evidence}
    assert len(pairs) == len(insight.evidence), "a mirrored rule was reported twice"
    # of A->B / B->A it keeps the higher-confidence direction
    top = insight.evidence[0]
    assert (top["antecedent"], top["consequent"]) == ("A", "B")


def test_strongest_pairs_quotes_a_real_lift():
    frame = _mirrored_rules()
    insight = strongest_pairs(frame, _names())
    assert insight.metric_value == frame["lift"].max()
    assert f"{frame['lift'].max():.0f}x" in insight.body


def test_cross_sell_hubs_counts_outgoing_rules():
    insight = cross_sell_hubs(_mirrored_rules(), _names())
    top = insight.evidence[0]
    assert top["stock_code"] == "A"  # A is the antecedent of two rules
    assert top["rule_count"] == 2
    assert insight.metric_value == 2


def test_thin_coverage_finds_products_with_exactly_one_rule():
    insight = thin_coverage(_mirrored_rules(), _names())
    codes = {e["stock_code"] for e in insight.evidence}
    assert codes == {"B", "D"}  # A has two rules, so it is not fragile
    assert insight.kind == "risk"


def test_category_mix_ignores_uncategorisable_sides():
    """A pair is only counted when both sides have a derived category."""
    frame = pd.DataFrame(
        [
            {"rule_id": "R1", "antecedents": ("A",), "consequents": ("Z",), "antecedent_len": 1,
             "support": 0.2, "confidence": 0.8, "lift": 9.0, "support_count": 20},
        ]
    )
    names = {"A": "JUMBO BAG RED RETROSPOT", "Z": "ZZZZ UNMATCHABLE WIDGET"}
    assert category_mix(frame, names) is None


def test_category_mix_reports_a_real_share():
    insight = category_mix(_mirrored_rules(), _names())
    assert 0.0 <= insight.metric_value <= 1.0
    assert insight.metric_format == "percent"


def test_insights_are_omitted_rather_than_invented_when_there_are_no_rules():
    empty = pd.DataFrame(
        columns=["rule_id", "antecedents", "consequents", "antecedent_len",
                 "support", "confidence", "lift", "support_count"]
    )
    produced = build_insights(empty, _names(), triggerable=0, catalog_size=0)
    assert produced == []


def test_build_insights_returns_well_formed_records():
    produced = build_insights(
        _mirrored_rules(), _names(), triggerable=3, catalog_size=4, basket_coverage=0.9
    )
    assert produced
    for insight in produced:
        assert insight.id and insight.title and insight.body
        assert insight.kind in ("opportunity", "coverage", "risk", "pattern")
        assert insight.metric_format in ("number", "percent", "multiple", "currency")
        assert isinstance(insight.metric_value, float)


def test_coverage_insight_uses_the_real_ratio():
    produced = build_insights(_mirrored_rules(), _names(), triggerable=3, catalog_size=4)
    coverage = next(i for i in produced if i.id == "catalog-coverage")
    assert coverage.metric_value == 0.75
    assert "3 of 4" in coverage.body
