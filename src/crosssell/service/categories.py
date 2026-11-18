"""Derive a product category from its name.

The Online Retail dataset carries no category column and no product images --
it is invoice lines and free-text descriptions. The dashboard still needs a way
to show a product as something other than a code, and a category is a useful
merchandising dimension, so one is *derived* here from keywords in the product
name.

This is a presentation-layer convenience and nothing else:

* it never feeds mining, ranking or evaluation -- the rules are built from
  StockCodes alone, exactly as before;
* it is deterministic and dependency-free, so the same name always yields the
  same category;
* everything that fails to match is reported as ``Uncategorised`` rather than
  being forced into the nearest bucket.

The UI labels these as derived from the product name. They are a reading aid,
not a claim about the retailer's own taxonomy.

Ordering matters: the first category whose pattern matches wins. Seasonal lines
are tested first because for a gift wholesaler "CHRISTMAS" is a stronger
merchandising signal than the object itself -- a Christmas candle belongs with
the Christmas range, not with the candles.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

UNCATEGORISED = "Uncategorised"


@dataclass(frozen=True)
class Category:
    """A derived category plus the icon the dashboard should draw for it."""

    name: str
    icon: str
    keywords: tuple[str, ...]


# Keywords are matched whole-word against the upper-cased product name, in this
# order. They were chosen from the actual token frequencies in the shipped
# catalog, not invented.
CATEGORIES: tuple[Category, ...] = (
    Category("Christmas & Seasonal", "pine-tree", (
        "CHRISTMAS", "XMAS", "ADVENT", "SANTA", "REINDEER", "SNOWFLAKE", "SNOWMAN",
        "EASTER", "HALLOWEEN", "VALENTINE",
    )),
    Category("Party & Celebration", "party-popper", (
        "PARTY", "BUNTING", "BALLOON", "BALLOONS", "CONFETTI", "BIRTHDAY", "GARLAND",
    )),
    Category("Bags & Totes", "shopping-bag", (
        "BAG", "BAGS", "TOTE", "SHOPPER", "SATCHEL", "RUCKSACK",
    )),
    Category("Candles & Lighting", "flame", (
        "CANDLE", "CANDLES", "CANDLEHOLDER", "TLIGHT", "LANTERN", "LAMP", "NIGHTLIGHT",
        "TEALIGHT", "LIGHT", "LIGHTS", "LED",
    )),
    Category("Kitchen & Dining", "utensils", (
        "MUG", "BOWL", "PLATE", "PLATES", "CUP", "CUPS", "SAUCER", "TEAPOT", "JUG",
        "CUTLERY", "BAKING", "APRON", "TRAY", "COASTER", "COASTERS", "BOTTLE",
        "FLASK", "NAPKIN", "NAPKINS", "CAKESTAND", "CAKE", "TEASPOON", "SPOON",
        "FORK", "KNIFE", "TEA", "COFFEE", "EGG", "LUNCH", "COOKIE", "CUTTER",
        "CUTTERS", "MOULD", "MOULDS", "SCALES", "JELLY", "JAM", "PANTRY", "BOWLS",
        "MUGS", "BISCUIT",
    )),
    Category("Storage & Containers", "package", (
        "BOX", "BOXES", "TIN", "TINS", "JAR", "JARS", "CRATE", "BASKET", "CADDY",
        "CANISTER", "DRAWER", "HOLDER", "RACK",
    )),
    Category("Stationery & Paper", "notebook-pen", (
        "CARD", "CARDS", "NOTEBOOK", "PEN", "PENS", "PENCIL", "PENCILS", "ERASER",
        "STICKER", "STICKERS", "WRAP", "ENVELOPE", "ENVELOPES", "PAPER", "NOTES",
        "CHALKBOARD", "JOURNAL",
    )),
    Category("Jewellery & Accessories", "gem", (
        "BRACELET", "NECKLACE", "EARRINGS", "EARRING", "RING", "BROOCH", "PURSE",
        "SCARF", "UMBRELLA", "HAIRCLIP", "JEWELLERY", "BEADS", "PENDANT", "HAIR",
    )),
    Category("Toys & Games", "gamepad-2", (
        "TOY", "TOYS", "GAME", "GAMES", "PUZZLE", "DOLL", "SKITTLES", "JIGSAW",
        "BINGO", "PLAYHOUSE", "SPACEBOY", "SOLDIER",
    )),
    Category("Garden & Outdoor", "sprout", (
        "GARDEN", "PLANT", "WATERING", "TROWEL", "BIRD", "BIRDS", "WINDMILL",
        "PARASOL", "DOORMAT", "FLOWERPOT", "SEEDS", "GARDENERS",
    )),
    Category("Home Decor", "home", (
        "HEART", "HEARTS", "HANGING", "DECORATION", "DECORATIONS", "ORNAMENT",
        "SIGN", "MIRROR", "FRAME", "CUSHION", "CLOCK", "VASE", "DOORSTOP", "HOOK",
        "HOOKS", "CANDLEPOT", "STAR", "BLOCK", "LETTERS", "DOORKNOB", "MAGNET",
        "MAGNETS", "ART", "CABINET", "BUTTERFLY", "FLOWER", "FLOWERS", "WALL",
    )),
    Category("Textiles & Soft Goods", "shirt", (
        "TOWEL", "BLANKET", "THROW", "APRONS", "CUSHIONS", "FELT", "RIBBON",
        "GLOVES", "SLIPPER", "SLIPPERS", "RIBBONS", "COVER", "COVERS",
    )),
)

_COMPILED: tuple[tuple[Category, re.Pattern[str]], ...] = tuple(
    (c, re.compile(r"\b(?:" + "|".join(re.escape(k) for k in c.keywords) + r")\b"))
    for c in CATEGORIES
)

#: Every category the dashboard can render, including the explicit fallback.
CATEGORY_NAMES: tuple[str, ...] = tuple(c.name for c in CATEGORIES) + (UNCATEGORISED,)

ICONS: dict[str, str] = {c.name: c.icon for c in CATEGORIES} | {UNCATEGORISED: "box"}


def categorise(product_name: str | None) -> str:
    """Return the derived category for ``product_name``.

    Falls back to :data:`UNCATEGORISED` rather than guessing, so the dashboard
    can show honestly that nothing was derived.
    """
    if not product_name:
        return UNCATEGORISED
    haystack = str(product_name).upper()
    for category, pattern in _COMPILED:
        if pattern.search(haystack):
            return category.name
    return UNCATEGORISED


def category_icon(category: str) -> str:
    """Icon name the frontend should draw for ``category``."""
    return ICONS.get(category, "box")
