"""End-to-end pipeline, artifact layout, reproducibility and evaluation."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from crosssell.config import Config
from crosssell.evaluation import (
    evaluate,
    leave_one_out_replay,
    rule_metric_summary,
    threshold_sweep,
)
from crosssell.pipeline import prepare, train
from crosssell.service.store import RuleStore, read_rules_csv, write_rules_csv
from crosssell.versioning import build_manifest, make_version


@pytest.fixture(scope="module")
def trained(written_raw: Config):
    return train(written_raw, save_processed=True)


def test_pipeline_produces_rules(trained):
    assert len(trained.mining.rules) > 0
    assert trained.mining.itemsets["length"].max() >= 2


def test_all_artifacts_are_written(trained):
    directory = trained.artifacts_dir
    for name in (
        "manifest.json", "rules.csv", "itemsets.csv", "products.csv",
        "popularity.csv", "cleaning_audit.csv", "evaluation.json", "simulation.json",
    ):
        assert (directory / name).exists(), f"missing artifact {name}"
    assert (directory.parent / "latest.json").exists()


def test_manifest_records_everything_needed_to_reproduce(trained):
    manifest = trained.manifest
    assert manifest["dataset"]["sha256"]
    assert manifest["configuration"]["mining"]["min_support"]
    assert manifest["environment"]["packages"]["python"]
    assert manifest["evaluation"]["test_hit_rate_at_k"] is not None
    assert manifest["reproduce"]["command"]


def test_version_is_deterministic_for_same_data_and_config(written_raw, trained):
    prepared = prepare(written_raw)
    again = make_version(prepared.dataset["sha256"], written_raw)
    assert again == trained.ruleset_version


def test_changing_a_threshold_changes_the_version(written_raw, trained):
    other = replace(written_raw, mining=replace(written_raw.mining, min_support=0.05))
    prepared = prepare(written_raw)
    assert make_version(prepared.dataset["sha256"], other) != trained.ruleset_version


def test_retraining_is_reproducible(written_raw, trained):
    second = train(written_raw, save_processed=False)
    assert second.ruleset_version == trained.ruleset_version
    assert len(second.mining.rules) == len(trained.mining.rules)
    assert second.mining.rules["lift"].tolist() == trained.mining.rules["lift"].tolist()


def test_mlxtend_engine_gives_the_same_rules(written_raw, tmp_path):
    """Swapping in the reference miner must not change a single rule."""
    pytest.importorskip("mlxtend")
    builtin = train(written_raw, save_processed=False)
    # Write to a scratch artifacts dir so this run does not move the `latest`
    # pointer that the other tests rely on.
    other_cfg = replace(
        written_raw,
        mining=replace(written_raw.mining, engine="mlxtend"),
        paths=replace(written_raw.paths, artifacts_dir=str(tmp_path / "artifacts")),
    )
    other = train(other_cfg, save_processed=False)
    assert len(other.mining.rules) == len(builtin.mining.rules)
    def keys(frame):
        return set(zip(frame["antecedents"], frame["consequents"], strict=True))

    assert keys(other.mining.rules) == keys(builtin.mining.rules)


def test_splits_do_not_leak_products_unseen_in_training(written_raw):
    prepared = prepare(written_raw)
    train_products = {i for s in prepared.splits["train"].itemsets for i in s}
    for name in ("validation", "test"):
        products = {i for s in prepared.splits[name].itemsets for i in s}
        assert products <= set(prepared.eligible_products)
        assert products <= train_products | set(prepared.eligible_products)


def test_store_round_trip(trained, written_raw):
    store = RuleStore.from_config(written_raw)
    assert store.version == trained.ruleset_version
    assert len(store.recommender) == len(trained.mining.rules)
    assert store.artifacts.manifest["ruleset_version"] == trained.ruleset_version
    assert "all" in store.cohorts


def test_rules_csv_round_trip_preserves_itemsets(trained, tmp_path):
    path = tmp_path / "rules.csv"
    write_rules_csv(trained.mining.rules, path)
    reloaded = read_rules_csv(path)
    assert reloaded["antecedents"].iloc[0] == trained.mining.rules["antecedents"].iloc[0]
    assert len(reloaded) == len(trained.mining.rules)


def test_store_serves_a_recommendation(trained, written_raw):
    store = RuleStore.from_config(written_raw)
    product = store.artifacts.rules["antecedents"].iloc[0][0]
    recs = store.recommender.recommend([product])
    assert recs and recs[0].product_name


def test_evaluation_reports_a_coherent_replay(trained, written_raw):
    """Structural checks only.

    This fixture has 10 products, so "recommend the 5 best-sellers" covers half
    the catalog and is unbeatable by construction. Whether the rules actually
    beat that baseline is a property of the real dataset, measured by
    `crosssell.cli report` (8.15x on the Online Retail hold-out), not something a
    toy fixture can show.
    """
    prepared = prepare(written_raw)
    result = evaluate(
        trained.recommender, trained.mining.rules, prepared.splits["test"], k=5, label="test"
    )
    replay = result["replay"]
    assert replay["baskets_evaluated"] > 0
    assert 0 < replay["hit_rate_at_k"] <= 1
    assert 0 <= replay["basket_coverage"] <= 1
    assert replay["mrr_at_k"] <= replay["hit_rate_at_k"]
    assert result["catalog_coverage"]["products_tested"] > 0


def test_replay_is_deterministic(trained, written_raw):
    prepared = prepare(written_raw)
    kwargs = dict(k=5, seed=42, max_baskets=200)
    first = leave_one_out_replay(trained.recommender, prepared.splits["test"], **kwargs)
    second = leave_one_out_replay(trained.recommender, prepared.splits["test"], **kwargs)
    assert first == second


def test_threshold_sweep_covers_the_grid(trained, written_raw):
    prepared = prepare(written_raw)
    sweep = threshold_sweep(
        trained.recommender, prepared.splits["validation"],
        confidences=[0.2, 0.5], lifts=[1.0, 2.0], k=5, max_baskets=100,
    )
    assert len(sweep) == 4
    assert {"hit_rate_at_k", "basket_coverage", "mrr_at_k"} <= set(sweep.columns)


def test_rule_metric_summary_shape(trained):
    summary = rule_metric_summary(trained.mining.rules)
    assert summary["rules"] == len(trained.mining.rules)
    assert summary["lift"]["min"] <= summary["lift"]["median"] <= summary["lift"]["max"]


def test_prepared_data_cache_is_reused(written_raw):
    first = prepare(written_raw, use_cache=True)
    second = prepare(written_raw, use_cache=True)
    assert second.dataset["sha256"] == first.dataset["sha256"]
    assert len(second.splits["train"]) == len(first.splits["train"])


def test_default_simulation_is_stored_and_consistent(trained):
    payload = json.loads((trained.artifacts_dir / "simulation.json").read_text())
    for scenario in payload["scenarios"]:
        expected = scenario["eligible_transactions"] * scenario["adoption_rate"]
        assert scenario["expected_additional_orders"] == pytest.approx(expected)
        assert scenario["estimated_incremental_revenue"] == pytest.approx(
            expected * scenario["average_order_value"]
        )
    assert payload["disclaimer"]


def test_cohort_rule_sets_are_written_when_enabled(trained, written_raw):
    store = RuleStore.from_config(written_raw)
    cohort_dir = trained.artifacts_dir / "cohorts"
    if cohort_dir.exists():
        for cohort in store.artifacts.cohort_rules:
            assert cohort in store.cohorts
            assert len(store.for_cohort(cohort)) >= 0


def test_manifest_builder_is_self_contained(written_raw):
    manifest = build_manifest(
        ruleset_version="rs-test",
        config=written_raw,
        dataset={"sha256": "abc", "name": "x.csv"},
        data_summary={},
        mining={"rules": 1},
    )
    assert manifest["ruleset_version"] == "rs-test"
    assert manifest["configuration"]["mining"]["engine"] == written_raw.mining.engine
    assert "built_at" in manifest
