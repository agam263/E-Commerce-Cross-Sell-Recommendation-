"""Revenue-impact simulation (PRD FR-09, US-005, AC-05, AC-10).

    expected additional orders  = eligible transactions x cross-sell adoption rate
    estimated incremental revenue = expected additional orders x average order value

Every number produced here is a **simulated planning estimate under explicit
assumptions**, not measured uplift. Establishing real uplift needs a live A/B
test, which is explicitly out of scope in the PRD.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

DISCLAIMER = (
    "Simulated estimate under user-supplied assumptions. These figures are not "
    "measured or guaranteed revenue uplift; validating actual uplift requires a "
    "controlled live experiment."
)


@dataclass(frozen=True)
class ScenarioResult:
    name: str
    adoption_rate: float
    eligible_transactions: int
    expected_additional_orders: float
    average_order_value: float
    estimated_incremental_revenue: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SimulationReport:
    scenarios: list[ScenarioResult]
    assumptions: dict[str, object]
    formula: dict[str, str] = field(
        default_factory=lambda: {
            "expected_additional_orders": "eligible_transactions * adoption_rate",
            "estimated_incremental_revenue": "expected_additional_orders * average_order_value",
        }
    )
    disclaimer: str = DISCLAIMER
    generated_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds")
    )

    def to_dict(self) -> dict[str, object]:
        return {
            "scenarios": [s.to_dict() for s in self.scenarios],
            "assumptions": self.assumptions,
            "formula": self.formula,
            "disclaimer": self.disclaimer,
            "generated_at": self.generated_at,
        }


def simulate_revenue(
    eligible_transactions: int,
    average_order_value: float,
    scenarios: dict[str, float],
    currency: str = "GBP",
    notes: str | None = None,
) -> SimulationReport:
    """Run the baseline simulation for each named adoption scenario.

    Parameters
    ----------
    eligible_transactions:
        Transactions the cross-sell surface could realistically appear on --
        e.g. invoices in the evaluation window for which the engine produces at
        least one recommendation.
    average_order_value:
        Average value of the *additional* purchase, in ``currency``.
    scenarios:
        ``{"conservative": 0.02, "base": 0.05, ...}`` adoption rates in ``[0, 1]``.
    """
    if eligible_transactions < 0:
        raise ValueError("eligible_transactions must be >= 0")
    if average_order_value < 0:
        raise ValueError("average_order_value must be >= 0")
    if not scenarios:
        raise ValueError("at least one scenario is required")

    results: list[ScenarioResult] = []
    for name, rate in scenarios.items():
        if not 0 <= rate <= 1:
            raise ValueError(f"adoption rate for scenario {name!r} must be in [0, 1], got {rate}")
        orders = eligible_transactions * rate
        results.append(
            ScenarioResult(
                name=name,
                adoption_rate=float(rate),
                eligible_transactions=int(eligible_transactions),
                expected_additional_orders=float(orders),
                average_order_value=float(average_order_value),
                estimated_incremental_revenue=float(orders * average_order_value),
            )
        )
    results.sort(key=lambda s: s.adoption_rate)

    assumptions = {
        "eligible_transactions": int(eligible_transactions),
        "average_order_value": float(average_order_value),
        "currency": currency,
        "adoption_rates": {k: float(v) for k, v in scenarios.items()},
    }
    if notes:
        assumptions["notes"] = notes
    return SimulationReport(scenarios=results, assumptions=assumptions)
