"""API routers, one module per resource in the PRD's API contract."""

from crosssell.api.routers import health, meta, products, recommendations, rules, simulation

__all__ = ["health", "meta", "products", "recommendations", "rules", "simulation"]
