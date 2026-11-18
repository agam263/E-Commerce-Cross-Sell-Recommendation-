"""Cross-sell recommendations (PRD: ``GET /recommendations/{product_id}``, US-001)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from crosssell.api.deps import get_store
from crosssell.api.presenters import recommendation_to_out
from crosssell.api.schemas import BasketRequest, RecommendationResponse
from crosssell.service.recommender import SOURCE_FALLBACK, UnknownProductError
from crosssell.service.store import RuleStore

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


def _respond(
    store: RuleStore,
    basket: list[str],
    cohort: str,
    top_k: int | None,
    min_confidence: float | None,
    min_lift: float | None,
    allow_fallback: bool | None,
    rank_by: list[str] | None = None,
) -> RecommendationResponse:
    try:
        recommender = store.for_cohort(cohort)
    except KeyError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    try:
        recs = recommender.recommend(
            basket,
            top_k=top_k,
            min_confidence=min_confidence,
            min_lift=min_lift,
            allow_fallback=allow_fallback,
            rank_by=rank_by,
        )
    except UnknownProductError as exc:
        raise HTTPException(
            404,
            detail=(
                f"{exc}. The product is either not in the dataset or was filtered out "
                "before mining (too few invoices). Use /products?search= to find valid ids."
            ),
        ) from exc
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc

    mining_cfg = store.manifest.get("configuration", {}).get("mining", {})
    return RecommendationResponse(
        basket=basket,
        basket_names=[recommender.product_name(p) for p in basket],
        cohort=cohort or "all",
        ruleset_version=recommender.ruleset_version,
        rank_by=list(rank_by or recommender.cfg.rank_by),
        top_k=top_k or recommender.cfg.top_k,
        thresholds={
            "min_confidence": min_confidence,
            "min_lift": min_lift,
            "configured_min_confidence": mining_cfg.get("min_confidence"),
            "configured_min_lift": mining_cfg.get("min_lift"),
        },
        count=len(recs),
        used_fallback=bool(recs) and recs[0].source == SOURCE_FALLBACK,
        recommendations=[recommendation_to_out(r) for r in recs],
    )


@router.get(
    "/{product_id}",
    response_model=RecommendationResponse,
    summary="Ranked cross-sell recommendations for one product",
)
def recommend_for_product(
    product_id: str,
    top_k: int | None = Query(None, ge=1, le=50),
    min_confidence: float | None = Query(None, ge=0, le=1),
    min_lift: float | None = Query(None, ge=0),
    cohort: str = Query("all", description="all | new | repeat"),
    allow_fallback: bool | None = Query(None),
    rank_by: list[str] | None = Query(
        None,
        description=(
            "Ranking order, repeatable: ?rank_by=lift&rank_by=confidence&rank_by=support "
            "reproduces the PRD's lift-first ordering. Omit for the configured default."
        ),
    ),
    store: RuleStore = Depends(get_store),
) -> RecommendationResponse:
    return _respond(
        store,
        [product_id.strip()],
        cohort,
        top_k,
        min_confidence,
        min_lift,
        allow_fallback,
        rank_by,
    )


@router.post(
    "",
    response_model=RecommendationResponse,
    summary="Ranked cross-sell recommendations for a multi-product basket",
)
def recommend_for_basket(
    payload: BasketRequest, store: RuleStore = Depends(get_store)
) -> RecommendationResponse:
    return _respond(
        store,
        payload.products,
        payload.cohort or "all",
        payload.top_k,
        payload.min_confidence,
        payload.min_lift,
        payload.allow_fallback,
        payload.rank_by,
    )
