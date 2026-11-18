"""Shared FastAPI dependencies: rule-set access and optional API-key auth."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from fastapi import Depends, Header, HTTPException, Request, status

from crosssell.config import Config, load_config
from crosssell.service.store import RuleStore

log = logging.getLogger(__name__)

CONFIG_ENV = "CROSSSELL_CONFIG"
VERSION_ENV = "CROSSSELL_RULESET_VERSION"
API_KEY_ENV = "CROSSSELL_API_KEY"


def load_app_config() -> Config:
    """Config path comes from ``$CROSSSELL_CONFIG`` or the repo default."""
    path = os.environ.get(CONFIG_ENV)
    return load_config(Path(path) if path else None)


def load_store(config: Config) -> RuleStore:
    version = os.environ.get(VERSION_ENV) or None
    store = RuleStore.from_config(config, version)
    log.info(
        "Serving rule set %s (%s rules, %s products, cohorts=%s)",
        store.version,
        f"{len(store.recommender):,}",
        f"{len(store.artifacts.products):,}",
        store.cohorts,
    )
    return store


def get_config(request: Request) -> Config:
    return request.app.state.config


def get_store(request: Request) -> RuleStore:
    store = getattr(request.app.state, "store", None)
    if store is None:  # pragma: no cover - guarded by lifespan
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No rule set is loaded. Run `python -m crosssell.cli train` first.",
        )
    return store


def get_started_at(request: Request) -> float:
    return getattr(request.app.state, "started_at", time.time())


async def require_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """Optional shared-secret auth (PRD good-to-have).

    Disabled unless ``api.api_key`` is set in the config or ``$CROSSSELL_API_KEY``
    is exported, so local development and the test-suite need no credentials.
    """
    config: Config = request.app.state.config
    expected = os.environ.get(API_KEY_ENV) or config.api.api_key
    if not expected:
        return
    if x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )


StoreDep = Depends(get_store)
ConfigDep = Depends(get_config)
AuthDep = Depends(require_api_key)
