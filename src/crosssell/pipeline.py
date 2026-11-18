"""End-to-end training pipeline: raw dataset -> versioned, evaluated rule set.

Steps (each one is a pure function living in its own module, so each can be
unit-tested in isolation):

1. load the immutable raw file and fingerprint it
2. apply the documented cleaning policy, keeping an audit trail
3. build the product catalog and invoice-level baskets
4. split chronologically into train / validation / test
5. restrict to products frequent enough **in the training window**
6. mine frequent itemsets and association rules on train only
7. evaluate on the untouched test split
8. mine cohort-specific rule sets (stretch goal)
9. write artifacts + reproducibility manifest
"""

from __future__ import annotations

import hashlib
import json
import logging
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from crosssell import evaluation as evaluation_mod
from crosssell.config import Config
from crosssell.data.baskets import (
    COHORT_NEW,
    COHORT_REPEAT,
    TransactionSet,
    build_product_catalog,
    build_transactions,
    split_transactions,
)
from crosssell.data.loader import file_fingerprint, load_raw
from crosssell.data.preprocessing import clean_transactions, validate_clean
from crosssell.mining.engine import MiningResult, mine
from crosssell.service.recommender import Recommender
from crosssell.service.simulation import simulate_revenue
from crosssell.service.store import (
    write_itemsets_csv,
    write_latest_pointer,
    write_rules_csv,
)
from crosssell.versioning import build_manifest, make_version, write_manifest

log = logging.getLogger(__name__)


@dataclass
class PreparedData:
    """Everything produced by the data stage, shared by train/tune/evaluate."""

    dataset: dict[str, Any]
    cleaning_audit: pd.DataFrame
    cleaning_summary: dict[str, Any]
    validation_checks: dict[str, bool]
    catalog: pd.DataFrame
    catalog_mined: pd.DataFrame
    transactions_describe: dict[str, Any]
    splits: dict[str, TransactionSet]
    eligible_products: list[str]
    invoice_meta: pd.DataFrame
    n_products_total: int


@dataclass
class TrainResult:
    ruleset_version: str
    artifacts_dir: Path
    mining: MiningResult
    evaluation: dict[str, Any]
    manifest: dict[str, Any]
    splits: dict[str, TransactionSet] = field(default_factory=dict)
    recommender: Recommender | None = None


def _popularity(ts: TransactionSet) -> pd.Series:
    return ts.item_support()


def _default_simulation(
    cfg: Config,
    catalog: pd.DataFrame,
    rules: pd.DataFrame,
    test: TransactionSet,
    replay: dict[str, Any],
) -> dict[str, Any]:
    """Pre-computed default scenarios so the dashboard opens on real numbers."""
    coverage = float(replay.get("basket_coverage", 0.0))
    eligible = int(round(len(test) * coverage))

    avg_value = float(catalog["avg_line_revenue"].median()) if len(catalog) else 0.0
    if len(rules):
        weights = rules["support_count"].astype(float)
        values = (
            rules["consequents"]
            .map(lambda c: c[0] if len(c) else None)
            .map(catalog.set_index("StockCode")["avg_line_revenue"])
            .astype(float)
        )
        valid = values.notna()
        if valid.any() and weights[valid].sum() > 0:
            avg_value = float((values[valid] * weights[valid]).sum() / weights[valid].sum())

    report = simulate_revenue(
        eligible_transactions=eligible,
        average_order_value=round(avg_value, 2),
        scenarios=cfg.simulation.scenarios,
        notes=(
            "Defaults derived from the hold-out window: eligible transactions = "
            f"{len(test):,} test invoices x {coverage:.1%} basket coverage; average order "
            "value = support-weighted mean value of one purchase of a recommended product."
        ),
    )
    return report.to_dict()


def _mine_cohorts(
    clean_train: TransactionSet, cfg: Config
) -> dict[str, dict[str, Any]]:
    """Stretch goal US-009: separate rule sets for new vs repeat customers."""
    out: dict[str, dict[str, Any]] = {}
    if not cfg.cohorts.enabled:
        return out
    for cohort in (COHORT_NEW, COHORT_REPEAT):
        subset = clean_train.by_cohort(cohort)
        if len(subset) < 100:
            log.warning("Cohort %r has only %s baskets; skipping", cohort, len(subset))
            continue
        result = mine(subset, cfg.mining)
        out[cohort] = {
            "baskets": len(subset),
            "rules": result.rules,
            "stats": result.stats,
        }
        log.info("Cohort %-7s %6s baskets -> %s rules", cohort, len(subset), len(result.rules))
    return out


