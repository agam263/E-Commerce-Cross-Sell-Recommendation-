"""Product catalog endpoints (PRD: ``GET /products``)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from crosssell.api.deps import get_store
from crosssell.api.presenters import products_to_out
from crosssell.api.schemas import ProductListResponse, ProductOut
from crosssell.service.store import RuleStore

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=ProductListResponse, summary="List or search products")
def list_products(
    search: str | None = Query(None, description="Case-insensitive match on code or name"),
    only_with_rules: bool = Query(False, description="Keep products that can fire a rule"),
    sort_by: str = Query("invoice_count", pattern="^(invoice_count|total_revenue|product_name)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    store: RuleStore = Depends(get_store),
) -> ProductListResponse:
    frame = store.artifacts.products
    if search:
        needle = search.strip().lower()
        mask = frame["StockCode"].astype(str).str.lower().str.contains(needle, regex=False) | frame[
            "ProductName"
        ].astype(str).str.lower().str.contains(needle, regex=False)
        frame = frame.loc[mask]
    if only_with_rules:
        frame = frame.loc[frame["StockCode"].isin(store.triggerable_products)]

    column = {"product_name": "ProductName"}.get(sort_by, sort_by)
    frame = frame.sort_values(column, ascending=(order == "asc"), kind="stable")
    total = int(len(frame))
    page = frame.iloc[offset : offset + limit]
    return ProductListResponse(
        total=total, limit=limit, offset=offset, items=products_to_out(page, store)
    )


@router.get("/{product_id}", response_model=ProductOut, summary="Fetch one product")
def get_product(product_id: str, store: RuleStore = Depends(get_store)) -> ProductOut:
    frame = store.artifacts.products
    match = frame.loc[frame["StockCode"].astype(str) == product_id.strip()]
    if match.empty:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown product id {product_id!r} in rule set {store.version}.",
        )
    return products_to_out(match, store)[0]
