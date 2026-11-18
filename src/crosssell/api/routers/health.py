"""Service health check (PRD: ``GET /health``)."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends

from crosssell import __version__
from crosssell.api.deps import get_started_at, get_store
from crosssell.api.schemas import HealthResponse
from crosssell.service.store import RuleStore

router = APIRouter(tags=["service"])


@router.get("/health", response_model=HealthResponse, summary="Service health check")
def health(
    store: RuleStore = Depends(get_store),
    started_at: float = Depends(get_started_at),
) -> HealthResponse:
    return HealthResponse(
        status="ok",
        ruleset_version=store.version,
        rules_loaded=len(store.recommender),
        products_loaded=int(len(store.artifacts.products)),
        cohorts=store.cohorts,
        uptime_seconds=round(time.time() - started_at, 3),
        api_version=__version__,
    )
