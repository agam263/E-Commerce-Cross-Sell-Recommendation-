"""Typed configuration objects loaded from ``config/config.yaml``.

The whole configuration is serialisable back to a plain dict so it can be
embedded verbatim in the rule-set manifest (PRD FR-10 / US-004).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

import yaml


def _resolve_repo_root() -> Path:
    """Resolve the repository root for editable, source, and installed layouts."""
    candidate = Path(__file__).resolve().parents[2]
    if (candidate / "config" / "config.yaml").exists():
        return candidate
    cwd = Path.cwd()
    if (cwd / "config" / "config.yaml").exists():
        return cwd
    return candidate


REPO_ROOT = _resolve_repo_root()
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "config.yaml"


def _build(cls: type, data: dict[str, Any] | None) -> Any:
    """Instantiate a dataclass from a dict, ignoring unknown keys loudly."""
    data = dict(data or {})
    known = {f.name for f in fields(cls)}
    unknown = set(data) - known
    if unknown:
        raise ValueError(f"Unknown configuration key(s) for {cls.__name__}: {sorted(unknown)}")
    return cls(**data)


@dataclass(frozen=True)
class ProjectConfig:
    name: str = "crosssell"
    ruleset_version: str = "auto"


@dataclass(frozen=True)
class PathsConfig:
    raw_data: str = "data/raw/Online Retail.xlsx"
    interim_dir: str = "data/interim"
    processed_dir: str = "data/processed"
    artifacts_dir: str = "artifacts"
    reports_dir: str = "reports"


@dataclass(frozen=True)
class PreprocessingConfig:
    drop_exact_duplicates: bool = True
    exclude_cancellations: bool = True
    require_positive_quantity: bool = True
    require_positive_unit_price: bool = True
    drop_missing_customer_id: bool = False
    drop_non_product_codes: bool = True
    non_product_stock_codes: list[str] = field(default_factory=list)
    non_product_code_patterns: list[str] = field(default_factory=list)
    country: str | None = None
    min_basket_size: int = 2
    min_product_invoices: int = 5


@dataclass(frozen=True)
class SplitConfig:
    strategy: str = "temporal"
    train_fraction: float = 0.70
    validation_fraction: float = 0.15
    test_fraction: float = 0.15

    def __post_init__(self) -> None:
        total = self.train_fraction + self.validation_fraction + self.test_fraction
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"split fractions must sum to 1.0, got {total}")
        if self.strategy not in {"temporal", "random"}:
            raise ValueError("split.strategy must be 'temporal' or 'random'")


@dataclass(frozen=True)
class MiningConfig:
    engine: str = "builtin"
    min_support: float = 0.01
    max_itemset_size: int = 3
    min_confidence: float = 0.2
    min_lift: float = 1.0
    min_antecedent_count: int = 1
    max_consequent_size: int = 1

    def __post_init__(self) -> None:
        if self.engine not in {"builtin", "mlxtend"}:
            raise ValueError("mining.engine must be 'builtin' or 'mlxtend'")
        if not 0 < self.min_support <= 1:
            raise ValueError("mining.min_support must be in (0, 1]")
        if self.max_itemset_size < 2:
            raise ValueError("mining.max_itemset_size must be >= 2 to produce rules")


@dataclass(frozen=True)
class RecommendationConfig:
    top_k: int = 5
    # Lexicographic ranking order. Confidence first: min_lift already acts as a
    # hard admission filter, so among admitted rules the quantity worth
    # maximising is P(consequent | antecedent). Validated on the validation
    # split; see reports/evaluation_report.md.
    rank_by: list[str] = field(default_factory=lambda: ["confidence", "lift", "support"])
    fallback: str = "popularity"
    fallback_size: int = 5

    def __post_init__(self) -> None:
        allowed = {"lift", "confidence", "support", "leverage", "conviction"}
        bad = set(self.rank_by) - allowed
        if bad:
            raise ValueError(f"recommendation.rank_by contains unknown metric(s): {sorted(bad)}")
        if self.fallback not in {"popularity", "none"}:
            raise ValueError("recommendation.fallback must be 'popularity' or 'none'")


@dataclass(frozen=True)
class SimulationConfig:
    scenarios: dict[str, float] = field(
        default_factory=lambda: {"conservative": 0.02, "base": 0.05, "optimistic": 0.10}
    )


@dataclass(frozen=True)
class EvaluationConfig:
    k: int = 5
    random_seed: int = 42
    max_eval_baskets: int = 20000


@dataclass(frozen=True)
class CohortConfig:
    enabled: bool = True
    repeat_min_invoices: int = 2


@dataclass(frozen=True)
class ApiConfig:
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173"])
    api_key: str | None = None


@dataclass(frozen=True)
class Config:
    """Root configuration object."""

    project: ProjectConfig = field(default_factory=ProjectConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    preprocessing: PreprocessingConfig = field(default_factory=PreprocessingConfig)
    split: SplitConfig = field(default_factory=SplitConfig)
    mining: MiningConfig = field(default_factory=MiningConfig)
    recommendation: RecommendationConfig = field(default_factory=RecommendationConfig)
    simulation: SimulationConfig = field(default_factory=SimulationConfig)
    evaluation: EvaluationConfig = field(default_factory=EvaluationConfig)
    cohorts: CohortConfig = field(default_factory=CohortConfig)
    api: ApiConfig = field(default_factory=ApiConfig)
    source_path: str | None = None

    # -- construction -------------------------------------------------------
    @classmethod
    def from_dict(cls, raw: dict[str, Any], source_path: str | None = None) -> Config:
        raw = dict(raw or {})
        sections = {
            "project": ProjectConfig,
            "paths": PathsConfig,
            "preprocessing": PreprocessingConfig,
            "split": SplitConfig,
            "mining": MiningConfig,
            "recommendation": RecommendationConfig,
            "simulation": SimulationConfig,
            "evaluation": EvaluationConfig,
            "cohorts": CohortConfig,
            "api": ApiConfig,
        }
        unknown = set(raw) - set(sections)
        if unknown:
            raise ValueError(f"Unknown configuration section(s): {sorted(unknown)}")
        kwargs = {name: _build(klass, raw.get(name)) for name, klass in sections.items()}
        return cls(source_path=source_path, **kwargs)

    @classmethod
    def load(cls, path: str | Path | None = None) -> Config:
        path = Path(path) if path else DEFAULT_CONFIG_PATH
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")
        with path.open("r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        return cls.from_dict(raw, source_path=str(path))

    # -- serialisation ------------------------------------------------------
    def to_dict(self, include_source: bool = False) -> dict[str, Any]:
        out = {
            f.name: (asdict(getattr(self, f.name)) if is_dataclass(getattr(self, f.name))
                     else getattr(self, f.name))
            for f in fields(self)
        }
        if not include_source:
            out.pop("source_path", None)
        return out

    def fingerprint(self) -> str:
        """Stable 12-char hash of the settings that influence the rule set.

        ``api`` and ``paths`` are excluded: moving a file or changing CORS does
        not change the mined rules.
        """
        relevant = {
            k: v for k, v in self.to_dict().items()
            if k not in {"api", "paths", "project", "source_path"}
        }
        payload = json.dumps(relevant, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:12]

    # -- path helpers -------------------------------------------------------
    def resolve(self, relative: str | Path) -> Path:
        p = Path(relative)
        return p if p.is_absolute() else (REPO_ROOT / p)

    @property
    def raw_data_path(self) -> Path:
        return self.resolve(self.paths.raw_data)

    @property
    def processed_dir(self) -> Path:
        return self.resolve(self.paths.processed_dir)

    @property
    def interim_dir(self) -> Path:
        return self.resolve(self.paths.interim_dir)

    @property
    def artifacts_dir(self) -> Path:
        return self.resolve(self.paths.artifacts_dir)

    @property
    def reports_dir(self) -> Path:
        return self.resolve(self.paths.reports_dir)


def load_config(path: str | Path | None = None) -> Config:
    """Convenience wrapper around :meth:`Config.load`."""
    return Config.load(path)
