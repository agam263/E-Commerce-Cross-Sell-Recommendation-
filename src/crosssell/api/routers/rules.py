"""Association-rule browsing (PRD: ``GET /rules``, US-002)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from crosssell.api.deps import get_store
from crosssell.api.presenters import rules_to_out
from crosssell.api.schemas import RuleListResponse
from crosssell.service.store import RuleStore

router = APIRouter(prefix="/rules", tags=["rules"])

SORTABLE = ("lift", "confidence", "support", "leverage", "support_count", "antecedent_count")


@router.get("", response_model=RuleListResponse, summary="Browse and filter association rules")
def list_rules(
    product: str | None = Query(None, description="Only rules involving this StockCode"),
    role: str = Query("any", pattern="^(any|antecedent|consequent)$"),
    min_support: float | None = Query(None, ge=0, le=1),
    min_confidence: float | None = Query(None, ge=0, le=1),
    min_lift: float | None = Query(None, ge=0),
    max_antecedent_len: int | None = Query(None, ge=1),
    search: str | None = Query(None, description="Match product code or name on either side"),
    cohort: str = Query("all", description="all | new | repeat"),
    sort_by: str = Query("lift"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    store: RuleStore = Depends(get_store),
) -> RuleListResponse:
    if sort_by not in SORTABLE:
        raise HTTPException(422, detail=f"sort_by must be one of {list(SORTABLE)}")
    try:
        recommender = store.for_cohort(cohort)
    except KeyError as exc:
        raise HTTPException(404, detail=str(exc)) from exc

    frame = recommender.rules
    names = recommender.names

    if product:
        code = product.strip()
        in_ante = frame["antecedents"].map(lambda a: code in a)
        in_cons = frame["consequents"].map(lambda c: code in c)
        mask = {"antecedent": in_ante, "consequent": in_cons}.get(role, in_ante | in_cons)
        frame = frame.loc[mask]
    if search:
        needle = search.strip().lower()

        def _matches(items) -> bool:
            return any(
                needle in str(i).lower() or needle in names.get(i, "").lower() for i in items
            )

        frame = frame.loc[
            frame["antecedents"].map(_matches) | frame["consequents"].map(_matches)
        ]
    if min_support is not None:
        frame = frame.loc[frame["support"] >= min_support]
    if min_confidence is not None:
        frame = frame.loc[frame["confidence"] >= min_confidence]
    if min_lift is not None:
        frame = frame.loc[frame["lift"] >= min_lift]
    if max_antecedent_len is not None:
        frame = frame.loc[frame["antecedent_len"] <= max_antecedent_len]

    frame = frame.sort_values(sort_by, ascending=(order == "asc"), kind="stable")
    total = int(len(frame))
    page = frame.iloc[offset : offset + limit]

    return RuleListResponse(
        total=total,
        limit=limit,
        offset=offset,
        cohort=cohort,
        ruleset_version=store.version,
        filters={
            "product": product,
            "role": role,
            "search": search,
            "min_support": min_support,
            "min_confidence": min_confidence,
            "min_lift": min_lift,
            "max_antecedent_len": max_antecedent_len,
            "sort_by": sort_by,
            "order": order,
        },
        items=rules_to_out(page, names),
    )
