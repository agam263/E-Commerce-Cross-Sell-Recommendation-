"""Rule-set metadata, dashboard statistics and evaluation results.

Covers ``GET /config`` from the PRD contract (US-003) plus two convenience
endpoints the React dashboard uses so the overview screen needs one request.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends

from crosssell.api.deps import get_store
from crosssell.api.presenters import histogram, products_to_out, rules_to_out
from crosssell.api.schemas import ConfigResponse, StatsResponse
from crosssell.evaluation import rule_metric_summary
from crosssell.service.store import RuleStore

router = APIRouter(tags=["metadata"])


@router.get("/config", response_model=ConfigResponse, summary="Active rule-set configuration")
def get_active_config(store: RuleStore = Depends(get_store)) -> ConfigResponse:
    manifest = store.manifest
    configuration = manifest.get("configuration", {})
    return ConfigResponse(
        ruleset_version=store.version,
        built_at=manifest.get("built_at"),
        pipeline_version=manifest.get("pipeline_version"),
        config_fingerprint=manifest.get("config_fingerprint"),
        dataset=manifest.get("dataset", {}),
        thresholds=configuration.get("mining", {}),
        recommendation=configuration.get("recommendation", {}),
        preprocessing=configuration.get("preprocessing", {}),
        split=configuration.get("split", {}),
        simulation_defaults=store.artifacts.simulation,
        cohorts=store.cohorts,
        environment=manifest.get("environment", {}),
        reproduce=manifest.get("reproduce", {}),
    )


@router.get("/stats", response_model=StatsResponse, summary="Dashboard KPIs and distributions")
def get_stats(store: RuleStore = Depends(get_store)) -> StatsResponse:
    manifest = store.manifest
    rules = store.artifacts.rules
    itemsets = store.artifacts.itemsets
    evaluation = store.artifacts.evaluation
    data_summary = manifest.get("data_summary", {})
    splits = data_summary.get("splits", {})
    replay = evaluation.get("test", {}).get("replay", {})

    by_length = (
        {str(int(k)): int(v) for k, v in itemsets["length"].value_counts().sort_index().items()}
        if len(itemsets)
        else {}
    )

    kpis: dict[str, Any] = {
        "rules": int(len(rules)),
        "frequent_itemsets": int(len(itemsets)),
        "products_in_rule_set": int(len(store.artifacts.products)),
        "products_with_recommendation": len(store.triggerable_products),
        "training_invoices": splits.get("train", {}).get("invoices"),
        "test_invoices": splits.get("test", {}).get("invoices"),
        "mean_basket_size": data_summary.get("baskets", {}).get("mean_basket_size"),
        "date_min": data_summary.get("baskets", {}).get("date_min"),
        "date_max": data_summary.get("baskets", {}).get("date_max"),
        "avg_confidence": float(rules["confidence"].mean()) if len(rules) else 0.0,
        "avg_lift": float(rules["lift"].mean()) if len(rules) else 0.0,
        "median_support": float(rules["support"].median()) if len(rules) else 0.0,
        "hit_rate_at_k": replay.get("hit_rate_at_k"),
        "popularity_baseline_hit_rate": replay.get("popularity_baseline_hit_rate"),
        "uplift_vs_popularity": replay.get("uplift_vs_popularity"),
        "basket_coverage": replay.get("basket_coverage"),
        "catalog_coverage": evaluation.get("test", {}).get("catalog_coverage", {}).get("coverage"),
        "k": replay.get("k"),
        "rows_in": data_summary.get("cleaning", {}).get("rows_in"),
        "rows_out": data_summary.get("cleaning", {}).get("rows_out"),
        "retention": data_summary.get("cleaning", {}).get("retention"),
    }

    # Headline counts the dashboard leads with. `products_in_rule_set` above is
    # the mined catalog (products that survived the minimum-invoice filter);
    # these two are the totals over the whole cleaned dataset, which is what a
    # business reader means by "how many transactions / products".
    cleaning = data_summary.get("cleaning", {})
    kpis["total_invoices"] = cleaning.get("invoices")
    kpis["catalog_products"] = cleaning.get("products")
    kpis["mined_baskets"] = data_summary.get("baskets", {}).get("invoices")
    kpis["customers"] = cleaning.get("customers")

    # Rules per triggering product: the shape of the coverage, not just its size.
    singles = rules.loc[rules["antecedent_len"] == 1] if len(rules) else rules
    if len(singles):
        per_product = singles["antecedents"].map(lambda a: a[0]).value_counts()
        kpis["rules_per_product"] = {
            "mean": float(per_product.mean()),
            "median": float(per_product.median()),
            "max": int(per_product.max()),
            "products_with_one_rule": int((per_product == 1).sum()),
        }
    else:
        kpis["rules_per_product"] = None

    # 24, not 10: a strong pair produces both A->B and B->A with equal lift,
    # so the dashboard de-duplicates mirrors and needs headroom to still
    # fill its chart.
    top_rules = rules.sort_values(["lift", "confidence"], ascending=False).head(24)
    top_products = (
        store.artifacts.products.loc[
            store.artifacts.products["StockCode"].isin(store.triggerable_products)
        ]
        .sort_values("invoice_count", ascending=False)
        .head(10)
    )

    cohort_stats = {
        cohort: {
            "rules": int(len(frame)),
            "avg_confidence": float(frame["confidence"].mean()) if len(frame) else 0.0,
            "avg_lift": float(frame["lift"].mean()) if len(frame) else 0.0,
            "baskets": manifest.get("mining", {}).get("cohorts", {}).get(cohort, {}).get("baskets"),
        }
        for cohort, frame in store.artifacts.cohort_rules.items()
    }

    return StatsResponse(
        ruleset_version=store.version,
        built_at=manifest.get("built_at"),
        kpis=kpis,
        rule_metric_summary=rule_metric_summary(rules),
        itemsets_by_length=by_length,
        metric_histograms={
            "support": histogram(rules["support"]) if len(rules) else {},
            "confidence": histogram(rules["confidence"], clip_quantile=1.0) if len(rules) else {},
            "lift": histogram(rules["lift"]) if len(rules) else {},
            "basket_size": _basket_size_histogram(data_summary),
        },
        top_rules=rules_to_out(top_rules, store.recommender.names),
        top_products=products_to_out(top_products, store),
        cohorts=cohort_stats,
        evaluation=evaluation,
        simulation_defaults=store.artifacts.simulation,
    )


def _basket_size_histogram(data_summary: dict[str, Any]) -> dict[str, Any]:
    baskets = data_summary.get("baskets", {})
    return {
        "mean": baskets.get("mean_basket_size"),
        "median": baskets.get("median_basket_size"),
        "p95": baskets.get("p95_basket_size"),
        "max": baskets.get("max_basket_size"),
    }


@router.get("/evaluation", summary="Hold-out evaluation results for the active rule set")
def get_evaluation(store: RuleStore = Depends(get_store)) -> dict[str, Any]:
    return {
        "ruleset_version": store.version,
        "evaluation": store.artifacts.evaluation,
        "cleaning_audit": (
            store.artifacts.cleaning_audit.to_dict(orient="records")
            if isinstance(store.artifacts.cleaning_audit, pd.DataFrame)
            else []
        ),
    }
