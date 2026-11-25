"""API integration tests against a real (small) rule set served by FastAPI."""

from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from crosssell.api.main import create_app
from crosssell.config import Config
from crosssell.pipeline import train
from crosssell.service.store import RuleStore


@pytest.fixture(scope="module")
def store(written_raw: Config) -> RuleStore:
    train(written_raw, save_processed=False)
    return RuleStore.from_config(written_raw)


@pytest.fixture(scope="module")
def client(store: RuleStore, written_raw: Config):
    with TestClient(create_app(store=store, config=written_raw)) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def known_product(store: RuleStore) -> str:
    return store.artifacts.rules["antecedents"].iloc[0][0]


# ---------------------------------------------------------------- service --
def test_root_lists_the_contract(client):
    payload = client.get("/").json()
    assert "/health" in payload["endpoints"]
    assert payload["docs"] == "/docs"


def test_health(client, store):
    payload = client.get("/health").json()
    assert payload["status"] == "ok"
    assert payload["ruleset_version"] == store.version
    assert payload["rules_loaded"] > 0
    assert payload["uptime_seconds"] >= 0


def test_openapi_schema_is_served(client):
    schema = client.get("/openapi.json").json()
    for path in ("/health", "/products", "/rules", "/recommendations/{product_id}",
                 "/simulate-revenue", "/config"):
        assert path in schema["paths"], f"{path} missing from the OpenAPI contract"


# --------------------------------------------------------------- products --
def test_list_products(client):
    payload = client.get("/products", params={"limit": 5}).json()
    assert payload["total"] > 0
    assert len(payload["items"]) <= 5
    assert {"stock_code", "product_name", "has_rules"} <= payload["items"][0].keys()


def test_search_products_by_name(client):
    payload = client.get("/products", params={"search": "teacup"}).json()
    assert payload["total"] >= 1
    assert all("TEACUP" in item["product_name"].upper() for item in payload["items"])


def test_filter_products_with_rules(client):
    payload = client.get("/products", params={"only_with_rules": True, "limit": 100}).json()
    assert all(item["has_rules"] for item in payload["items"])


def test_product_pagination_is_stable(client):
    first = client.get("/products", params={"limit": 2, "offset": 0}).json()
    second = client.get("/products", params={"limit": 2, "offset": 2}).json()
    assert first["total"] == second["total"]
    codes = {i["stock_code"] for i in first["items"]} & {i["stock_code"] for i in second["items"]}
    assert not codes


def test_get_single_product(client, known_product):
    payload = client.get(f"/products/{known_product}").json()
    assert payload["stock_code"] == known_product


def test_unknown_product_returns_404(client):
    response = client.get("/products/NOPE")
    assert response.status_code == 404
    assert "NOPE" in response.json()["detail"]


# ------------------------------------------------------------------ rules --
def test_list_rules(client):
    payload = client.get("/rules", params={"limit": 5}).json()
    assert payload["total"] > 0
    rule = payload["items"][0]
    assert {"support", "confidence", "lift", "antecedent_names"} <= rule.keys()
    assert rule["lift"] >= 1.0


def test_rules_sorted_descending_by_lift(client):
    params = {"sort_by": "lift", "order": "desc", "limit": 20}
    items = client.get("/rules", params=params).json()["items"]
    lifts = [i["lift"] for i in items]
    assert lifts == sorted(lifts, reverse=True)


def test_rules_threshold_filters(client):
    items = client.get("/rules", params={"min_confidence": 0.5, "limit": 50}).json()["items"]
    assert all(i["confidence"] >= 0.5 for i in items)


def test_rules_filtered_by_product_and_role(client, known_product):
    payload = client.get(
        "/rules", params={"product": known_product, "role": "antecedent", "limit": 50}
    ).json()
    assert payload["total"] > 0
    assert all(known_product in i["antecedents"] for i in payload["items"])


def test_invalid_sort_column_is_rejected(client):
    assert client.get("/rules", params={"sort_by": "; drop table"}).status_code == 422


def test_unknown_cohort_returns_404(client):
    assert client.get("/rules", params={"cohort": "ghosts"}).status_code == 404


# -------------------------------------------------------- recommendations --
def test_recommendations_for_a_product(client, known_product):
    payload = client.get(f"/recommendations/{known_product}").json()
    assert payload["count"] > 0
    assert payload["basket"] == [known_product]
    first = payload["recommendations"][0]
    assert first["rank"] == 1
    assert first["source"] in {"association_rule", "fallback_popularity"}
    assert first["explanation"]


def test_recommendations_never_include_the_input(client, known_product):
    payload = client.get(f"/recommendations/{known_product}").json()
    assert known_product not in [r["stock_code"] for r in payload["recommendations"]]


def test_recommendations_respect_top_k(client, known_product):
    payload = client.get(f"/recommendations/{known_product}", params={"top_k": 1}).json()
    assert len(payload["recommendations"]) == 1


def test_recommendations_carry_the_ruleset_version(client, known_product, store):
    payload = client.get(f"/recommendations/{known_product}").json()
    assert payload["ruleset_version"] == store.version


