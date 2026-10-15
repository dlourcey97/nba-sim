"""Write small display JSON files under results/latest/."""

from __future__ import annotations

import json
from pathlib import Path

from outputs.summarize import GameSummary, summary_to_json_dict


def results_dir(repo_root: Path) -> Path:
    return repo_root / "results" / "latest"


def write_game_json(repo_root: Path, summary: GameSummary) -> Path:
    """Overwrite one game JSON. Directory is created if needed."""
    directory = results_dir(repo_root)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{summary.away_abbr}-{summary.home_abbr}_{summary.game_id}.json"
    payload = summary_to_json_dict(summary)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return path


def clear_latest(repo_root: Path) -> int:
    """Delete existing JSON files in results/latest/. Returns count removed."""
    directory = results_dir(repo_root)
    if not directory.is_dir():
        return 0
    removed = 0
    for path in directory.glob("*.json"):
        path.unlink()
        removed += 1
    return removed
