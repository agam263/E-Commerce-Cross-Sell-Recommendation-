"""FastAPI application exposing the cross-sell rule set."""

from crosssell.api.main import app, create_app

__all__ = ["app", "create_app"]
