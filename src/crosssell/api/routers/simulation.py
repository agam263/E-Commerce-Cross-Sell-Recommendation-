"""Revenue-impact simulation (PRD: ``POST /simulate-revenue``, US-005)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from crosssell.api.deps import get_config, get_store
from crosssell.api.schemas import SimulationRequest, SimulationResponse
from crosssell.config import Config
from crosssell.service.simulation import simulate_revenue
from crosssell.service.store import RuleStore

router = APIRouter(tags=["simulation"])


@router.post(
    "/simulate-revenue",
    response_model=SimulationResponse,
    summary="Simulate incremental revenue under explicit adoption assumptions",
)
def simulate(
    payload: SimulationRequest,
    store: RuleStore = Depends(get_store),
    config: Config = Depends(get_config),
) -> SimulationResponse:
    scenarios = payload.scenarios or config.simulation.scenarios
    try:
        report = simulate_revenue(
            eligible_transactions=payload.eligible_transactions,
            average_order_value=payload.average_order_value,
            scenarios=scenarios,
            currency=payload.currency,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    return SimulationResponse(ruleset_version=store.version, **report.to_dict())
