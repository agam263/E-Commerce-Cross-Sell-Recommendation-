"""Rule-set versioning and the reproducibility manifest (PRD FR-10, US-003/004).

A rule set is identified by ``<data fingerprint>-<config fingerprint>``, so the
same dataset plus the same configuration always yields the same version string,
and any change to either produces a new one.
"""

from __future__ import annotations

import json
import platform
import sys
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

from crosssell import __version__
from crosssell.config import Config

TRACKED_PACKAGES = ("pandas", "numpy", "scipy", "mlxtend", "fastapi", "pydantic")


def package_versions() -> dict[str, str]:
    out: dict[str, str] = {"python": sys.version.split()[0], "crosssell": __version__}
    for name in TRACKED_PACKAGES:
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = "not installed"
    return out


def make_version(data_fingerprint: str, config: Config) -> str:
    """Deterministic rule-set version string."""
    if config.project.ruleset_version not in (None, "", "auto"):
        return str(config.project.ruleset_version)
    return f"rs-{data_fingerprint[:8]}-{config.fingerprint()[:8]}"


def build_manifest(
    *,
    ruleset_version: str,
    config: Config,
    dataset: dict[str, Any],
    data_summary: dict[str, Any],
    mining: dict[str, Any],
    evaluation: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble everything needed to reproduce and audit this rule set."""
    manifest: dict[str, Any] = {
        "ruleset_version": ruleset_version,
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "pipeline_version": __version__,
        "config_fingerprint": config.fingerprint(),
        "dataset": dataset,
        "data_summary": data_summary,
        "mining": mining,
        "evaluation": evaluation or {},
        "configuration": config.to_dict(),
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "packages": package_versions(),
        },
        "reproduce": {
            "command": "python -m crosssell.cli train --config config/config.yaml",
            "note": (
                "Same raw file (sha256 above) + same configuration => same "
                "ruleset_version and the same rule set."
            ),
        },
    }
    if extra:
        manifest.update(extra)
    return manifest


def write_manifest(path: str | Path, manifest: dict[str, Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    return path


def read_manifest(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
