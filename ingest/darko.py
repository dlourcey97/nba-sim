"""DARKO daily projections as a disagreement list. Never fed into the sim.

The about page says the leaderboard offers a CSV download. The same numbers
are in the public leaderboard page. One request per refresh. Credit: darko.app.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import pyarrow as pa
import pyarrow.parquet as pq
import requests

_URL = "https://www.darko.app/"
_UA = "nba-sim/1.0 (personal noncommercial NBA research)"
_KEYS = [
    "nba_id",
    "player_name",
    "team_name",
    "tm_id",
    "position",
    "age",
    "season",
    "rookie_season",
    "career_game_num",
    "dpm",
    "o_dpm",
    "d_dpm",
    "box_dpm",
    "on_off_dpm",
    "market_rating",
    "market_as_of",
    "x_minutes",
    "x_pace",
    "x_pts_100",
    "x_ast_100",
    "x_fg_pct",
    "x_fg3_pct",
    "x_ft_pct",
]


def expected_points(row: dict) -> float:
    """Box-score points from DARKO's per-100 forecast and expected minutes."""
    minutes = float(row.get("x_minutes") or 0.0)
    pace = float(row.get("x_pace") or 0.0)
    per_100 = float(row.get("x_pts_100") or 0.0)
    return per_100 / 100.0 * (minutes / 48.0) * pace


def parse_leaderboard_html(html: str) -> list[dict]:
    import json

    marker = html.find('players:{keys:')
    if marker < 0:
        raise ValueError("DARKO leaderboard payload was not in the page")
    decoder = json.JSONDecoder()
    keys_at = html.find("[", marker)
    keys, _end = decoder.raw_decode(html[keys_at:])
    values_at = html.find("values:", marker)
    blob = html[values_at + len("values:") :]
    blob = re.sub(r"(?<=\[|,)(-?)\.", r"\g<1>0.", blob)
    columns, _end = decoder.raw_decode(blob)
    index = {name: pos for pos, name in enumerate(keys)}
    count = len(columns[0]) if columns else 0
    parsed = []
    for row_index in range(count):
        item = {}
        for name in _KEYS:
            pos = index.get(name)
            if pos is None or pos >= len(columns):
                continue
            item[name] = columns[pos][row_index]
        if item.get("nba_id") is None:
            continue
        item["nba_id"] = int(item["nba_id"])
        item["expected_pts"] = expected_points(item)
        parsed.append(item)
    return parsed


def refresh_darko(settings, *, log=print) -> str:
    time_mod = __import__("time")
    time_mod.sleep(1.0)
    response = requests.get(_URL, headers={"User-Agent": _UA}, timeout=30)
    if response.status_code in {401, 403, 429}:
        log(f"darko stopped on HTTP {response.status_code}")
        return "stopped"
    response.raise_for_status()
    rows = parse_leaderboard_html(response.text)
    directory = settings.data_dir / "external" / "darko"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "leaderboard.parquet"
    if path.is_file():
        path.with_suffix(".prev.parquet").write_bytes(path.read_bytes())
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, path, compression="zstd")
    log(f"darko rows={len(rows)}")
    meta = directory / "darko_meta.parquet"
    pq.write_table(
        pa.table({"fetched_at": [datetime.now(timezone.utc).isoformat()], "rows": [len(rows)]}),
        meta,
        compression="zstd",
    )
    return "ok"


def write_disagreements(settings, summaries, *, log=print) -> None:
    """List the 10 largest point gaps versus our slate. Does not change the sim."""
    path = settings.data_dir / "external" / "darko" / "leaderboard.parquet"
    if not path.is_file() or not summaries:
        return
    darko = {int(row["nba_id"]): row for row in pq.read_table(path).to_pylist()}
    gaps = []
    for summary in summaries:
        for player in summary.players:
            other = darko.get(int(player.player_id))
            if other is None:
                continue
            ours = float(player.stats["pts"].mean)
            theirs = float(other["expected_pts"])
            gaps.append((abs(ours - theirs), player.player_name, ours, theirs))
    gaps.sort(reverse=True)
    lines = ["# DARKO disagreements", "", "Credit: darko.app. These numbers are not used in the sim.", ""]
    for gap, name, ours, theirs in gaps[:10]:
        lines.append(f"- {name}: sim {ours:.1f} pts, DARKO {theirs:.1f} pts, gap {gap:.1f}")
    out = settings.repo_root / "results" / "darko_disagreements.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"wrote {out}")
