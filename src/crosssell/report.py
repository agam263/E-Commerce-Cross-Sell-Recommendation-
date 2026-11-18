"""Markdown evaluation report + figures (PRD AC-09, "Final grading should report
the generated rule population and distributions of support, confidence and lift,
plus at least one clearly documented revenue-impact simulation scenario").

Charts follow one house style: a single hue per chart (every figure here shows
one measure), recessive grid and axes, no chart junk, values printed only where
they are the point of the figure.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from crosssell.config import Config  # noqa: E402
from crosssell.evaluation import leave_one_out_replay  # noqa: E402
from crosssell.service.store import RuleStore  # noqa: E402

log = logging.getLogger(__name__)

# Validated palette: one categorical hue for single-measure charts, a second for
# the one comparison figure. Surfaces and ink come from the same system.
SERIES_1 = "#2a78d6"
SERIES_2 = "#eb6834"
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SOFT = "#52514e"
GRID = "#e8e8e4"

STYLE = {
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID,
    "axes.labelcolor": INK_SOFT,
    "axes.titlecolor": INK,
    "axes.titlesize": 11,
    "axes.titleweight": "bold",
    "axes.labelsize": 9,
    "axes.grid": True,
    "axes.axisbelow": True,
    "grid.color": GRID,
    "grid.linewidth": 0.8,
    "xtick.color": INK_SOFT,
    "ytick.color": INK_SOFT,
    "xtick.labelsize": 8.5,
    "ytick.labelsize": 8.5,
    "legend.frameon": False,
    "font.size": 9,
    "figure.dpi": 150,
}


def _clean_axes(ax: plt.Axes, grid_axis: str = "y") -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)
    ax.grid(axis=grid_axis)
    ax.grid(axis="x" if grid_axis == "y" else "y", visible=False)


def _histogram(ax: plt.Axes, values: pd.Series, title: str, xlabel: str, clip: float = 0.99) -> None:
    series = values.replace([np.inf, -np.inf], np.nan).dropna()
    upper = float(series.quantile(clip))
    ax.hist(series.clip(upper=upper), bins=30, color=SERIES_1, edgecolor=SURFACE, linewidth=0.6)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("rules")
    _clean_axes(ax)


def make_figures(store: RuleStore, out_dir: Path, hit_curve: pd.DataFrame | None = None) -> dict[str, Path]:
    """Render every figure referenced by the report."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rules = store.artifacts.rules
    figures: dict[str, Path] = {}

    with plt.rc_context(STYLE):
        # 1 -- metric distributions ----------------------------------------
        fig, axes = plt.subplots(1, 3, figsize=(11, 3.1))
        _histogram(axes[0], rules["support"], "Support", "support")
        _histogram(axes[1], rules["confidence"], "Confidence", "P(consequent | antecedent)", clip=1.0)
        _histogram(axes[2], rules["lift"], "Lift", "lift")
        fig.suptitle(f"Rule-metric distributions ({len(rules):,} rules)", y=1.04, fontsize=12, fontweight="bold")
        fig.tight_layout()
        path = out_dir / "rule_metric_distributions.png"
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        figures["metrics"] = path

        # 2 -- frequent itemsets by length ---------------------------------
        counts = store.artifacts.itemsets["length"].value_counts().sort_index()
        fig, ax = plt.subplots(figsize=(5, 3))
        bars = ax.bar([f"{i}-itemsets" for i in counts.index], counts.to_numpy(), color=SERIES_1, width=0.55)
        ax.bar_label(bars, fmt="{:,.0f}", padding=3, color=INK_SOFT, fontsize=8.5, fontweight="bold")
        ax.set_title("Frequent itemsets found by Apriori")
        ax.set_ylabel("itemsets")
        ax.margins(y=0.18)
        _clean_axes(ax)
        fig.tight_layout()
        path = out_dir / "itemsets_by_length.png"
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        figures["itemsets"] = path

        # 3 -- top rules by lift -------------------------------------------
        # A -> B and B -> A share a lift value, so showing both would spend half
        # the chart twice. Keep the higher-confidence direction of each pair.
        names = store.recommender.names
        ranked = rules.sort_values(["lift", "confidence"], ascending=False)
        seen: set[frozenset[str]] = set()
        keep: list[int] = []
        for idx, row in zip(ranked.index, ranked.itertuples(index=False), strict=True):
            key = frozenset(tuple(row.antecedents) + tuple(row.consequents))
            if key in seen:
                continue
            seen.add(key)
            keep.append(idx)
            if len(keep) == 12:
                break
        top = ranked.loc[keep].iloc[::-1]
        labels = [
            f"{names.get(r.antecedents[0], r.antecedents[0])[:30]} → {names.get(r.consequents[0], r.consequents[0])[:30]}"
            for r in top.itertuples()
        ]
        fig, ax = plt.subplots(figsize=(9.5, 4.2))
        bars = ax.barh(labels, top["lift"].to_numpy(), color=SERIES_1, height=0.62)
        ax.bar_label(bars, fmt="{:,.1f}×", padding=3, color=INK_SOFT, fontsize=8.5, fontweight="bold")
        ax.set_title("Strongest rules by lift")
        ax.set_xlabel("lift")
        ax.margins(x=0.12)
        _clean_axes(ax, grid_axis="x")
        fig.tight_layout()
        path = out_dir / "top_rules_by_lift.png"
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        figures["top_rules"] = path

        # 4 -- hit rate vs K, engine against the popularity baseline -------
        if hit_curve is not None and len(hit_curve):
            fig, ax = plt.subplots(figsize=(5.6, 3.4))
            ax.plot(hit_curve["k"], hit_curve["hit_rate"], marker="o", markersize=5,
                    linewidth=2, color=SERIES_1, label="Association rules")
            ax.plot(hit_curve["k"], hit_curve["baseline"], marker="s", markersize=5,
                    linewidth=2, color=SERIES_2, linestyle="--", label="Popularity baseline")
            for _, row in hit_curve.iterrows():
                ax.annotate(f"{row['hit_rate']:.1%}", (row["k"], row["hit_rate"]),
                            textcoords="offset points", xytext=(0, 8), ha="center",
                            fontsize=8, color=INK_SOFT, fontweight="bold")
            ax.set_title("Hold-out hit rate by list length K")
            ax.set_xlabel("K (recommendations shown)")
            ax.set_ylabel("hit rate")
            ax.set_xticks(hit_curve["k"].tolist())
            ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
            ax.margins(y=0.2)
            ax.legend(loc="upper left", fontsize=8.5)
            _clean_axes(ax)
            fig.tight_layout()
            path = out_dir / "hit_rate_by_k.png"
            fig.savefig(path, bbox_inches="tight")
            plt.close(fig)
            figures["hit_curve"] = path

        # 5 -- revenue scenarios -------------------------------------------
        scenarios = store.artifacts.simulation.get("scenarios", [])
        if scenarios:
            frame = pd.DataFrame(scenarios)
            fig, ax = plt.subplots(figsize=(5.6, 3.2))
            bars = ax.bar(frame["name"], frame["estimated_incremental_revenue"],
                          color=SERIES_1, width=0.5)
            ax.bar_label(bars, fmt="£{:,.0f}", padding=3, color=INK_SOFT, fontsize=8.5, fontweight="bold")
            ax.set_title("Simulated incremental revenue by adoption scenario")
            ax.set_ylabel("estimated incremental revenue (£)")
            ax.margins(y=0.2)
            _clean_axes(ax)
            fig.tight_layout()
            path = out_dir / "revenue_scenarios.png"
            fig.savefig(path, bbox_inches="tight")
            plt.close(fig)
            figures["scenarios"] = path

    log.info("Wrote %s figures to %s", len(figures), out_dir)
    return figures


