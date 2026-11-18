"""Derived business insights for the dashboard (``GET /insights``).

Thin wrapper over :mod:`crosssell.service.insights`. Everything returned is
computed from the active rule set; nothing is hard-coded.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from crosssell.api.deps import get_store
from crosssell.api.schemas import InsightListResponse, InsightOut
from crosssell.service.insights import build_insights
from crosssell.service.store import RuleStore

router = APIRouter(tags=["insights"])


@router.get(
    "/insights",
    response_model=InsightListResponse,
    summary="Business insights derived from the active rule set",
)
def list_insights(
    cohort: str = Query("all", description="all | new | repeat"),
    store: RuleStore = Depends(get_store),
) -> InsightListResponse:
    try:
        recommender = store.for_cohort(cohort)
    except KeyError as exc:
        raise HTTPException(404, detail=str(exc)) from exc

    evaluation = store.manifest.get("evaluation", {}) or {}
    basket_coverage = evaluation.get("basket_coverage")

    insights = build_insights(
        rules=recommender.rules,
        names=recommender.names,
        triggerable=len(store.triggerable_products),
        catalog_size=int(len(store.artifacts.products)),
        basket_coverage=float(basket_coverage) if basket_coverage is not None else None,
    )
    return InsightListResponse(
        ruleset_version=recommender.ruleset_version,
        cohort=cohort or "all",
        count=len(insights),
        insights=[InsightOut(**i.to_dict()) for i in insights],
    )
