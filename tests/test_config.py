"""Configuration loading, validation and fingerprinting."""

from __future__ import annotations

from dataclasses import replace

import pytest
import yaml

from crosssell.config import DEFAULT_CONFIG_PATH, Config, load_config


def test_shipped_config_loads():
    cfg = load_config()
    assert cfg.mining.min_support > 0
    assert cfg.recommendation.top_k >= 1
    assert cfg.split.train_fraction + cfg.split.validation_fraction + cfg.split.test_fraction == 1.0


def test_shipped_config_has_no_unknown_keys():
    raw = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text())
    Config.from_dict(raw)  # raises on an unknown section or key


def test_unknown_section_is_rejected():
    with pytest.raises(ValueError, match="Unknown configuration section"):
        Config.from_dict({"nonsense": {}})


def test_unknown_key_is_rejected():
    with pytest.raises(ValueError, match="Unknown configuration key"):
        Config.from_dict({"mining": {"min_suport": 0.1}})


@pytest.mark.parametrize(
    "section,payload,message",
    [
        ("split", {"train_fraction": 0.5, "validation_fraction": 0.2,
                   "test_fraction": 0.2}, "sum to 1.0"),
        ("split", {"strategy": "magic"}, "temporal"),
        ("mining", {"engine": "spark"}, "builtin"),
        ("mining", {"min_support": 0}, "min_support"),
        ("mining", {"min_support": 1.5}, "min_support"),
        ("mining", {"max_itemset_size": 1}, "max_itemset_size"),
        ("recommendation", {"rank_by": ["magic"]}, "unknown metric"),
        ("recommendation", {"fallback": "guess"}, "fallback"),
    ],
)
def test_invalid_values_are_rejected(section, payload, message):
    with pytest.raises(ValueError, match=message):
        Config.from_dict({section: payload})


def test_fingerprint_changes_with_modelling_settings():
    base = load_config()
    changed = replace(base, mining=replace(base.mining, min_support=base.mining.min_support / 2))
    assert base.fingerprint() != changed.fingerprint()


def test_fingerprint_ignores_paths_and_api_settings():
    """Moving a file or changing CORS must not invalidate a rule set."""
    base = load_config()
    moved = replace(
        base,
        paths=replace(base.paths, raw_data="somewhere/else.xlsx"),
        api=replace(base.api, cors_origins=["http://example.test"]),
    )
    assert base.fingerprint() == moved.fingerprint()


def test_fingerprint_is_stable_across_loads():
    assert load_config().fingerprint() == load_config().fingerprint()


def test_to_dict_round_trips():
    cfg = load_config()
    assert Config.from_dict(cfg.to_dict()).fingerprint() == cfg.fingerprint()


def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_config("does/not/exist.yaml")


def test_relative_paths_resolve_against_the_repo_root():
    cfg = load_config()
    assert cfg.artifacts_dir.is_absolute()
    assert cfg.raw_data_path.is_absolute()