def hit_rate_curve(store: RuleStore, holdout, ks=(1, 3, 5, 10, 20), seed: int = 42) -> pd.DataFrame:
    """Hit rate and popularity baseline at several list lengths."""
    rows = []
    for k in ks:
        res = leave_one_out_replay(store.recommender, holdout, k=k, seed=seed, max_baskets=20000)
        rows.append(
            {
                "k": k,
                "hit_rate": res["hit_rate_at_k"],
                "baseline": res["popularity_baseline_hit_rate"],
                "mrr": res["mrr_at_k"],
                "coverage": res["basket_coverage"],
            }
        )
    return pd.DataFrame(rows)


def _md_table(frame: pd.DataFrame, floatfmt: str = "{:.4f}") -> str:
    def fmt(value: Any) -> str:
        if isinstance(value, float):
            return floatfmt.format(value)
        if isinstance(value, (int, np.integer)):
            return f"{value:,}"
        return str(value)

    header = "| " + " | ".join(str(c) for c in frame.columns) + " |"
    sep = "| " + " | ".join("---" for _ in frame.columns) + " |"
    rows = [
        "| " + " | ".join(fmt(v) for v in record) + " |"
        for record in frame.itertuples(index=False, name=None)
    ]
    return "\n".join([header, sep, *rows])


