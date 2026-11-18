"""Revenue simulation arithmetic and its guard-rails."""

from __future__ import annotations

import pytest

from crosssell.service.simulation import DISCLAIMER, simulate_revenue


def test_scenario_arithmetic_is_exact():
    report = simulate_revenue(10_000, 18.50, {"base": 0.05})
    scenario = report.scenarios[0]
    assert scenario.expected_additional_orders == pytest.approx(500.0)
    assert scenario.estimated_incremental_revenue == pytest.approx(9250.0)


def test_scenarios_are_ordered_by_adoption_rate():
    report = simulate_revenue(
        1000, 10.0, {"optimistic": 0.10, "conservative": 0.02, "base": 0.05}
    )
    assert [s.name for s in report.scenarios] == ["conservative", "base", "optimistic"]


def test_revenue_scales_linearly_with_adoption():
    report = simulate_revenue(1000, 10.0, {"a": 0.02, "b": 0.04})
    low, high = report.scenarios
    assert high.estimated_incremental_revenue == pytest.approx(
        2 * low.estimated_incremental_revenue
    )


def test_zero_adoption_yields_zero_revenue():
    report = simulate_revenue(1000, 10.0, {"none": 0.0})
    assert report.scenarios[0].estimated_incremental_revenue == 0.0


def test_assumptions_and_formula_are_recorded():
    report = simulate_revenue(1000, 10.0, {"base": 0.05}, currency="EUR", notes="hi")
    payload = report.to_dict()
    assert payload["assumptions"]["currency"] == "EUR"
    assert payload["assumptions"]["notes"] == "hi"
    assert payload["assumptions"]["adoption_rates"] == {"base": 0.05}
    orders_formula = payload["formula"]["expected_additional_orders"]
    assert "eligible_transactions * adoption_rate" in orders_formula


def test_output_is_labelled_as_a_simulation():
    report = simulate_revenue(1000, 10.0, {"base": 0.05})
    assert report.disclaimer == DISCLAIMER
    assert "not measured" in DISCLAIMER or "not guaranteed" in DISCLAIMER


@pytest.mark.parametrize(
    "kwargs",
    [
        {"eligible_transactions": -1, "average_order_value": 10.0, "scenarios": {"a": 0.1}},
        {"eligible_transactions": 10, "average_order_value": -1.0, "scenarios": {"a": 0.1}},
        {"eligible_transactions": 10, "average_order_value": 10.0, "scenarios": {}},
        {"eligible_transactions": 10, "average_order_value": 10.0, "scenarios": {"a": 1.5}},
        {"eligible_transactions": 10, "average_order_value": 10.0, "scenarios": {"a": -0.1}},
    ],
)
def test_invalid_inputs_are_rejected(kwargs):
    with pytest.raises(ValueError):
        simulate_revenue(**kwargs)


def test_reproducible_from_stored_assumptions():
    """PRD evaluation metric: 'reproduce calculations from stored assumptions'."""
    first = simulate_revenue(2500, 7.25, {"base": 0.05}).to_dict()
    second = simulate_revenue(
        first["assumptions"]["eligible_transactions"],
        first["assumptions"]["average_order_value"],
        first["assumptions"]["adoption_rates"],
    ).to_dict()
    assert first["scenarios"] == second["scenarios"]
