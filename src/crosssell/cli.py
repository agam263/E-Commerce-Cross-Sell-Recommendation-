"""Command-line entry point for the cross-sell pipeline.

    python -m crosssell.cli train                 # mine + evaluate + version a rule set
    python -m crosssell.cli tune                  # threshold sweep on the VALIDATION split
    python -m crosssell.cli evaluate              # re-evaluate the active rule set
    python -m crosssell.cli report                # markdown evaluation report + figures
    python -m crosssell.cli recommend 85123A      # ad-hoc recommendations in the terminal
    python -m crosssell.cli info                  # what is the active rule set?
    python -m crosssell.cli serve                 # run the FastAPI app
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from crosssell import __version__
from crosssell.config import Config, load_config


def _setup_logging(verbosity: int) -> None:
    level = logging.WARNING if verbosity < 0 else logging.INFO if verbosity == 0 else logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-7s %(name)-28s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("matplotlib").setLevel(logging.WARNING)


def _load(args: argparse.Namespace) -> Config:
    return load_config(args.config)


# ---------------------------------------------------------------- commands --
def cmd_train(args: argparse.Namespace) -> int:
    from crosssell.pipeline import train

    cfg = _load(args)
    result = train(cfg, save_processed=not args.no_processed, use_cache=not args.no_cache)
    manifest = result.manifest
    print("\n" + "=" * 78)
    print(f"Rule set      : {result.ruleset_version}")
    print(f"Artifacts     : {result.artifacts_dir}")
    train_invoices = manifest["data_summary"]["splits"]["train"]["invoices"]
    print(f"Transactions  : {train_invoices:,} training baskets")
    print(f"Itemsets      : {manifest['mining']['frequent_itemsets']:,} "
          f"{manifest['mining']['frequent_itemsets_by_length']}")
    print(f"Rules         : {manifest['mining']['rules']:,}")
    ev = manifest["evaluation"]
    print(f"hit@{ev['k']} (test) : {ev['test_hit_rate_at_k']:.4f}  "
          f"(popularity baseline {ev['popularity_baseline_hit_rate']:.4f})")
    print(f"Coverage      : {ev['catalog_coverage']:.1%} of catalog products have a rule")
    print("=" * 78)
    return 0


def cmd_tune(args: argparse.Namespace) -> int:
    """Grid-search serving thresholds on the validation split only."""
    import pandas as pd

    from crosssell.evaluation import threshold_sweep
    from crosssell.pipeline import prepare
    from crosssell.service.store import RuleStore

    cfg = _load(args)
    prepared = prepare(cfg, use_cache=not args.no_cache)
    store = RuleStore.from_config(cfg, args.rules_version)

    sweep = threshold_sweep(
        store.recommender,
        prepared.splits["validation"],
        confidences=[float(c) for c in args.confidences],
        lifts=[float(lift) for lift in args.lifts],
        k=cfg.evaluation.k,
        seed=cfg.evaluation.random_seed,
        max_baskets=args.max_baskets,
    )
    out = cfg.reports_dir / "threshold_sweep.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    sweep.to_csv(out, index=False)

    with pd.option_context("display.width", 120, "display.float_format", "{:.4f}".format):
        print("\nValidation-split threshold sweep (test split untouched):\n")
        print(sweep.to_string(index=False))
    print(f"\nSaved to {out}")
    print(
        "\nPick a row, write min_confidence / min_lift into config/config.yaml, "
        "then re-run `train` so the stored rule set matches the chosen thresholds."
    )
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    from crosssell.evaluation import evaluate
    from crosssell.pipeline import prepare
    from crosssell.service.store import RuleStore

    cfg = _load(args)
    prepared = prepare(cfg, use_cache=not args.no_cache)
    store = RuleStore.from_config(cfg, args.rules_version)
    result = evaluate(
        store.recommender,
        store.artifacts.rules,
        prepared.splits[args.split],
        k=args.k or cfg.evaluation.k,
        seed=cfg.evaluation.random_seed,
        max_baskets=cfg.evaluation.max_eval_baskets,
        label=args.split,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    from crosssell.report import build_report

    cfg = _load(args)
    path = build_report(cfg, version=args.rules_version)
    print(f"Evaluation report written to {path}")
    return 0


def cmd_recommend(args: argparse.Namespace) -> int:
    from crosssell.service.recommender import UnknownProductError
    from crosssell.service.store import RuleStore

    cfg = _load(args)
    store = RuleStore.from_config(cfg, args.rules_version)
    recommender = store.for_cohort(args.cohort)
    try:
        recs = recommender.recommend(args.products, top_k=args.top_k)
    except UnknownProductError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    basket = ", ".join(f"{p} ({recommender.product_name(p)})" for p in args.products)
    print(f"\nBasket      : {basket}")
    print(f"Rule set    : {recommender.ruleset_version}\n")
    if not recs:
        print("No recommendation available (and fallback is disabled).")
        return 0
    for rec in recs:
        metrics = (
            f"support={rec.support:.4f} confidence={rec.confidence:.3f} lift={rec.lift:.2f}"
            if rec.source == "association_rule"
            else f"popularity={rec.popularity_support:.4f}"
        )
        print(f"{rec.rank}. {rec.stock_code:<9} {rec.product_name[:48]:<50} [{rec.source}]")
        print(f"   {metrics}")
        print(f"   {rec.explanation}\n")
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    from crosssell.service.store import RuleStore

    cfg = _load(args)
    store = RuleStore.from_config(cfg, args.rules_version)
    m = store.manifest
    print(json.dumps(
        {
            "ruleset_version": m.get("ruleset_version"),
            "built_at": m.get("built_at"),
            "dataset": m.get("dataset"),
            "mining": {k: v for k, v in m.get("mining", {}).items() if k != "cohorts"},
            "evaluation": m.get("evaluation"),
            "thresholds": m.get("configuration", {}).get("mining"),
            "cohorts": store.cohorts,
            "artifacts": str(store.artifacts.directory),
        },
        indent=2,
        default=str,
    ))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "crosssell.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        factory=False,
    )
    return 0


# ------------------------------------------------------------------ parser --
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crosssell",
        description="Apriori cross-sell recommendation engine",
    )
    parser.add_argument("--version", action="version", version=f"crosssell {__version__}")
    parser.add_argument(
        "-c", "--config", type=Path, default=None, help="path to config.yaml"
    )
    parser.add_argument(
        "-q", "--quiet", dest="verbosity", action="store_const", const=-1, default=0
    )
    parser.add_argument("-v", "--verbose", dest="verbosity", action="store_const", const=1)
    sub = parser.add_subparsers(dest="command", required=True)

    def add_rules_version(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--rules-version", default=None,
            help="rule-set version to use (default: the one in artifacts/latest.json)",
        )

    p_train = sub.add_parser("train", help="run the full pipeline and version a rule set")
    p_train.add_argument("--no-cache", action="store_true", help="ignore the prepared-data cache")
    p_train.add_argument("--no-processed", action="store_true", help="skip writing data/processed")
    p_train.set_defaults(func=cmd_train)

    p_tune = sub.add_parser("tune", help="threshold sweep on the validation split")
    add_rules_version(p_tune)
    p_tune.add_argument("--no-cache", action="store_true")
    p_tune.add_argument("--confidences", nargs="+", default=[0.1, 0.2, 0.3, 0.4, 0.5])
    p_tune.add_argument("--lifts", nargs="+", default=[1.0, 1.5, 2.0, 3.0])
    p_tune.add_argument("--max-baskets", type=int, default=4000)
    p_tune.set_defaults(func=cmd_tune)

    p_eval = sub.add_parser("evaluate", help="evaluate the active rule set on a split")
    add_rules_version(p_eval)
    p_eval.add_argument("--split", choices=["train", "validation", "test"], default="test")
    p_eval.add_argument("--k", type=int, default=None)
    p_eval.add_argument("--no-cache", action="store_true")
    p_eval.set_defaults(func=cmd_evaluate)

    p_report = sub.add_parser("report", help="write the markdown evaluation report + figures")
    add_rules_version(p_report)
    p_report.set_defaults(func=cmd_report)

    p_rec = sub.add_parser("recommend", help="recommend cross-sell products for a basket")
    p_rec.add_argument("products", nargs="+", help="one or more StockCode values")
    p_rec.add_argument("-k", "--top-k", type=int, default=None)
    p_rec.add_argument("--cohort", default=None, help="all | new | repeat")
    add_rules_version(p_rec)
    p_rec.set_defaults(func=cmd_recommend)

    p_info = sub.add_parser("info", help="show the active rule-set manifest summary")
    add_rules_version(p_info)
    p_info.set_defaults(func=cmd_info)

    p_serve = sub.add_parser("serve", help="run the FastAPI application")
    p_serve.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    p_serve.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    p_serve.add_argument("--reload", action="store_true")
    p_serve.set_defaults(func=cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging(args.verbosity)
    try:
        return int(args.func(args))
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
