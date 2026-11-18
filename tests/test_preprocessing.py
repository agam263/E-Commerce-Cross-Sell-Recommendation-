"""The cleaning policy is a modelling decision, so each rule gets a test."""

from __future__ import annotations

import pandas as pd
import pytest

from crosssell.config import PreprocessingConfig
from crosssell.data.loader import standardise_columns
from crosssell.data.preprocessing import (
    clean_transactions,
    is_cancellation,
    non_product_mask,
    validate_clean,
)


def test_cancellations_are_detected():
    series = pd.Series(["536365", "C536379", "c536380", None], dtype="string")
    assert is_cancellation(series).tolist() == [False, True, True, False]


def test_non_product_codes_match_list_and_patterns():
    cfg = PreprocessingConfig(
        non_product_stock_codes=["POST", "BANK CHARGES"],
        non_product_code_patterns=["^gift_"],
    )
    codes = pd.Series(["85123A", "POST", "post", "BANK CHARGES", "gift_0001_20", "21730"],
                      dtype="string")
    assert non_product_mask(codes, cfg).tolist() == [False, True, True, True, True, False]


def test_cleaning_removes_each_problem_class(raw_frame, base_config):
    result = clean_transactions(raw_frame, base_config.preprocessing)
    frame = result.frame

    assert not frame.duplicated().any()
    assert not is_cancellation(frame["InvoiceNo"]).any()
    assert (frame["Quantity"] > 0).all()
    assert (frame["UnitPrice"] > 0).all()
    assert "POST" not in set(frame["StockCode"])
    assert not frame["StockCode"].str.startswith("gift_").any()


def test_audit_accounts_for_every_removed_row(raw_frame, base_config):
    result = clean_transactions(raw_frame, base_config.preprocessing)
    audit = result.audit
    assert audit["rows_remaining"].iloc[0] == len(raw_frame)
    assert audit["rows_remaining"].iloc[-1] == len(result.frame)
    # each stage's remaining = previous remaining - removed
    for i in range(1, len(audit)):
        expected = audit["rows_remaining"].iloc[i - 1] - audit["rows_removed"].iloc[i]
        assert audit["rows_remaining"].iloc[i] == expected


def test_missing_customer_id_rows_are_kept_by_default(raw_frame, base_config):
    result = clean_transactions(raw_frame, base_config.preprocessing)
    assert result.frame["CustomerID"].isna().any(), "a basket is valid without a customer id"


def test_dropping_missing_customer_id_is_opt_in(raw_frame, base_config):
    cfg = PreprocessingConfig(
        **{**base_config.preprocessing.__dict__, "drop_missing_customer_id": True}
    )
    result = clean_transactions(raw_frame, cfg)
    assert result.frame["CustomerID"].notna().all()


def test_line_revenue_is_consistent(raw_frame, base_config):
    result = clean_transactions(raw_frame, base_config.preprocessing)
    expected = result.frame["Quantity"] * result.frame["UnitPrice"]
    pd.testing.assert_series_equal(
        result.frame["LineRevenue"], expected, check_names=False
    )


def test_validation_passes_on_cleaned_output(raw_frame, base_config):
    result = clean_transactions(raw_frame, base_config.preprocessing)
    checks = validate_clean(result.frame, base_config.preprocessing)
    assert all(checks.values()), [name for name, ok in checks.items() if not ok]


def test_country_filter(raw_frame, base_config):
    cfg = PreprocessingConfig(
        **{**base_config.preprocessing.__dict__, "country": "France"}
    )
    result = clean_transactions(raw_frame, cfg)
    assert set(result.frame["Country"]) == {"France"}


def test_schema_aliases_are_normalised():
    frame = pd.DataFrame(
        {
            " Invoice No ": ["1"], "stock_code": ["A"], "DESCRIPTION": ["x"],
            "Qty": [1], "invoice date": ["2011-01-01"], "Unit Price": [1.0],
            "customer id": [1.0], "country": ["UK"],
        }
    )
    out = standardise_columns(frame)
    assert list(out.columns) == [
        "InvoiceNo", "StockCode", "Quantity", "InvoiceDate", "UnitPrice",
        "Description", "CustomerID", "Country",
    ]


def test_missing_required_column_raises():
    with pytest.raises(ValueError, match="Missing required column"):
        standardise_columns(pd.DataFrame({"InvoiceNo": ["1"], "StockCode": ["A"]}))


def test_optional_columns_are_created_when_absent():
    frame = pd.DataFrame(
        {"InvoiceNo": ["1"], "StockCode": ["A"], "Quantity": [1],
         "InvoiceDate": ["2011-01-01"], "UnitPrice": [1.0]}
    )
    out = standardise_columns(frame)
    assert out["Description"].isna().all()
