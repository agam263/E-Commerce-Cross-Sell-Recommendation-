# PRD traceability

Every requirement in the PRD, mapped to the code that implements it and the test
that proves it. Paths are relative to the repository root.

## Functional requirements

| # | Requirement | Implementation | Test |
| --- | --- | --- | --- |
| FR-01 | Ingest the Online Retail dataset | `src/crosssell/data/loader.py`, `scripts/download_data.py` | `tests/test_preprocessing.py::test_schema_aliases_are_normalised` |
| FR-02 | Documented preprocessing → reproducible cleaned dataset | `src/crosssell/data/preprocessing.py` (audit trail), `config/config.yaml` | `tests/test_preprocessing.py` (10 tests) |
| FR-03 | Construct transaction baskets from `InvoiceNo` | `src/crosssell/data/baskets.py::build_transactions` | `tests/test_baskets.py::test_quantities_collapse_to_presence` |
| FR-04 | Apriori with configurable minimum support | `src/crosssell/mining/apriori.py` | `tests/test_mining.py::test_builtin_engine_matches_mlxtend` |
| FR-05 | Generate rules with support, confidence, lift | `src/crosssell/mining/rules.py` | `tests/test_mining.py::test_rule_metric_formulas`, `::test_generated_rules_match_mlxtend` |
| FR-06 | Filter and rank recommendation candidates | `src/crosssell/service/recommender.py` | `tests/test_recommender.py` (18 tests) |
| FR-07 | FastAPI exposes recommendation and rule endpoints | `src/crosssell/api/` | `tests/test_api.py` (35 tests) |
| FR-08 | React consumes the API and displays metrics | `frontend/src/pages/` (6 screens), `frontend/src/components/` | `npm run build`; live headless verification of every route, desktop and 390px |
| FR-09 | Revenue simulation from explicit assumptions | `src/crosssell/service/simulation.py` | `tests/test_simulation.py` (11 tests) |
| FR-10 | Expose rule-set version/configuration metadata | `src/crosssell/versioning.py`, `GET /config` | `tests/test_pipeline.py::test_manifest_records_everything_needed_to_reproduce` |
| FR-11 | Automated tests for pipeline and API | `tests/` (184 tests) | `make test` |
| FR-12 | README, setup, architecture diagram, repro steps | `README.md`, `docs/ARCHITECTURE.md`, `Makefile` | — |

## Acceptance criteria

| # | Criterion | Evidence |
| --- | --- | --- |
| AC-01 | Apriori generates frequent itemsets | 33,680 itemsets in `artifacts/<version>/itemsets.csv`; `tests/test_mining.py::test_apriori_counts_a_hand_checked_example` |
| AC-02 | Rules expose support, confidence, lift | `rules.csv` columns; `GET /rules`; Rule Explorer screen |
| AC-03 | Valid product → ranked recommendations **or** a documented fallback | `recommender.recommend()`; `tests/test_recommender.py::test_popularity_fallback_when_no_rule_fires`, `::test_fallback_never_fabricates_rule_metrics` |
| AC-04 | React displays recommendations and rule evidence | Product Explorer cards show price, derived category, strength band, support/confidence/lift, a prose explanation and an inspectable rule drawer; a radial association graph shows the same relationships visually |
| AC-05 | Revenue simulator computes from explicit assumptions | Revenue Simulator screen; `POST /simulate-revenue`; `tests/test_simulation.py::test_scenario_arithmetic_is_exact` |
| AC-06 | Rule-set version and thresholds visible | `GET /config`, Model / Rule Set screen, every recommendation response carries `ruleset_version` |
| AC-07 | Tests cover pipeline logic and API endpoints | 184 tests, `make test` |
| AC-08 | README documents install, architecture, data prep, mining, API, repro | `README.md`, `docs/ARCHITECTURE.md` |
| AC-09 | Final report covers support/confidence/lift + ≥1 simulation scenario | `reports/evaluation_report.md` (3 scenarios, 5 figures) |
| AC-10 | No claim that simulated revenue equals realised uplift | Disclaimer in `simulation.py`, in the API response, on the Simulator screen, in the report and the README |

## Product principles

