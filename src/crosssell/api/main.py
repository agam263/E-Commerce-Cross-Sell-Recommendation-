"""FastAPI application factory.

The rule set is loaded once at startup and held in ``app.state`` -- requests
never touch the raw dataset, which keeps responses fast and guarantees every
answer in a session comes from the same ``ruleset_version`` (PRD US-003/US-007).
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from crosssell import __version__
from crosssell.api.deps import load_app_config, load_store, require_api_key
from crosssell.api.routers import (
    health,
    insights,
    meta,
    products,
    recommendations,
    rules,
    simulation,
)
from crosssell.service.recommender import UnknownProductError

log = logging.getLogger(__name__)

DESCRIPTION = """
Cross-sell recommendation engine built on **Apriori association-rule mining** over the
Online Retail dataset.

* `/products` - search the catalog
* `/recommendations/{product_id}` - ranked cross-sell suggestions with the rule behind each one
* `/rules` - browse support / confidence / lift
* `/simulate-revenue` - revenue-impact scenarios under explicit assumptions
* `/config` - active rule-set version, thresholds and dataset snapshot

Recommendations describe **historical co-occurrence**, not guaranteed future purchases,
and simulated revenue is a planning estimate, never measured uplift.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.started_at = time.time()
    app.state.config = getattr(app.state, "config", None) or load_app_config()
    if getattr(app.state, "store", None) is None:
        try:
            app.state.store = load_store(app.state.config)
        except FileNotFoundError as exc:
            app.state.store = None
            log.error("Startup without a rule set: %s", exc)
    yield


def create_app(store: Any = None, config: Any = None) -> FastAPI:
    """Build the application. Tests inject a pre-built ``store``/``config``."""
    app = FastAPI(
        title="Cross-Sell Recommendation Engine API",
        description=DESCRIPTION,
        version=__version__,
        lifespan=lifespan,
        contact={"name": "Cross-Sell Engine"},
        license_info={"name": "MIT"},
    )
    app.state.store = store
    app.state.config = config
    cors = (config or load_app_config()).api.cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(UnknownProductError)
    async def _unknown_product(_: Request, exc: UnknownProductError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={
                "error": "unknown_product",
                "detail": str(exc),
                "hint": "Use /products?search=... to find a valid StockCode.",
            },
        )

    @app.exception_handler(ValueError)
    async def _bad_value(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_request", "detail": str(exc), "hint": None},
        )

    guarded = [Depends(require_api_key)]
    app.include_router(health.router)
    app.include_router(products.router, dependencies=guarded)
    app.include_router(rules.router, dependencies=guarded)
    app.include_router(recommendations.router, dependencies=guarded)
    app.include_router(simulation.router, dependencies=guarded)
    app.include_router(meta.router, dependencies=guarded)
    app.include_router(insights.router, dependencies=guarded)

    @app.get("/", tags=["service"], summary="API index")
    def index() -> dict[str, Any]:
        return {
            "name": "Cross-Sell Recommendation Engine API",
            "version": __version__,
            "docs": "/docs",
            "openapi": "/openapi.json",
            "endpoints": [
                "/health", "/products", "/products/{product_id}", "/rules",
                "/recommendations/{product_id}", "POST /recommendations",
                "POST /simulate-revenue", "/config", "/stats", "/evaluation",
            ],
        }

    return app


app = create_app()
