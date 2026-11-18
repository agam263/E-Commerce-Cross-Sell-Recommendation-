# Architecture

## 1. System view

```
┌──────────────────────────┐
│ Merchandising / Growth   │
│ team (browser)           │
└────────────┬─────────────┘
             │ HTTPS
┌────────────▼─────────────┐      ┌────────────────────────────┐
│ React dashboard          │      │ Offline (run on demand)    │
│ Vite · Tailwind · Axios  │      │                            │
│ 6 screens, Recharts      │      │  crosssell.cli train       │
└────────────┬─────────────┘      │  crosssell.cli tune        │
             │ REST / JSON        │  crosssell.cli report      │
┌────────────▼─────────────┐      └─────────────┬──────────────┘
│ FastAPI                  │                    │ writes
│  /products  /rules       │                    ▼
│  /recommendations        │      ┌────────────────────────────┐
│  /simulate-revenue       │◄─────┤ artifacts/<ruleset_version>│
│  /config /stats /health  │ load │  rules.csv  itemsets.csv   │
└────────────┬─────────────┘ once │  products.csv  manifest    │
             │                    │  evaluation.json  cohorts/ │
┌────────────▼─────────────┐      └─────────────▲──────────────┘
│ Recommendation service   │                    │
│  antecedent index        │      ┌─────────────┴──────────────┐
│  ranking + fallback      │      │ data/raw/Online Retail.xlsx│
│  revenue simulation      │      │ immutable, hashed          │
└──────────────────────────┘      └────────────────────────────┘
```

The serving path never reads the dataset. Training writes a versioned, immutable
rule set; the API loads one at startup and answers from memory. Retraining
produces a *new* version rather than mutating the one being served.

## 2. Pipeline

```
load_raw ──► clean_transactions ──► build_transactions ──► split_transactions
   │              │                        │                      │
   │         audit trail            invoice → set of        chronological
   │         (every row             distinct products       70 / 15 / 15
   │          accounted for)                                      │
   │                                                              ▼
   │                                         product eligibility (train only)
   │                                                              │
   ▼                                                              ▼
file_fingerprint ──────────────────────────────────────►  mine (Apriori)
(sha256 into manifest)                                            │
                                                     frequent itemsets
                                                              │
                                                       generate_rules
                                                 support/confidence/lift/
                                                 leverage/conviction + filters
                                                              │
                        ┌─────────────────────────────────────┤
                        ▼                                     ▼
                 evaluate (hold-out)                  Recommender (serving)
                 replay, baselines,                   antecedent index,
                 coverage                             ranking, fallback
                        │                                     │
                        └──────────────► artifacts/ ◄─────────┘
                                         + manifest.json
```

## 3. Module map

| Module | Responsibility | Depends on |
| --- | --- | --- |
| `config.py` | typed settings, validation, fingerprinting | — |
| `data/loader.py` | read xlsx/csv/parquet, normalise schema, hash the file | config |
| `data/preprocessing.py` | the cleaning policy + audit trail | config |
| `data/baskets.py` | baskets, catalog, cohorts, chronological splits | config |
| `mining/apriori.py` | frequent itemsets (Agrawal & Srikant 1994) | — |
| `mining/rules.py` | rule generation and interest metrics | — |
| `mining/engine.py` | engine dispatch (`builtin` / `mlxtend`) + stats | config, data |
| `service/recommender.py` | antecedent index, ranking, explanations, fallback | config |
| `service/simulation.py` | revenue scenarios | — |
| `service/store.py` | artifact persistence and loading | config, service |
| `evaluation.py` | replay evaluation, baselines, threshold sweep | service, data |
| `versioning.py` | version strings and the reproducibility manifest | config |
| `pipeline.py` | orchestration, caching, artifact writing | all of the above |
| `report.py` | markdown report + matplotlib figures | service, evaluation |
| `api/` | HTTP contract, DI, optional auth | service, config |
| `cli.py` | command-line entry point | pipeline, service, report |

`mining/apriori.py` and `mining/rules.py` deliberately depend on nothing in the
project: they take plain sequences of frozensets and return plain data, so they
can be tested against mlxtend directly and reused outside this codebase.

## 4. Key design decisions

### Rule sets are versioned artifacts, not pickles

`rs-<data hash>-<config hash>`. The version is derived, not assigned, so it
cannot drift from what produced it. A pickle would couple the API to the exact
library versions used at training time; CSV and JSON stay readable with nothing
installed, which also means a reviewer can audit the rules by eye.

The config fingerprint deliberately excludes `paths` and `api`: moving a file or
changing CORS must not invalidate a rule set.

### Product eligibility is decided on the training split

Dropping products with fewer than *n* invoices is a modelling decision, so the
counts come from the training window only. Deciding it on the full dataset would
leak information about which products survive into the future — a small leak,
but the kind that quietly inflates offline numbers.

### Serving thresholds are separate from mining thresholds

Mining decides what gets *stored*; the API can filter harder per request
(`min_confidence`, `min_lift`). The dashboard's threshold controls therefore
re-filter an existing rule set instead of re-mining, which is what makes "change
the thresholds and watch coverage move" instant in the demo.

