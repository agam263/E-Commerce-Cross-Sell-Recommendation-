"""Shared fixtures.

Everything here is built from a small synthetic dataset, so the whole suite runs
in seconds and never needs the 23 MB Online Retail file.
"""

from __future__ import annotations

import random
from dataclasses import replace
from datetime import datetime, timedelta

import pandas as pd
import pytest

from crosssell.config import Config
from crosssell.data.baskets import build_product_catalog, build_transactions
from crosssell.data.preprocessing import clean_transactions
from crosssell.service.recommender import Recommender

# Products that genuinely sell together, so the miner has something to find.
PAIRS = [("10001", "10002"), ("10003", "10004"), ("10005", "10006")]
NAMES = {
    "10001": "RED TEACUP",
    "10002": "RED SAUCER",
    "10003": "BLUE LANTERN",
    "10004": "BLUE CANDLE",
    "10005": "PICNIC BASKET",
    "10006": "PICNIC BLANKET",
    "10007": "LONE WOLF MUG",
    "10008": "RARE VASE",
    "10009": "PLAIN NOTEBOOK",
    "10010": "WRAPPING PAPER",
}


def make_raw_frame(n_invoices: int = 400, seed: int = 7) -> pd.DataFrame:
    """A miniature Online Retail file, including every data-quality problem."""
    rng = random.Random(seed)
    start = datetime(2011, 1, 1, 9, 0)
    rows: list[dict] = []
    codes = list(NAMES)

    for i in range(n_invoices):
        invoice = f"5{i:05d}"
        when = start + timedelta(hours=i * 3)
        customer = 10000 + (i % 60)
        basket: set[str] = set()
        for left, right in PAIRS:
            if rng.random() < 0.35:
                basket.add(left)
                if rng.random() < 0.8:
                    basket.add(right)
        while len(basket) < 2:
            basket.add(rng.choice(codes))
        for _ in range(rng.randint(0, 2)):
            basket.add(rng.choice(codes))

        for code in sorted(basket):
            rows.append(
                {
                    "InvoiceNo": invoice,
                    "StockCode": code,
                    "Description": NAMES[code],
                    "Quantity": rng.randint(1, 12),
                    "InvoiceDate": when,
                    "UnitPrice": round(rng.uniform(1.0, 9.5), 2),
                    "CustomerID": float(customer) if i % 11 else None,  # some missing ids
                    "Country": "United Kingdom" if i % 7 else "France",
                }
            )
        # service line that is not a product
        if i % 10 == 0:
            rows.append({
                "InvoiceNo": invoice, "StockCode": "POST", "Description": "POSTAGE",
                "Quantity": 1, "InvoiceDate": when, "UnitPrice": 18.0,
                "CustomerID": float(customer), "Country": "United Kingdom",
            })

    # --- deliberate data-quality problems ---------------------------------
    rows.append(dict(rows[0]))                                   # exact duplicate
    rows.append({**rows[1], "InvoiceNo": "C90001", "Quantity": -4})   # cancellation
    rows.append({**rows[2], "InvoiceNo": "590002", "Quantity": -2})   # bare return
    rows.append({**rows[3], "InvoiceNo": "590003", "UnitPrice": 0.0})  # zero price
    rows.append({**rows[4], "InvoiceNo": "590004", "StockCode": "gift_0001_20"})  # pseudo product
    return pd.DataFrame(rows)


@pytest.fixture(scope="session")
def raw_frame() -> pd.DataFrame:
    return make_raw_frame()


