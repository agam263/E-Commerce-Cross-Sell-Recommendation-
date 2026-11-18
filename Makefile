# Cross-Sell Recommendation Engine -- common tasks.
# Every target is safe to re-run.

PY      := .venv/bin/python
PIP     := .venv/bin/pip
export PYTHONPATH := src

.DEFAULT_GOAL := help
.PHONY: help setup data images train tune evaluate report test lint api ui ui-build clean clean-artifacts all

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup:  ## Create the virtualenv and install Python + frontend dependencies
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	cd frontend && npm install

data:  ## Download the Online Retail dataset into data/raw/
	$(PY) scripts/download_data.py

images:  ## Download the per-category product photographs (already committed; re-run to refresh)
	$(PY) scripts/fetch_category_images.py

train:  ## Mine, evaluate and version a rule set
	$(PY) -m crosssell.cli train

tune:  ## Threshold sweep on the validation split (test split untouched)
	$(PY) -m crosssell.cli tune

evaluate:  ## Evaluate the active rule set on the hold-out split
	$(PY) -m crosssell.cli evaluate --split test

report:  ## Write reports/evaluation_report.md and its figures
	$(PY) -m crosssell.cli report

test:  ## Run the test-suite
	$(PY) -m pytest tests -q

lint:  ## Lint the Python sources
	.venv/bin/ruff check src tests

api:  ## Serve the API on http://127.0.0.1:8000 (docs at /docs)
	$(PY) -m crosssell.cli serve --reload

ui:  ## Run the React dashboard on http://localhost:5173
	cd frontend && npm run dev

ui-build:  ## Production build of the dashboard into frontend/dist
	cd frontend && npm run build

all: train report test  ## Train, report and test in one go

clean:  ## Remove caches and build output
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache frontend/dist

clean-artifacts:  ## Also remove trained rule sets and the prepared-data cache
	rm -rf artifacts/* data/interim/* data/processed/*
	@touch artifacts/.gitkeep data/interim/.gitkeep data/processed/.gitkeep