### The expensive half of serving is separated from the cheap half

`Recommender.candidate_rules()` finds the rules whose antecedent is contained in
the basket (index lookup + subset test); `rank_candidates()` filters and ranks
them. The threshold sweep calls the first once per basket and the second once
per threshold combination — which is what turned a grid search from ~45 minutes
into ~20 seconds.

### Prepared data is cached, keyed by content

Reading and cleaning the 23 MB spreadsheet dominates runtime. `pipeline.prepare()`
caches its result under `data/interim/`, keyed by the raw-file hash plus the
data-stage configuration, so a stale cache can never be silently reused.

### Two mining engines

`builtin` is the implementation of the paper; `mlxtend` is an independent
reference. The test-suite asserts they agree itemset-for-itemset and
rule-for-rule. Writing the algorithm is the point of the track; proving it
correct against an established library is what makes it usable.

## 5. Apriori implementation notes

Candidate generation is the paper's `apriori-gen`: join `L(k-1)` with itself on
the shared `k-2` prefix, then prune any candidate with an infrequent
`(k-1)`-subset (downward closure).

Counting uses two exact strategies:

* **k = 2** — co-occurring pairs are counted directly while scanning each basket.
  The number of *candidate* pairs is quadratic in the frequent items (622,234 at
  the shipped thresholds) while the number of pairs that actually occur is far
  smaller, so enumerating candidates and counting them would be wasteful.
* **k ≥ 3** — vertical tid-lists: a candidate's transaction set is the
  intersection of its `(k-1)`-prefix's tid-list with its last item's, so support
  is obtained without re-scanning the database.

At the shipped configuration this mines 33,680 frequent itemsets from 12,779
baskets in 2.6 seconds.

## 6. Request flow

```
GET /recommendations/85123A?top_k=5&cohort=repeat
    │
    ├─ require_api_key        no-op unless a key is configured
    ├─ get_store              rule set loaded at startup
    ├─ store.for_cohort       pick the "repeat" rule set
    ├─ candidate_rules        rules whose antecedent ⊆ {85123A}
    ├─ rank_candidates        drop basket items, best rule per consequent,
    │                         sort by confidence → lift → support, take K
    ├─ fallback               only if nothing qualified: best-sellers,
    │                         labelled, with null metrics
    └─ 200 { basket, ruleset_version, thresholds, recommendations[] }
         404 unknown product · 422 malformed input
```

## 7. Frontend structure

```
src/
  api/client.js        axios instance, base URL resolution, error messages
  lib/useApi.js        fetch hook with stale-response guarding + debounce
  lib/format.js        number/date/currency formatting, CSV download
  components/          Layout + nav, StatTile/Meter, Charts, loading/error/empty
  pages/               Overview, ProductExplorer, RuleExplorer,
                       RevenueSimulator, ModelInfo, Help
```

In development Vite proxies `/api` to `127.0.0.1:8000`, so the app uses relative
URLs in both development and production. Charts are single-measure, so each uses
one hue from a colour-vision-validated palette; rule-backed and fallback
recommendations are distinguished by border style and a text badge, never by
colour alone.

---

## Presentation layer (added in the dashboard rebuild)

```
crosssell.service.categories   product name -> derived category  (presentation only)
crosssell.service.insights     rule table   -> templated, evidence-backed insights
        |                                      GET /insights
        v
frontend/src/
  components/Charts.jsx        resolves CSS custom properties to literal colours
                               before handing them to Recharts: a var() inside an
                               SVG presentation attribute is invalid and is
                               ignored by Safari and Firefox
  components/AssociationGraph  hand-rolled radial SVG; deterministic layout, so
                               the same data always draws the same picture
  components/ProductTile       ProductPhoto -> category photograph, falling back
                               to an icon tile when a category has no pinned
                               image or the file fails to load
  lib/categoryImages.js        reads public/category-images/attribution.json
```

### Product imagery

```
scripts/fetch_category_images.py        (run once, offline)
        | pinned category -> exact Commons file title
        v
frontend/public/category-images/*.jpg + attribution.json   (vendored)
        v
served by the app itself -- no external request at view time
```

Per-product photography is not possible from this dataset and was tested
rather than assumed: the real SKU names return zero results in image search,
and generalising the query returns a different object. So the unit of imagery
is the *category*, each image is chosen by hand and pinned by file title, and
the UI states what the picture is. Vendoring rather than hotlinking keeps the
dashboard working offline, stops an upstream rename from breaking it, and
means nothing about the catalog is sent anywhere when someone opens a page.

Two boundaries are deliberate:

* **Categories never reach the miner.** They are derived from free text and are
  a reading aid. Rules are built from StockCodes exactly as before, so the model
  is unaffected by how a product happens to be named.
* **Insights are built server-side from fixed templates.** The browser cannot
  compose a new claim; it can only render one the backend measured. Adding an
  insight means adding a template and a test, not writing prose in a component.