@pytest.fixture(scope="session")
def base_config(tmp_path_factory) -> Config:
    """Config pointed at a temporary workspace, with thresholds a toy set can meet."""
    root = tmp_path_factory.mktemp("workspace")
    cfg = Config.from_dict(
        {
            "project": {"name": "test", "ruleset_version": "auto"},
            "paths": {
                "raw_data": str(root / "raw.csv"),
                "interim_dir": str(root / "interim"),
                "processed_dir": str(root / "processed"),
                "artifacts_dir": str(root / "artifacts"),
                "reports_dir": str(root / "reports"),
            },
            "preprocessing": {
                "non_product_stock_codes": ["POST", "DOT", "M", "BANK CHARGES"],
                "non_product_code_patterns": ["^gift_"],
                "min_basket_size": 2,
                "min_product_invoices": 3,
            },
            "mining": {
                "min_support": 0.02,
                "max_itemset_size": 3,
                "min_confidence": 0.2,
                "min_lift": 1.0,
                "min_antecedent_count": 3,
            },
            "evaluation": {"k": 5, "random_seed": 42, "max_eval_baskets": 500},
            "cohorts": {"enabled": True, "repeat_min_invoices": 2},
        }
    )
    return cfg


@pytest.fixture(scope="session")
def written_raw(base_config: Config, raw_frame: pd.DataFrame) -> Config:
    path = base_config.raw_data_path
    path.parent.mkdir(parents=True, exist_ok=True)
    raw_frame.to_csv(path, index=False)
    return base_config


@pytest.fixture
def cleaned(raw_frame: pd.DataFrame, base_config: Config):
    return clean_transactions(raw_frame, base_config.preprocessing)


@pytest.fixture
def transactions(cleaned, base_config: Config):
    return build_transactions(cleaned.frame, base_config.preprocessing, base_config.cohorts)


@pytest.fixture
def catalog(cleaned):
    return build_product_catalog(cleaned.frame)


@pytest.fixture
def toy_rules() -> pd.DataFrame:
    """Hand-built rule table with known metric values."""
    return pd.DataFrame(
        [
            {
                "rule_id": "R000001", "antecedents": ("A",), "consequents": ("B",),
                "antecedent_len": 1, "consequent_len": 1, "support": 0.20,
                "confidence": 0.80, "lift": 4.0, "leverage": 0.15, "conviction": 4.0,
                "antecedent_support": 0.25, "consequent_support": 0.20,
                "support_count": 20, "antecedent_count": 25, "consequent_count": 20,
            },
            {
                "rule_id": "R000002", "antecedents": ("A",), "consequents": ("C",),
                "antecedent_len": 1, "consequent_len": 1, "support": 0.10,
                "confidence": 0.40, "lift": 8.0, "leverage": 0.08, "conviction": 1.6,
                "antecedent_support": 0.25, "consequent_support": 0.05,
                "support_count": 10, "antecedent_count": 25, "consequent_count": 5,
            },
            {
                "rule_id": "R000003", "antecedents": ("A", "B"), "consequents": ("D",),
                "antecedent_len": 2, "consequent_len": 1, "support": 0.05,
                "confidence": 0.90, "lift": 3.0, "leverage": 0.03, "conviction": 2.0,
                "antecedent_support": 0.055, "consequent_support": 0.30,
                "support_count": 5, "antecedent_count": 6, "consequent_count": 30,
            },
        ]
    )


@pytest.fixture
def toy_catalog() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"StockCode": code, "ProductName": f"PRODUCT {code}", "invoice_count": count,
             "lines": count, "total_quantity": count * 2, "total_revenue": count * 5.0,
             "median_unit_price": 2.5, "avg_line_revenue": 5.0}
            for code, count in [("A", 25), ("B", 20), ("C", 5), ("D", 30), ("E", 40)]
        ]
    )


@pytest.fixture
def toy_popularity() -> pd.Series:
    return pd.Series(
        {"E": 0.40, "D": 0.30, "A": 0.25, "B": 0.20, "C": 0.05}, name="support"
    )


@pytest.fixture
def recommender(toy_rules, toy_catalog, toy_popularity) -> Recommender:
    return Recommender(toy_rules, toy_catalog, toy_popularity, ruleset_version="toy")


@pytest.fixture
def lift_first_recommender(toy_rules, toy_catalog, toy_popularity, base_config) -> Recommender:
    cfg = replace(base_config.recommendation, rank_by=["lift", "confidence", "support"])
    return Recommender(toy_rules, toy_catalog, toy_popularity, cfg=cfg, ruleset_version="toy")