def _cache_key(cfg: Config, data_sha: str) -> str:
    """Prepared data depends on the raw file and the data-stage settings only."""
    payload = json.dumps(
        {
            "data": data_sha,
            "preprocessing": cfg.to_dict()["preprocessing"],
            "split": cfg.to_dict()["split"],
            "cohorts": cfg.to_dict()["cohorts"],
            "seed": cfg.evaluation.random_seed,
        },
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def prepare(cfg: Config, use_cache: bool = True) -> PreparedData:
    """Steps 1-5: ingest, clean, build baskets, split, restrict to eligible products.

    Reading and cleaning the 23 MB spreadsheet takes most of the pipeline's
    wall-clock time, so the result is cached under ``data/interim`` keyed by the
    raw-file hash plus the data-stage configuration. Change either and the cache
    key changes with it, so a stale cache cannot silently be reused.
    """
    # 1 -- ingest ----------------------------------------------------------
    raw_path = cfg.raw_data_path
    dataset_meta = file_fingerprint(raw_path)
    dataset_meta["source"] = "UCI Machine Learning Repository / Kaggle 'Online Retail' dataset"

    cache_path = cfg.interim_dir / f"prepared-{_cache_key(cfg, dataset_meta['sha256'])}.pkl"
    if use_cache and cache_path.exists():
        log.info("Reusing prepared data cache %s", cache_path.name)
        with cache_path.open("rb") as fh:
            return pickle.load(fh)

    raw = load_raw(raw_path)
    dataset_meta["rows"] = int(len(raw))

    # 2 -- clean -----------------------------------------------------------
    cleaning = clean_transactions(raw, cfg.preprocessing)
    checks = validate_clean(cleaning.frame, cfg.preprocessing)
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise RuntimeError(f"Cleaned dataset failed validation: {failed}")

    # 3 -- catalog + baskets ----------------------------------------------
    catalog = build_product_catalog(cleaning.frame)
    transactions = build_transactions(cleaning.frame, cfg.preprocessing, cfg.cohorts)

    # 4 -- chronological split --------------------------------------------
    splits = split_transactions(transactions, cfg.split, seed=cfg.evaluation.random_seed)

    # 5 -- product eligibility decided on TRAIN only (no look-ahead) -------
    train_counts = splits["train"].item_counts()
    eligible = list(train_counts[train_counts >= cfg.preprocessing.min_product_invoices].index)
    log.info(
        "Products eligible for mining: %s/%s (>=%s training invoices)",
        f"{len(eligible):,}",
        f"{len(train_counts):,}",
        cfg.preprocessing.min_product_invoices,
    )
    splits = {
        name: part.restrict_products(eligible, cfg.preprocessing.min_basket_size)
        for name, part in splits.items()
    }

    prepared = PreparedData(
        dataset=dataset_meta,
        cleaning_audit=cleaning.audit,
        cleaning_summary=cleaning.summary(),
        validation_checks=checks,
        catalog=catalog,
        catalog_mined=catalog[catalog["StockCode"].isin(set(eligible))].reset_index(drop=True),
        transactions_describe=transactions.describe(),
        splits=splits,
        eligible_products=eligible,
        invoice_meta=transactions.meta,
        n_products_total=int(len(catalog)),
    )
    if use_cache:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with cache_path.open("wb") as fh:
            pickle.dump(prepared, fh, protocol=pickle.HIGHEST_PROTOCOL)
        log.info("Cached prepared data at %s", cache_path)
    return prepared


def train(
    cfg: Config,
    save_processed: bool = True,
    prepared: PreparedData | None = None,
    use_cache: bool = True,
) -> TrainResult:
    """Run the full pipeline and persist a versioned rule set."""
    prepared = prepared or prepare(cfg, use_cache=use_cache)
    dataset_meta = prepared.dataset
    splits = prepared.splits
    catalog = prepared.catalog
    catalog_mined = prepared.catalog_mined
    eligible = prepared.eligible_products
    checks = prepared.validation_checks

    # 6 -- mine on train ---------------------------------------------------
    mining = mine(splits["train"], cfg.mining)
    if mining.rules.empty:
        raise RuntimeError(
            "No association rule cleared the thresholds. Lower mining.min_support / "
            "min_confidence / min_lift in config/config.yaml and retrain."
        )

    popularity = _popularity(splits["train"])
    recommender = Recommender(
        rules=mining.rules,
        catalog=catalog_mined,
        popularity=popularity,
        cfg=cfg.recommendation,
        ruleset_version="pending",
    )

    # 7 -- evaluate --------------------------------------------------------
    test_eval = evaluation_mod.evaluate(
        recommender,
        mining.rules,
        splits["test"],
        k=cfg.evaluation.k,
        seed=cfg.evaluation.random_seed,
        max_baskets=cfg.evaluation.max_eval_baskets,
        label="test",
    )
    validation_eval = evaluation_mod.leave_one_out_replay(
        recommender,
        splits["validation"],
        k=cfg.evaluation.k,
        seed=cfg.evaluation.random_seed,
        max_baskets=cfg.evaluation.max_eval_baskets,
    )
    evaluation = {
        "test": test_eval,
        "validation_replay": validation_eval,
        "split_sizes": {name: len(part) for name, part in splits.items()},
    }

    # 8 -- cohort rule sets -------------------------------------------------
    cohort_results = _mine_cohorts(splits["train"], cfg)

    # 9 -- persist ----------------------------------------------------------
    version = make_version(dataset_meta["sha256"], cfg)
    recommender.ruleset_version = version
    out_dir = cfg.artifacts_dir / version
    out_dir.mkdir(parents=True, exist_ok=True)

    write_rules_csv(mining.rules, out_dir / "rules.csv")
    write_itemsets_csv(mining.itemsets, out_dir / "itemsets.csv")
    catalog_mined.to_csv(out_dir / "products.csv", index=False)
    popularity.rename("support").rename_axis("StockCode").reset_index().to_csv(
        out_dir / "popularity.csv", index=False
    )
    prepared.cleaning_audit.to_csv(out_dir / "cleaning_audit.csv", index=False)
    (out_dir / "evaluation.json").write_text(
        json.dumps(evaluation, indent=2, default=str), encoding="utf-8"
    )

    simulation = _default_simulation(
        cfg, catalog_mined, mining.rules, splits["test"], test_eval["replay"]
    )
    (out_dir / "simulation.json").write_text(
        json.dumps(simulation, indent=2, default=str), encoding="utf-8"
    )

    cohort_summary: dict[str, Any] = {}
    for cohort, payload in cohort_results.items():
        cdir = out_dir / "cohorts" / cohort
        cdir.mkdir(parents=True, exist_ok=True)
        write_rules_csv(payload["rules"], cdir / "rules.csv")
        cohort_summary[cohort] = {"baskets": payload["baskets"], **payload["stats"]}

    data_summary = {
        "cleaning": prepared.cleaning_summary,
        "validation_checks": checks,
        "baskets": prepared.transactions_describe,
        "splits": {name: part.describe() for name, part in splits.items()},
        "products_in_catalog": prepared.n_products_total,
        "products_eligible_for_mining": int(len(eligible)),
    }
    manifest = build_manifest(
        ruleset_version=version,
        config=cfg,
        dataset=dataset_meta,
        data_summary=data_summary,
        mining={
            "engine": mining.engine,
            "elapsed_seconds": round(mining.elapsed_seconds, 2),
            **mining.stats,
            "cohorts": cohort_summary,
        },
        evaluation={
            "k": cfg.evaluation.k,
            "test_hit_rate_at_k": test_eval["replay"].get("hit_rate_at_k"),
            "test_basket_coverage": test_eval["replay"].get("basket_coverage"),
            "popularity_baseline_hit_rate": test_eval["replay"].get(
                "popularity_baseline_hit_rate"
            ),
            "catalog_coverage": test_eval["catalog_coverage"].get("coverage"),
        },
    )
    write_manifest(out_dir / "manifest.json", manifest)
    write_latest_pointer(cfg.artifacts_dir, version)

    if save_processed:
        cfg.processed_dir.mkdir(parents=True, exist_ok=True)
        catalog.to_csv(cfg.processed_dir / "product_catalog.csv", index=False)
        prepared.invoice_meta.to_csv(cfg.processed_dir / "invoice_meta.csv")
        with (cfg.processed_dir / "baskets_train.txt").open("w", encoding="utf-8") as fh:
            for inv, items in zip(
                splits["train"].invoice_ids, splits["train"].itemsets, strict=True
            ):
                fh.write(f"{inv}\t{' '.join(sorted(items))}\n")

    log.info("Rule set %s written to %s", version, out_dir)
    return TrainResult(
        ruleset_version=version,
        artifacts_dir=out_dir,
        mining=mining,
        evaluation=evaluation,
        manifest=manifest,
        splits=splits,
        recommender=recommender,
    )
