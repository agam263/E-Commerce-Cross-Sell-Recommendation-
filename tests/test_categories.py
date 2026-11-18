"""The derived product-category map.

These categories exist only so the dashboard can show a product as something
other than a code. They must be deterministic, must never silently reclassify,
and must say "Uncategorised" rather than guess.
"""

from __future__ import annotations

import pytest

from crosssell.service.categories import (
    CATEGORY_NAMES,
    UNCATEGORISED,
    categorise,
    category_icon,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("WHITE HANGING HEART T-LIGHT HOLDER", "Candles & Lighting"),
        ("JUMBO BAG RED RETROSPOT", "Bags & Totes"),
        ("REGENCY CAKESTAND 3 TIER", "Kitchen & Dining"),
        ("PARTY BUNTING", "Party & Celebration"),
        ("CHRISTMAS GINGHAM TREE", "Christmas & Seasonal"),
        ("SET OF 3 CAKE TINS PANTRY DESIGN", "Kitchen & Dining"),
        ("VICTORIAN GLASS HANGING T-LIGHT", "Candles & Lighting"),
        ("PACK OF 72 RETROSPOT CAKE CASES", "Kitchen & Dining"),
    ],
)
def test_known_products_land_in_the_expected_category(name, expected):
    assert categorise(name) == expected


def test_seasonal_wins_over_the_object_itself():
    """A Christmas candle belongs with the Christmas range.

    Precedence is deliberate and documented: for a gift wholesaler the season
    is the stronger merchandising signal than the object type.
    """
    assert categorise("CHRISTMAS CANDLE") == "Christmas & Seasonal"
    assert categorise("CANDLE") == "Candles & Lighting"


def test_unmatched_names_are_reported_not_guessed():
    assert categorise("ZZZZ UNMATCHABLE WIDGET") == UNCATEGORISED
    assert categorise("") == UNCATEGORISED
    assert categorise(None) == UNCATEGORISED


def test_matching_is_whole_word():
    """'CARD' must not match inside 'CARDIGAN'.

    Substring matching would drag unrelated products into Stationery; the
    patterns are anchored to word boundaries to stop that.
    """
    assert categorise("WOOLLEN CARDIGAN") == UNCATEGORISED
    assert categorise("THANK YOU CARDS") == "Stationery & Paper"


def test_earlier_categories_take_precedence():
    """Precedence is part of the contract, not an accident of ordering.

    'BIRTHDAY CARD' is party merchandise before it is stationery, and the
    ordering in CATEGORIES is what decides that.
    """
    assert categorise("BIRTHDAY CARD") == "Party & Celebration"


def test_categorisation_is_case_insensitive_and_stable():
    variants = (
        "jumbo bag red retrospot",
        "JUMBO BAG RED RETROSPOT",
        "Jumbo Bag Red Retrospot",
    )
    for variant in variants:
        assert categorise(variant) == "Bags & Totes"


def test_every_category_has_an_icon():
    for name in CATEGORY_NAMES:
        assert category_icon(name)
    assert category_icon("not a category") == "box"


def test_uncategorised_is_part_of_the_published_list():
    assert CATEGORY_NAMES[-1] == UNCATEGORISED