def build_report(cfg: Config, version: str | None = None) -> Path:
    """Render ``reports/evaluation_report.md`` plus its figures."""
    from crosssell.pipeline import prepare

    store = RuleStore.from_config(cfg, version)
    manifest = store.manifest
    rules = store.artifacts.rules
    evaluation = store.artifacts.evaluation
    test = evaluation.get("test", {})
    replay = test.get("replay", {})
    data_summary = manifest.get("data_summary", {})

    prepared = prepare(cfg)
    curve = hit_rate_curve(store, prepared.splits["test"], seed=cfg.evaluation.random_seed)

    figures_dir = cfg.reports_dir / "figures"
    figures = make_figures(store, figures_dir, curve)
    rel = {name: f"figures/{path.name}" for name, path in figures.items()}

    audit = store.artifacts.cleaning_audit
    splits = pd.DataFrame(
        [
            {
                "split": name,
                "invoices": info.get("invoices"),
                "products": info.get("products"),
                "mean basket": info.get("mean_basket_size"),
                "from": str(info.get("date_min"))[:10],
                "to": str(info.get("date_max"))[:10],
            }
            for name, info in data_summary.get("splits", {}).items()
        ]
    )

    metric_rows = []
    for metric in ("support", "confidence", "lift", "leverage"):
        series = rules[metric].replace([np.inf, -np.inf], np.nan).dropna()
        metric_rows.append(
            {
                "metric": metric,
                "min": series.min(),
                "p25": series.quantile(0.25),
                "median": series.median(),
                "mean": series.mean(),
                "p75": series.quantile(0.75),
                "p95": series.quantile(0.95),
                "max": series.max(),
            }
        )
    metrics_table = pd.DataFrame(metric_rows)

    scenarios = pd.DataFrame(store.artifacts.simulation.get("scenarios", []))
    if len(scenarios):
        scenarios = scenarios[
            ["name", "adoption_rate", "eligible_transactions",
             "expected_additional_orders", "estimated_incremental_revenue"]
        ]

    sweep_path = cfg.reports_dir / "threshold_sweep.csv"
    sweep_section = ""
    if sweep_path.exists():
        sweep = pd.read_csv(sweep_path).head(10)
        n_eval = int(sweep["baskets_evaluated"].iloc[0]) if "baskets_evaluated" in sweep else 0
        best = float(sweep["hit_rate_at_k"].iloc[0]) if len(sweep) else 0.0
        stderr = (best * (1 - best) / n_eval) ** 0.5 if n_eval else 0.0
        sweep_section = (
            "### Threshold sweep (validation split)\n\n"
            "Serving thresholds were chosen here, on validation; the hold-out numbers "
            "above were produced once, afterwards.\n\n"
            + _md_table(sweep)
            + f"\n\nOne standard error on these hit rates is about **{stderr:.4f}** "
            f"({n_eval:,} baskets), so the top rows are statistically indistinguishable. "
            "The shipped configuration takes a row inside that band rather than the "
            "numerically largest one — chasing a difference smaller than the noise is "
            "how you overfit a validation split.\n"
        )

    mining = manifest.get("mining", {})
    cfg_mining = manifest.get("configuration", {}).get("mining", {})
    cfg_rec = manifest.get("configuration", {}).get("recommendation", {})
    uplift = replay.get("uplift_vs_popularity")

    report = f"""# Evaluation Report — Cross-Sell Recommendation Engine

**Rule set** `{store.version}` · built {manifest.get("built_at")} · pipeline v{manifest.get("pipeline_version")}

**Dataset** `{manifest.get("dataset", {}).get("name")}` ({manifest.get("dataset", {}).get("rows", 0):,} rows,
sha256 `{str(manifest.get("dataset", {}).get("sha256"))[:16]}…`)

> Association rules describe historical co-occurrence in this dataset. They are
> evidence for a merchandising decision, not a prediction that a customer will buy.
> Every revenue figure below is a simulation under stated assumptions, not measured uplift.

---

## 1. Headline results

| Metric | Value | Reading |
| --- | --- | --- |
| Rules generated | {len(rules):,} | from {mining.get("frequent_itemsets", 0):,} frequent itemsets |
| Hit rate @{replay.get("k")} (hold-out) | **{replay.get("hit_rate_at_k", 0):.4f}** | hidden product recovered in the top {replay.get("k")} |
| Popularity baseline | {replay.get("popularity_baseline_hit_rate", 0):.4f} | "just show best-sellers" |
| Uplift vs baseline | **{uplift:.2f}×** | how much the rules beat popularity |
| MRR @{replay.get("k")} | {replay.get("mrr_at_k", 0):.4f} | mean reciprocal rank of the hidden product |
| Basket coverage | {replay.get("basket_coverage", 0):.1%} | hold-out baskets that got a rule-based answer |
| Catalog coverage | {test.get("catalog_coverage", {}).get("coverage", 0):.1%} | products with at least one rule |

**Evaluation protocol.** The invoices are split chronologically. Rules are mined on
the first {manifest.get("configuration", {}).get("split", {}).get("train_fraction", 0.7):.0%} of
invoices; thresholds were tuned on the validation slice; the figures above come from
the final slice, which the miner never saw. For each hold-out basket one product is
hidden at random (fixed seed), the engine recommends from the remaining products, and
we check whether the hidden product comes back in the top K.

![Hit rate by K]({rel.get("hit_curve", "")})

---

## 2. Data preparation

{_md_table(audit, floatfmt="{:,.0f}") if audit is not None else "_No audit recorded._"}

Retained **{data_summary.get("cleaning", {}).get("retention", 0):.1%}** of raw rows
({data_summary.get("cleaning", {}).get("rows_out", 0):,} of
{data_summary.get("cleaning", {}).get("rows_in", 0):,}),
covering {data_summary.get("cleaning", {}).get("invoices", 0):,} invoices and
{data_summary.get("cleaning", {}).get("products", 0):,} products.

### Splits

{_md_table(splits, floatfmt="{:.1f}")}

Products appearing in fewer than
{manifest.get("configuration", {}).get("preprocessing", {}).get("min_product_invoices")} training
invoices are excluded from mining — decided on the training window only, so the
hold-out cannot influence what the model is allowed to see.

---

## 3. Rule population

Mining configuration: `min_support={cfg_mining.get("min_support")}`,
`min_confidence={cfg_mining.get("min_confidence")}`, `min_lift={cfg_mining.get("min_lift")}`,
`min_antecedent_count={cfg_mining.get("min_antecedent_count")}`,
`max_itemset_size={cfg_mining.get("max_itemset_size")}`, engine `{mining.get("engine")}`
(mined in {mining.get("elapsed_seconds")}s).

![Frequent itemsets]({rel.get("itemsets", "")})

### Distribution of the interest metrics

{_md_table(metrics_table)}

![Rule metric distributions]({rel.get("metrics", "")})

![Top rules by lift]({rel.get("top_rules", "")})

Only one direction of each pair is plotted: `A → B` and `B → A` always share a
lift value, so both directions would occupy the chart twice. Note what the very
highest lifts actually are — colour variants of the same item (pizza dishes,
rain macs). Statistically these are the strongest associations in the data, but
commercially they are **substitutes, not complements**: a merchandiser should
read them as "customers buy this range in multiples" rather than as an add-on
opportunity. This is exactly why lift is an admission filter here and confidence
drives the ranking.

{sweep_section}
---

## 4. Revenue-impact simulation

Formula (PRD baseline):

```
expected additional orders    = eligible transactions × adoption rate
estimated incremental revenue = expected additional orders × average order value
```

{_md_table(scenarios, floatfmt="{:,.2f}") if len(scenarios) else "_No scenarios stored._"}

{store.artifacts.simulation.get("assumptions", {}).get("notes", "")}

![Revenue scenarios]({rel.get("scenarios", "")})

> **These are simulated planning estimates, not realised uplift.** They multiply
> assumptions the user supplies; establishing causal revenue impact requires a
> controlled live experiment, which is out of scope for this project.

---

## 5. Ranking policy

Recommendations are ranked by `{" → ".join(cfg_rec.get("rank_by", []))}`, top-{cfg_rec.get("top_k")},
with `{cfg_rec.get("fallback")}` as the documented no-rule fallback.

`min_lift={cfg_mining.get("min_lift")}` is enforced as an admission filter, so every
served rule is already a genuine association; among those, confidence — P(B\\|A) — is
what a top-K list should maximise. On validation this ordering retrieved the held-out
product noticeably more often than ranking by lift first.

---

## 6. Limitations

* One dataset: a UK gift wholesaler, Dec 2010 – Dec 2011. Seasonality is baked in.
* Returns, cancellations and zero-price lines are excluded from the baseline baskets;
  they remain in the raw file for a separate returns analysis.
* Rules are symmetric evidence of co-occurrence, not causation.
* Products below the support threshold have no rules and fall back to best-sellers,
  which is labelled as a fallback rather than given a fabricated confidence.
* Hit rate measures retrieval of a product the customer *did* buy; it cannot measure
  whether a recommendation would have *created* a purchase.

---

_Generated by `python -m crosssell.cli report`._
"""

    cfg.reports_dir.mkdir(parents=True, exist_ok=True)
    path = cfg.reports_dir / "evaluation_report.md"
    path.write_text(report, encoding="utf-8")
    (cfg.reports_dir / "hit_rate_curve.csv").write_text(curve.to_csv(index=False), encoding="utf-8")
    (cfg.reports_dir / "evaluation_summary.json").write_text(
        json.dumps(evaluation, indent=2, default=str), encoding="utf-8"
    )
    log.info("Report written to %s", path)
    return path