def test_recommendations_for_unknown_product_404(client):
    response = client.get("/recommendations/NOT_A_PRODUCT")
    assert response.status_code == 404
    assert "unknown" in response.json()["detail"].lower() or "Unknown" in response.json()["detail"]


def test_basket_recommendations_post(client, store):
    products = list(store.artifacts.rules["antecedents"].iloc[0])
    response = client.post("/recommendations", json={"products": products, "top_k": 3})
    assert response.status_code == 200
    payload = response.json()
    assert payload["basket"] == products
    assert all(r["stock_code"] not in products for r in payload["recommendations"])


def test_empty_basket_is_rejected(client):
    assert client.post("/recommendations", json={"products": []}).status_code == 422


def test_impossible_threshold_returns_fallback_or_nothing(client, known_product):
    payload = client.get(
        f"/recommendations/{known_product}",
        params={"min_confidence": 0.999999, "allow_fallback": False},
    ).json()
    assert payload["count"] == 0
    assert payload["recommendations"] == []


# -------------------------------------------------------------- simulation --
def test_simulate_revenue(client):
    response = client.post(
        "/simulate-revenue",
        json={"eligible_transactions": 1000, "average_order_value": 20.0,
              "scenarios": {"base": 0.05}},
    )
    assert response.status_code == 200
    payload = response.json()
    scenario = payload["scenarios"][0]
    assert scenario["expected_additional_orders"] == pytest.approx(50.0)
    assert scenario["estimated_incremental_revenue"] == pytest.approx(1000.0)
    assert payload["disclaimer"]


def test_simulation_uses_config_defaults_when_scenarios_omitted(client):
    payload = client.post(
        "/simulate-revenue",
        json={"eligible_transactions": 100, "average_order_value": 10.0},
    ).json()
    assert {s["name"] for s in payload["scenarios"]} == {"conservative", "base", "optimistic"}


@pytest.mark.parametrize(
    "payload",
    [
        {"eligible_transactions": -5, "average_order_value": 10.0},
        {"eligible_transactions": 10, "average_order_value": -1.0},
        {"eligible_transactions": 10, "average_order_value": 10.0, "scenarios": {"a": 2.0}},
        {"average_order_value": 10.0},
        {"eligible_transactions": "many", "average_order_value": 10.0},
    ],
)
def test_malformed_simulation_input_is_rejected(client, payload):
    assert client.post("/simulate-revenue", json=payload).status_code == 422


# ---------------------------------------------------------------- metadata --
def test_config_endpoint_exposes_thresholds_and_snapshot(client, store):
    payload = client.get("/config").json()
    assert payload["ruleset_version"] == store.version
    assert payload["thresholds"]["min_support"] > 0
    assert payload["dataset"]["sha256"]
    assert payload["reproduce"]["command"]


def test_stats_endpoint_feeds_the_dashboard(client):
    payload = client.get("/stats").json()
    assert payload["kpis"]["rules"] > 0
    assert payload["metric_histograms"]["lift"]["bins"]
    assert payload["top_rules"] and payload["top_products"]
    assert payload["itemsets_by_length"]


def test_stats_returns_enough_rules_to_survive_mirror_dedup(client):
    """The dashboard drops mirrored rules before charting them.

    A strongly co-occurring pair yields both A->B and B->A with identical lift,
    so the Overview chart keeps one direction per pair. If /stats returned only
    as many rules as the chart draws, that de-duplication would leave the chart
    half empty, so the endpoint deliberately returns a surplus.
    """
    rules = client.get("/stats").json()["top_rules"]
    assert len(rules) > 10

    pairs = {frozenset(r["antecedents"] + r["consequents"]) for r in rules}
    assert len(pairs) >= 6, "too few distinct pairs to fill the overview chart"


def test_evaluation_endpoint(client):
    payload = client.get("/evaluation").json()
    assert payload["evaluation"]["test"]["replay"]["baskets_evaluated"] > 0
    assert payload["cleaning_audit"][0]["stage"] == "raw input"


# -------------------------------------------------------------------- auth --
def test_api_key_is_enforced_when_configured(store, written_raw):
    secured = replace(written_raw, api=replace(written_raw.api, api_key="s3cret"))
    with TestClient(create_app(store=store, config=secured)) as client:
        assert client.get("/health").status_code == 200           # health stays open
        assert client.get("/products").status_code == 401
        assert client.get("/products", headers={"X-API-Key": "wrong"}).status_code == 401
        assert client.get("/products", headers={"X-API-Key": "s3cret"}).status_code == 200


def test_no_auth_required_by_default(client):
    assert client.get("/products").status_code == 200


# ------------------------------------------------------------- insights ----
def test_insights_endpoint_returns_data_backed_records(client):
    payload = client.get("/insights").json()
    assert payload["count"] == len(payload["insights"]) > 0
    for insight in payload["insights"]:
        assert insight["title"] and insight["body"]
        assert insight["kind"] in ("opportunity", "coverage", "risk", "pattern")
        assert insight["metric_format"] in ("number", "percent", "multiple", "currency")


