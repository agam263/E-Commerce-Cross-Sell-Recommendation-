"""Basket construction, cohort labelling and the chronological split."""

from __future__ import annotations

import pandas as pd

from crosssell.config import CohortConfig, PreprocessingConfig, SplitConfig
from crosssell.data.baskets import (
    COHORT_NEW,
    COHORT_REPEAT,
    COHORT_UNKNOWN,
    TransactionSet,
    assign_cohorts,
    build_product_catalog,
    build_transactions,
    split_transactions,
)


def test_quantities_collapse_to_presence(base_config):
    frame = pd.DataFrame(
        {
            "InvoiceNo": ["1", "1", "1", "2", "2"],
            "StockCode": ["A", "A", "B", "A", "C"],
            "Description": ["a", "a", "b", "a", "c"],
            "Quantity": [5, 7, 1, 2, 3],
            "InvoiceDate": pd.to_datetime(["2011-01-01"] * 5),
            "UnitPrice": [1.0] * 5,
            "CustomerID": ["1", "1", "1", "2", "2"],
            "Country": ["UK"] * 5,
            "LineRevenue": [5.0, 7.0, 1.0, 2.0, 3.0],
        }
    )
    ts = build_transactions(frame, base_config.preprocessing, base_config.cohorts)
    assert ts.itemsets[ts.invoice_ids.index("1")] == frozenset({"A", "B"})
    assert len(ts) == 2


def test_single_product_invoices_are_dropped(base_config):
    frame = pd.DataFrame(
        {
            "InvoiceNo": ["1", "2", "2"], "StockCode": ["A", "A", "B"],
            "Description": ["a", "a", "b"], "Quantity": [1, 1, 1],
            "InvoiceDate": pd.to_datetime(["2011-01-01"] * 3), "UnitPrice": [1.0] * 3,
            "CustomerID": ["1", "2", "2"], "Country": ["UK"] * 3,
            "LineRevenue": [1.0] * 3,
        }
    )
    ts = build_transactions(frame, PreprocessingConfig(min_basket_size=2), CohortConfig())
    assert ts.invoice_ids == ["2"], "an invoice with one product carries no co-occurrence"


def test_cohort_labels_use_invoice_sequence_not_hindsight():
    frame = pd.DataFrame(
        {
            "InvoiceNo": ["1", "2", "3", "4"],
            "StockCode": ["A"] * 4,
            "InvoiceDate": pd.to_datetime(["2011-01-01", "2011-02-01", "2011-03-01", "2011-01-05"]),
            "CustomerID": ["c1", "c1", "c1", None],
        }
    )
    cohorts = assign_cohorts(frame, CohortConfig(repeat_min_invoices=2))
    assert cohorts["1"] == COHORT_NEW          # customer's first invoice
    assert cohorts["2"] == COHORT_REPEAT       # second onwards
    assert cohorts["3"] == COHORT_REPEAT
    assert cohorts["4"] == COHORT_UNKNOWN      # no customer id


def test_temporal_split_is_chronological_and_disjoint(transactions):
    cfg = SplitConfig(train_fraction=0.7, validation_fraction=0.15, test_fraction=0.15)
    splits = split_transactions(transactions, cfg)
    assert sum(len(s) for s in splits.values()) == len(transactions)
    ids = [set(s.invoice_ids) for s in splits.values()]
    assert ids[0].isdisjoint(ids[1]) and ids[1].isdisjoint(ids[2])
    dates = {name: part.meta["InvoiceDate"] for name, part in splits.items()}
    assert dates["train"].max() <= dates["validation"].min()
    assert dates["validation"].max() <= dates["test"].min()


def test_restrict_products_reapplies_min_basket_size():
    ts = TransactionSet(
        invoice_ids=["1", "2"],
        itemsets=[frozenset({"A", "B", "C"}), frozenset({"A", "Z"})],
        meta=pd.DataFrame(
            {"InvoiceDate": pd.to_datetime(["2011-01-01", "2011-01-02"]), "n_items": [3, 2]},
            index=pd.Index(["1", "2"], name="InvoiceNo"),
        ),
    )
    restricted = ts.restrict_products({"A", "B"}, min_basket_size=2)
    assert restricted.invoice_ids == ["1"]
    assert restricted.itemsets[0] == frozenset({"A", "B"})


def test_item_counts_and_support(transactions):
    counts = transactions.item_counts()
    support = transactions.item_support()
    assert counts.is_monotonic_decreasing
    assert abs(support.iloc[0] - counts.iloc[0] / len(transactions)) < 1e-12


def test_bool_frame_matches_itemsets(transactions):
    frame = transactions.to_bool_frame()
    assert frame.shape == (len(transactions), transactions.n_items)
    assert frame.to_numpy().sum() == sum(len(s) for s in transactions.itemsets)
    assert frame.dtypes.unique().tolist() == [bool]


def test_catalog_picks_most_common_description():
    frame = pd.DataFrame(
        {
            "InvoiceNo": ["1", "2", "3"], "StockCode": ["A", "A", "A"],
            "Description": ["GOOD NAME", "GOOD NAME", "typo"],
            "Quantity": [1, 1, 1], "InvoiceDate": pd.to_datetime(["2011-01-01"] * 3),
            "UnitPrice": [2.0] * 3, "CustomerID": ["1", "2", "3"], "Country": ["UK"] * 3,
            "LineRevenue": [2.0] * 3,
        }
    )
    catalog = build_product_catalog(frame)
    assert catalog.loc[0, "ProductName"] == "GOOD NAME"
    assert catalog.loc[0, "invoice_count"] == 3