| Principle | How it is honoured |
| --- | --- |
| Recommend, do not claim certainty | Explanations are phrased as historical co-occurrence; the limitation is stated on the dashboard, in the report and the README |
| Explicit, configurable thresholds | Everything lives in `config/config.yaml`, is surfaced at `GET /config`, and is adjustable per request |
| Version every rule set | `rs-<data hash>-<config hash>` + `manifest.json` with dataset digest, config, environment |
| Keep evaluation data untouched | Chronological 70/15/15; `cli tune` only ever reads the validation split; the hold-out is evaluated once |
| Prefer explainability | Each recommendation carries its rule id, metrics, evidence counts and a prose explanation |
| Tie outputs to business value transparently | Simulator shows the formula, the assumptions and the disclaimer alongside the number |
| Clear fallback for sparse/new products | `fallback_popularity`, labelled, with `confidence`/`lift` as `null` |

## Scope

**In scope — delivered:** ingestion and cleaning · invoice-level baskets ·
Apriori · rule generation and filtering · recommendation ranking · FastAPI
endpoints · React dashboard · revenue simulation · evaluation, tests and
documentation.

**Out of scope — not attempted:** real-time personalisation from session
history · guaranteed uplift claims · payment/cart processing · neural
recommenders · causal A/B inference.

## Good-to-have and stretch

| Item | Status |
| --- | --- |
| Polished dashboard with charts | Done — 6 screens, light/dark, validated chart palette |
| Tests across pipeline and API | Done — 139 tests |
| README + architecture + repro steps | Done |
| Basic authentication | Done — optional `X-API-Key`, off by default (`tests/test_api.py::test_api_key_is_enforced_when_configured`) |
| Exportable rule tables | Done — CSV export in the Rule Explorer |
| **Stretch: new vs repeat cohorts** | Done — separate rule sets mined per cohort (6,663 / 5,617 rules), `?cohort=` on `/rules` and `/recommendations`, cohort selector in the UI. Labels use the customer's invoice sequence *at the time of the invoice*, so they never use information from the future |
| Batch scoring | Not implemented — listed as future work in the PRD |

## Deliberate deviations

| PRD text | What was built | Why |
| --- | --- | --- |
| "rank by a transparent score using lift first" | Both orderings ship. Default `rank_by: [confidence, lift, support]`; the PRD's `[lift, confidence, support]` is selectable per request (`?rank_by=`) and from a selector on the Product Explorer | Measured on validation: hit@5 0.181 vs 0.157. `min_lift` already gates admission, so every served rule is a real association; confidence is what a top-K list should maximise. Rather than hide the deviation, the dashboard lets a reviewer switch between the two live and see the difference |
| Dataset from Kaggle | Fetched from UCI (same dataset, dataset #352) | Kaggle needs credentials; a Kaggle copy can be dropped into `data/raw/` and used unchanged |
| mlxtend as the implementation | Own Apriori, with mlxtend as a tested reference engine | The track is "Advanced Data Science" — implementing the VLDB 1994 algorithm is the point; `mining.engine: mlxtend` switches to the library |

## Presentation-layer additions

These support the dashboard and do not touch mining, ranking or evaluation.

| Addition | Where | Note |
| --- | --- | --- |
| Derived product categories | `src/crosssell/service/categories.py` | Parsed from the product name, 82% of the catalog classified, the rest reported as `Uncategorised`. Never feeds mining |
| Category photography | `scripts/fetch_category_images.py`, `frontend/public/category-images/` | One hand-picked Wikimedia Commons photograph per category, pinned by exact file title and vendored locally. Per-product imagery is impossible: the dataset has no images and the real SKU names return zero search results. Every surface states the image represents the category, not the product. PD/CC0/CC BY/CC BY-SA only; credits shown in the UI |
| Business insights | `src/crosssell/service/insights.py`, `GET /insights` | Templated statements with measured values substituted in, each carrying the rows it was derived from. An insight the data cannot support is omitted, not padded |
| Per-request ranking | `Recommender.recommend(rank_by=...)`, `?rank_by=` | Re-ranks the already-mined rule set; never re-mines |
| Product economics on recommendations | `median_unit_price`, `invoice_count` on `RecommendationOut` | Price is genuine dataset data, not an estimate |
| Headline counts on `/stats` | `total_invoices`, `catalog_products`, `mined_baskets`, `rules_per_product` | Totals over the cleaned dataset, distinct from the mined catalog |
