"""Pydantic request/response models -- the published API contract (PRD US-007).

Field names are ``snake_case`` throughout and every response that depends on the
mined rules carries ``ruleset_version`` so a client can always tell which
configuration produced what it is displaying (US-003).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    ruleset_version: str
    rules_loaded: int
    products_loaded: int
    cohorts: list[str]
    uptime_seconds: float
    api_version: str


class ProductOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    stock_code: str = Field(description="Canonical product identifier (StockCode)")
    product_name: str
    invoice_count: int = Field(description="Invoices containing this product (cleaned data)")
    support: float = Field(description="Share of training invoices containing this product")
    total_quantity: float
    total_revenue: float
    median_unit_price: float
    avg_line_revenue: float = Field(
        description="Average value of one purchase of this product; the simulator's default AOV"
    )
    has_rules: bool = Field(description="True when at least one rule can fire for this product")
    category: str = Field(
        default="Uncategorised",
        description="Category derived from the product name; not a retailer taxonomy",
    )


class ProductListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ProductOut]


class RuleOut(BaseModel):
    rule_id: str
    antecedents: list[str]
    antecedent_names: list[str]
    antecedent_categories: list[str] = Field(
        default_factory=list,
        description="Categories derived from the antecedent product names",
    )
    consequents: list[str]
    consequent_names: list[str]
    consequent_categories: list[str] = Field(
        default_factory=list,
        description="Categories derived from the consequent product names",
    )
    antecedent_len: int
    support: float
    confidence: float
    lift: float
    leverage: float
    conviction: float | None
    support_count: int
    antecedent_count: int
    consequent_count: int


class RuleListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    cohort: str
    ruleset_version: str
    filters: dict[str, Any]
    items: list[RuleOut]


class RecommendationOut(BaseModel):
    stock_code: str
    product_name: str
    rank: int
    score: float
    source: Literal["association_rule", "fallback_popularity"]
    explanation: str
    support: float | None = None
    confidence: float | None = None
    lift: float | None = None
    leverage: float | None = None
    conviction: float | None = None
    rule_id: str | None = None
    antecedents: list[str] = Field(default_factory=list)
    antecedent_count: int | None = None
    support_count: int | None = None
    popularity_support: float | None = None
    avg_line_revenue: float | None = None
    median_unit_price: float | None = Field(
        default=None, description="Typical unit price of this product in the cleaned data"
    )
    invoice_count: int | None = Field(
        default=None, description="Invoices containing this product (cleaned data)"
    )
    category: str | None = Field(
        default=None,
        description="Category derived from the product name; not a retailer taxonomy",
    )


class RecommendationResponse(BaseModel):
    basket: list[str]
    basket_names: list[str]
    cohort: str
    ruleset_version: str
    rank_by: list[str] = Field(
        default_factory=list, description="Ranking order that produced this result"
    )
    top_k: int
    thresholds: dict[str, float | None]
    count: int
    used_fallback: bool = Field(
        description="True when no rule cleared the thresholds and popularity was used instead"
    )
    recommendations: list[RecommendationOut]


class BasketRequest(BaseModel):
    products: list[str] = Field(
        min_length=1, description="StockCode values currently in the basket"
    )
    top_k: int | None = Field(default=None, ge=1, le=50)
    min_confidence: float | None = Field(default=None, ge=0, le=1)
    min_lift: float | None = Field(default=None, ge=0)
    cohort: str | None = None
    allow_fallback: bool | None = None
    rank_by: list[str] | None = Field(
        default=None,
        description=(
            "Ranking order for this request, e.g. ['lift','confidence','support'] for the "
            "PRD's lift-first ordering. Omit to use the configured default."
        ),
    )

    @field_validator("products")
    @classmethod
    def _strip(cls, value: list[str]) -> list[str]:
        cleaned = [v.strip() for v in value if v and v.strip()]
        if not cleaned:
            raise ValueError("products must contain at least one non-empty StockCode")
        return cleaned


class SimulationRequest(BaseModel):
    """Explicit, user-supplied assumptions (PRD FR-09)."""

    eligible_transactions: int = Field(ge=0, description="Transactions the cross-sell could reach")
    average_order_value: float = Field(ge=0, description="Average value of the extra purchase")
    scenarios: dict[str, float] | None = Field(
        default=None,
        description="Adoption rates in [0,1], e.g. {'conservative':0.02,'base':0.05}",
    )
    currency: str = "GBP"
    notes: str | None = None

    @field_validator("scenarios")
    @classmethod
    def _rates(cls, value: dict[str, float] | None) -> dict[str, float] | None:
        if value is None:
            return None
        if not value:
            raise ValueError("scenarios must not be empty")
        for name, rate in value.items():
            if not 0 <= rate <= 1:
                raise ValueError(f"adoption rate for {name!r} must be between 0 and 1")
        return value


class ScenarioOut(BaseModel):
    name: str
    adoption_rate: float
    eligible_transactions: int
    expected_additional_orders: float
    average_order_value: float
    estimated_incremental_revenue: float


class SimulationResponse(BaseModel):
    ruleset_version: str
    scenarios: list[ScenarioOut]
    assumptions: dict[str, Any]
    formula: dict[str, str]
    disclaimer: str
    generated_at: str


class ConfigResponse(BaseModel):
    ruleset_version: str
    built_at: str | None
    pipeline_version: str | None
    config_fingerprint: str | None
    dataset: dict[str, Any]
    thresholds: dict[str, Any]
    recommendation: dict[str, Any]
    preprocessing: dict[str, Any]
    split: dict[str, Any]
    simulation_defaults: dict[str, Any]
    cohorts: list[str]
    environment: dict[str, Any]
    reproduce: dict[str, Any]


class StatsResponse(BaseModel):
    """Everything the overview dashboard needs in one request."""

    ruleset_version: str
    built_at: str | None
    kpis: dict[str, Any]
    rule_metric_summary: dict[str, Any]
    itemsets_by_length: dict[str, int]
    metric_histograms: dict[str, Any]
    top_rules: list[RuleOut]
    top_products: list[ProductOut]
    cohorts: dict[str, Any]
    evaluation: dict[str, Any]
    simulation_defaults: dict[str, Any]


class ErrorResponse(BaseModel):
    error: str
    detail: str
    hint: str | None = None


class InsightOut(BaseModel):
    """One derived insight, with the numbers and rows that back it."""

    id: str
    kind: Literal["opportunity", "coverage", "risk", "pattern"]
    title: str
    body: str
    metric_label: str
    metric_value: float
    metric_format: Literal["number", "percent", "multiple", "currency"] = "number"
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class InsightListResponse(BaseModel):
    ruleset_version: str
    cohort: str
    count: int
    insights: list[InsightOut]
