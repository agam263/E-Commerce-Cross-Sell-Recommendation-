"""Persistence and loading of versioned rule-set artifacts.

Artifacts are plain CSV/JSON so a reviewer can open any of them without special
tooling (PRD US-008 "reproduce and evaluate the project")::

    artifacts/
      latest.json                     pointer to the active rule set
      <ruleset_version>/
        manifest.json                 full reproducibility manifest
        rules.csv                     association rules + metrics
        itemsets.csv                  frequent itemsets
        products.csv                  product catalog (names, revenue stats)
        popularity.csv                per-product support (fallback + baseline)
        cleaning_audit.csv            rows removed by each cleaning stage
        evaluation.json               hold-out evaluation results
        simulation.json               default revenue-impact scenarios
        cohorts/<cohort>/rules.csv    stretch goal: cohort-specific rule sets
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from crosssell.config import Config, RecommendationConfig
from crosssell.service.recommender import Recommender

log = logging.getLogger(__name__)

LATEST_POINTER = "latest.json"
ITEM_SEPARATOR = "|"

_LIST_COLUMNS = ("antecedents", "consequents")


def _encode_items(value) -> str:
    return ITEM_SEPARATOR.join(str(v) for v in value)


def _decode_items(value) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(str(v) for v in value)
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ()
    return tuple(part for part in str(value).split(ITEM_SEPARATOR) if part)


def write_rules_csv(rules: pd.DataFrame, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = rules.copy()
    for col in _LIST_COLUMNS:
        if col in out.columns:
            out[col] = out[col].map(_encode_items)
    out.to_csv(path, index=False)
    return path


def read_rules_csv(path: str | Path) -> pd.DataFrame:
    rules = pd.read_csv(path, dtype={"rule_id": "string"})
    for col in _LIST_COLUMNS:
        if col in rules.columns:
            rules[col] = rules[col].map(_decode_items)
    return rules


def write_itemsets_csv(itemsets: pd.DataFrame, path: str | Path) -> Path:
    path = Path(path)
    out = itemsets.copy()
    if "itemset" in out.columns:
        out["itemset"] = out["itemset"].map(_encode_items)
    out.to_csv(path, index=False)
    return path


def read_itemsets_csv(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if "itemset" in frame.columns:
        frame["itemset"] = frame["itemset"].map(_decode_items)
    return frame


@dataclass
class RuleSetArtifacts:
    """Everything the API needs to serve one rule-set version."""

    version: str
    directory: Path
    rules: pd.DataFrame
    itemsets: pd.DataFrame
    products: pd.DataFrame
    popularity: pd.Series
    manifest: dict
    evaluation: dict = field(default_factory=dict)
    simulation: dict = field(default_factory=dict)
    cleaning_audit: pd.DataFrame | None = None
    cohort_rules: dict[str, pd.DataFrame] = field(default_factory=dict)


class RuleStore:
    """Loads a rule set from disk and exposes ready-to-serve recommenders."""

    def __init__(self, artifacts: RuleSetArtifacts, recommendation_cfg: RecommendationConfig):
        self.artifacts = artifacts
        self.cfg = recommendation_cfg
        self.recommender = Recommender(
            rules=artifacts.rules,
            catalog=artifacts.products,
            popularity=artifacts.popularity,
            cfg=recommendation_cfg,
            ruleset_version=artifacts.version,
        )
        self._triggerable: frozenset[str] | None = None
        self.cohort_recommenders: dict[str, Recommender] = {
            cohort: Recommender(
                rules=frame,
                catalog=artifacts.products,
                popularity=artifacts.popularity,
                cfg=recommendation_cfg,
                ruleset_version=f"{artifacts.version}:{cohort}",
            )
            for cohort, frame in artifacts.cohort_rules.items()
        }

    # -- accessors ----------------------------------------------------------
    @property
    def version(self) -> str:
        return self.artifacts.version

    @property
    def manifest(self) -> dict:
        return self.artifacts.manifest

    def for_cohort(self, cohort: str | None) -> Recommender:
        if not cohort or cohort == "all":
            return self.recommender
        if cohort not in self.cohort_recommenders:
            raise KeyError(
                f"No rule set for cohort {cohort!r}. "
                f"Available: {sorted(self.cohort_recommenders) or ['all']}"
            )
        return self.cohort_recommenders[cohort]

    @property
    def triggerable_products(self) -> frozenset[str]:
        """Products that appear in at least one rule antecedent (can fire a rule)."""
        if self._triggerable is None:
            self._triggerable = frozenset(
                item for ante in self.artifacts.rules["antecedents"] for item in ante
            )
        return self._triggerable

    @property
    def cohorts(self) -> list[str]:
        return ["all", *sorted(self.cohort_recommenders)]

    # -- loading ------------------------------------------------------------
    @staticmethod
    def resolve_version(artifacts_dir: str | Path, version: str | None = None) -> Path:
        artifacts_dir = Path(artifacts_dir)
        if version:
            directory = artifacts_dir / version
            if not directory.exists():
                raise FileNotFoundError(f"Rule set {version!r} not found in {artifacts_dir}")
            return directory
        pointer = artifacts_dir / LATEST_POINTER
        if pointer.exists():
            payload = json.loads(pointer.read_text(encoding="utf-8"))
            directory = artifacts_dir / payload["ruleset_version"]
            if directory.exists():
                return directory
        candidates = sorted(
            (p for p in artifacts_dir.glob("*/manifest.json")),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            raise FileNotFoundError(
                f"No trained rule set found in {artifacts_dir}. "
                "Run:  python -m crosssell.cli train"
            )
        return candidates[0].parent

    @classmethod
    def load(
        cls,
        artifacts_dir: str | Path,
        version: str | None = None,
        recommendation_cfg: RecommendationConfig | None = None,
    ) -> RuleStore:
        directory = cls.resolve_version(artifacts_dir, version)
        log.info("Loading rule set from %s", directory)

        def _json(name: str) -> dict:
            path = directory / name
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

        manifest = _json("manifest.json")
        products = pd.read_csv(directory / "products.csv", dtype={"StockCode": "string"})
        products["StockCode"] = products["StockCode"].astype(str)
        popularity_frame = pd.read_csv(directory / "popularity.csv", dtype={"StockCode": "string"})
        popularity = pd.Series(
            popularity_frame["support"].to_numpy(),
            index=popularity_frame["StockCode"].astype(str),
            name="support",
        )

        cohort_rules: dict[str, pd.DataFrame] = {}
        cohort_dir = directory / "cohorts"
        if cohort_dir.exists():
            for sub in sorted(cohort_dir.iterdir()):
                rules_path = sub / "rules.csv"
                if rules_path.exists():
                    cohort_rules[sub.name] = read_rules_csv(rules_path)

        audit_path = directory / "cleaning_audit.csv"
        artifacts = RuleSetArtifacts(
            version=manifest.get("ruleset_version", directory.name),
            directory=directory,
            rules=read_rules_csv(directory / "rules.csv"),
            itemsets=read_itemsets_csv(directory / "itemsets.csv"),
            products=products,
            popularity=popularity,
            manifest=manifest,
            evaluation=_json("evaluation.json"),
            simulation=_json("simulation.json"),
            cleaning_audit=pd.read_csv(audit_path) if audit_path.exists() else None,
            cohort_rules=cohort_rules,
        )
        cfg = recommendation_cfg or RecommendationConfig(
            **manifest.get("configuration", {}).get("recommendation", {})
        )
        return cls(artifacts, cfg)

    @classmethod
    def from_config(cls, config: Config, version: str | None = None) -> RuleStore:
        return cls.load(config.artifacts_dir, version, config.recommendation)


def write_latest_pointer(artifacts_dir: str | Path, ruleset_version: str) -> Path:
    artifacts_dir = Path(artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    path = artifacts_dir / LATEST_POINTER
    path.write_text(
        json.dumps({"ruleset_version": ruleset_version}, indent=2) + "\n", encoding="utf-8"
    )
    return path
