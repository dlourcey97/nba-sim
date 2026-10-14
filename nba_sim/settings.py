"""Load .env and config.yaml."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from nba_sim.errors import ConfigError, PathInsideRepoError
from nba_sim.schema import SEASON_PATTERN

_SEASON = re.compile(SEASON_PATTERN)


@dataclass(frozen=True)
class Settings:
    repo_root: Path
    data_dir: Path
    archive_dir: Path | None
    max_bytes: int
    current_season: str
    config: dict[str, Any]


def repo_root_from_here() -> Path:
    return Path(__file__).resolve().parents[1]


def assert_outside_repo(path: Path, repo_root: Path) -> Path:
    """Reject a data path that contains the repo or sits inside it."""
    if not path.is_absolute():
        raise ConfigError(f"{path} must be an absolute path outside the repository.")
    resolved = path.resolve()
    root = repo_root.resolve()
    if resolved == root or root in resolved.parents or resolved in root.parents:
        raise PathInsideRepoError(resolved, root)
    return resolved


def load_settings(repo_root: Path | None = None) -> Settings:
    root = (repo_root or repo_root_from_here()).resolve()
    env_path = root / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)
    data_raw = os.environ.get("DATA_DIR", "").strip()
    if not data_raw:
        raise ConfigError("DATA_DIR is not set. Add it to .env, outside the repository.")
    archive_raw = os.environ.get("ARCHIVE_DIR", "").strip()
    data_dir = assert_outside_repo(Path(data_raw), root)
    archive_dir = assert_outside_repo(Path(archive_raw), root) if archive_raw else None
    if archive_dir is not None and archive_dir == data_dir:
        raise ConfigError("ARCHIVE_DIR must be different from DATA_DIR.")
    config_path = root / "config.yaml"
    if not config_path.is_file():
        raise ConfigError(f"missing {config_path}")
    with config_path.open(encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ConfigError("config.yaml must be a mapping.")
    _validate_config(loaded)
    return Settings(
        repo_root=root,
        data_dir=data_dir,
        archive_dir=archive_dir,
        max_bytes=int(loaded["storage"]["max_bytes"]),
        current_season=str(loaded["season"]["current"]),
        config=loaded,
    )


def _require(config: dict[str, Any], *path: str) -> Any:
    node: Any = config
    walked: list[str] = []
    for part in path:
        walked.append(part)
        if not isinstance(node, dict) or part not in node:
            raise ConfigError("config.yaml missing " + ".".join(walked))
        node = node[part]
    return node


def _validate_config(config: dict[str, Any]) -> None:
    max_bytes = _require(config, "storage", "max_bytes")
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes <= 0:
        raise ConfigError("storage.max_bytes must be a positive integer.")
    current = _require(config, "season", "current")
    if not isinstance(current, str) or _SEASON.fullmatch(current) is None:
        raise ConfigError("season.current must look like 2025-26.")
    runs = _require(config, "simulation", "runs")
    if not isinstance(runs, int) or isinstance(runs, bool) or runs <= 0:
        raise ConfigError("simulation.runs must be a positive integer.")
    seed = _require(config, "simulation", "seed")
    if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool)):
        raise ConfigError("simulation.seed must be an integer or null.")
    seasons_back = _require(config, "blending", "season_weights", "seasons_back")
    weights = _require(config, "blending", "season_weights", "weights")
    if not isinstance(seasons_back, list) or not isinstance(weights, list):
        raise ConfigError("blending.season_weights seasons_back and weights must be lists.")
    if len(seasons_back) != len(weights) or not weights:
        raise ConfigError("blending.season_weights seasons_back and weights must be the same non-empty length.")
    if any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in weights):
        raise ConfigError("blending.season_weights.weights must be numbers.")
    if abs(sum(float(value) for value in weights) - 1.0) > 1e-6:
        raise ConfigError("blending.season_weights.weights must sum to 1.")
    for key in ("form_decay", "regression_strength"):
        value = _require(config, "blending", key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            raise ConfigError(f"blending.{key} must be a non-negative number.")
    for key in ("max_retries",):
        value = _require(config, "http", key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ConfigError(f"http.{key} must be a non-negative integer.")
    for key in ("backoff_seconds", "delay_seconds", "timeout_seconds"):
        value = _require(config, "http", key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            raise ConfigError(f"http.{key} must be a non-negative number.")
    percentiles = _require(config, "outputs", "percentiles")
    if list(percentiles) != [10, 25, 50, 75, 90]:
        raise ConfigError("outputs.percentiles must be [10, 25, 50, 75, 90].")
    minimum = _require(config, "minutes", "min_minutes")
    maximum = _require(config, "minutes", "max_minutes")
    if float(minimum) >= float(maximum):
        raise ConfigError("minutes.min_minutes must be below minutes.max_minutes.")
    _require(config, "context", "rest_day_factors")
    _require(config, "context", "opponent_defense_weight")
    _require(config, "context", "teammate_absence_usage_share")
    _require(config, "archive", "save_play_by_play")