def test_insight_evidence_references_real_products(client):
    """An insight may not cite a product that is not in the catalog."""
    payload = client.get("/insights").json()
    codes = {
        row[key]
        for insight in payload["insights"]
        for row in insight["evidence"]
        for key in ("stock_code", "antecedent", "consequent")
        if key in row
    }
    for code in codes:
        assert client.get(f"/products/{code}").status_code == 200


def test_insights_reject_an_unknown_cohort(client):
    assert client.get("/insights", params={"cohort": "nope"}).status_code == 404


# ----------------------------------------------------- ranking override ----
def test_rank_by_changes_the_order_and_is_echoed(client, known_product):
    lift_first = client.get(
        f"/recommendations/{known_product}",
        params=[("rank_by", "lift"), ("rank_by", "confidence"), ("rank_by", "support")],
    ).json()
    assert lift_first["rank_by"] == ["lift", "confidence", "support"]

    default = client.get(f"/recommendations/{known_product}").json()
    assert default["rank_by"], "the response must always say how it was ranked"

    # Whatever the order, the lift-first result must be sorted by lift.
    lifts = [r["lift"] for r in lift_first["recommendations"] if r["lift"] is not None]
    assert lifts == sorted(lifts, reverse=True)


def test_invalid_rank_by_is_a_422(client, known_product):
    response = client.get(
        f"/recommendations/{known_product}", params={"rank_by": "not_a_metric"}
    )
    assert response.status_code == 422


def test_basket_post_accepts_rank_by(client, known_product):
    response = client.post(
        "/recommendations",
        json={"products": [known_product], "rank_by": ["lift", "confidence", "support"]},
    )
    assert response.status_code == 200
    assert response.json()["rank_by"] == ["lift", "confidence", "support"]


# ----------------------------------------------- product detail on cards ----
def test_recommendations_carry_price_and_category(client, known_product):
    recs = client.get(f"/recommendations/{known_product}").json()["recommendations"]
    assert recs
    for rec in recs:
        assert rec["category"]
        assert rec["median_unit_price"] is not None
        assert rec["invoice_count"] is not None


def test_products_expose_a_derived_category(client):
    items = client.get("/products", params={"limit": 20}).json()["items"]
    assert items
    assert all(item["category"] for item in items)


def test_stats_exposes_headline_business_counts(client):
    kpis = client.get("/stats").json()["kpis"]
    for key in ("total_invoices", "catalog_products", "mined_baskets", "rules_per_product"):
        assert key in kpis
    assert kpis["total_invoices"] >= kpis["mined_baskets"], (
        "baskets are built from invoices, so there cannot be more of them"
    )
    assert kpis["rules_per_product"]["max"] >= kpis["rules_per_product"]["median"]


def test_rules_expose_categories_for_both_sides(client):
    """The Rule Explorer picks a product image from the rule's categories.

    Without these the rule table has no way to choose an image, because a rule
    carries codes and names but not the derived category.
    """
    rules = client.get("/rules", params={"limit": 5}).json()["items"]
    assert rules
    for rule in rules:
        assert len(rule["antecedent_categories"]) == len(rule["antecedents"])
        assert len(rule["consequent_categories"]) == len(rule["consequents"])
        assert all(rule["antecedent_categories"])
        assert all(rule["consequent_categories"])


def test_rule_categories_agree_with_the_product_endpoint(client):
    """A product must not be in one category in /rules and another in /products."""
    rule = client.get("/rules", params={"limit": 1}).json()["items"][0]
    code = rule["antecedents"][0]
    product = client.get(f"/products/{code}").json()
    assert rule["antecedent_categories"][0] == product["category"]


# -------------------------------------------------------------------- cors --
def test_cors_env_allows_deployed_frontend_origins(monkeypatch, store, written_raw):
    monkeypatch.setenv("CROSSSELL_CORS_ORIGINS", "https://custom.example.com/")
    monkeypatch.setenv("CROSSSELL_CORS_ORIGIN_REGEX", r"^https://.*\.vercel\.app$")
    with TestClient(create_app(store=store, config=written_raw)) as client:
        for origin in ("https://custom.example.com", "https://crosssell-ui.vercel.app"):
            res = client.options(
                "/health",
                headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
            )
            assert res.status_code == 200
            assert res.headers.get("access-control-allow-origin") == origin
            assert res.headers.get("access-control-allow-credentials") == "true"


def test_cors_wildcard_disables_credentials(monkeypatch, store, written_raw):
    monkeypatch.setenv("CROSSSELL_CORS_ORIGINS", "*")
    with TestClient(create_app(store=store, config=written_raw)) as client:
        res = client.options(
            "/health",
            headers={"Origin": "https://anywhere.example", "Access-Control-Request-Method": "GET"},
        )
        assert res.status_code == 200
        assert res.headers.get("access-control-allow-origin") == "*"
        assert "access-control-allow-credentials" not in res.headers
