"""Cross-sell recommendation engine (Apriori association rules).

Package layout
--------------
``crosssell.config``       typed configuration loaded from ``config/config.yaml``
``crosssell.data``         loading, cleaning and basket construction
``crosssell.mining``       Apriori frequent itemsets + association-rule metrics
``crosssell.service``      recommendation ranking, revenue simulation, rule store
``crosssell.evaluation``   hold-out evaluation of the rule set
``crosssell.pipeline``     end-to-end training pipeline producing a versioned rule set
``crosssell.api``          FastAPI application
"""

__version__ = "1.0.0"

__all__ = ["__version__"]
