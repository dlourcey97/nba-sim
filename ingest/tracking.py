"""NBA.com tracking stats via the stats API. Compact parquet only.

One request at a time. A 403 stops the batch. Credit: NBA.com.
Season S in a backtest reads season S-1 only. Sim flags stay off until a
decision run says otherwise.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pyarrow as pa
import pyarrow.parquet as pq
from nba_api.stats.endpoints import leaguedashptstats
from nba_api.stats.library.http import STATS_HEADERS

USER_AGENT = "nba-sim/1.0 (personal noncommercial NBA research)"
_MEASURES = ("PullUpShot", "CatchShoot", "Rebounding", "Passing")
_SEASONS = ("2023-24", "2024-25", "2025-26", "2026-27")
_SCHEMA = pa.schema(
    [
        ("season", pa.string()),
        ("player_id", pa.int64()),
        ("player_name", pa.string()),
        ("team_abbr", pa.string()),
        ("pullup_fga", pa.float64()),
        ("catch_fga", pa.float64()),
        ("reb_chances", pa.float64()),
        ("minutes", pa.float64()),
        ("potential_ast", pa.float64()),
    ]
)


class TrackingStopped(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    headers = dict(STATS_HEADERS)
    headers["User-Agent"] = USER_AGENT
    return headers


def _num(row: dict, *names: str) -> float:
    for name in names:
        if row.get(name) not in (None, ""):
            try:
                return float(row[name])
            except (TypeError, ValueError):
                continue
    return 0.0


def _fetch_measure(season: str, measure: str) -> list[dict]:
    time.sleep(1.5)
    endpoint = leaguedashptstats.LeagueDashPtStats(
        season=season,
        per_mode_simple="Totals",
        player_or_team="Player",
        pt_measure_type=measure,
        season_type_all_star="Regular Season",
        headers=_headers(),
        timeout=60,
        get_request=True,
    )
    frames = endpoint.get_data_frames()
    if not frames:
        return []
    return frames[0].to_dict(orient="records")


def refresh_tracking(settings, *, log=print) -> str:
    """Fetch prior tracking seasons. Returns 'ok', 'fresh', or 'stopped'."""
    directory = settings.data_dir / "external" / "tracking"
    path = directory / "player_tracking.parquet"
    meta = directory / "tracking_meta.parquet"
    if meta.is_file() and path.is_file():
        fetched = str(pq.read_table(meta).column("fetched_at")[0])
        if fetched[:10] == datetime.now(timezone.utc).date().isoformat():
            log("tracking fetch skipped (already fetched today)")
            return "fresh"
    merged: dict[tuple[str, int], dict] = {}
    if path.is_file():
        for row in pq.read_table(path).to_pylist():
            merged[(str(row["season"]), int(row["player_id"]))] = row
    try:
        for season in _SEASONS:
            frames = {measure: _fetch_measure(season, measure) for measure in _MEASURES}
            for measure, rows in frames.items():
                if rows:
                    log(f"tracking {season} {measure} cols={','.join(list(rows[0])[:8])} n={len(rows)}")
            ids = set()
            for rows in frames.values():
                for row in rows:
                    if row.get("PLAYER_ID") is not None:
                        ids.add(int(row["PLAYER_ID"]))
            for player_id in ids:
                bucket = {
                    "season": season,
                    "player_id": player_id,
                    "player_name": "",
                    "team_abbr": "",
                    "pullup_fga": 0.0,
                    "catch_fga": 0.0,
                    "reb_chances": 0.0,
                    "minutes": 0.0,
                    "potential_ast": 0.0,
                }
                for measure, rows in frames.items():
                    row = next((item for item in rows if int(item.get("PLAYER_ID") or -1) == player_id), None)
                    if row is None:
                        continue
                    bucket["player_name"] = str(row.get("PLAYER_NAME") or bucket["player_name"])
                    bucket["team_abbr"] = str(row.get("TEAM_ABBREVIATION") or bucket["team_abbr"])
                    if measure == "PullUpShot":
                        bucket["pullup_fga"] = _num(row, "PULL_UP_FGA", "FGA")
                    elif measure == "CatchShoot":
                        bucket["catch_fga"] = _num(row, "CATCH_SHOOT_FGA", "FGA")
                    elif measure == "Rebounding":
                        if row.get("REB_CHANCES") not in (None, ""):
                            bucket["reb_chances"] = _num(row, "REB_CHANCES")
                        else:
                            bucket["reb_chances"] = _num(row, "OREB_CHANCES") + _num(row, "DREB_CHANCES")
                        bucket["minutes"] = max(bucket["minutes"], _num(row, "MIN"))
                    elif measure == "Passing":
                        bucket["potential_ast"] = _num(row, "POTENTIAL_AST")
                        bucket["minutes"] = max(bucket["minutes"], _num(row, "MIN"))
                merged[(season, player_id)] = bucket
            log(f"tracking {season} players={len(ids)}")
    except Exception as exc:
        message = str(exc)
        if "403" in message or "401" in message or "429" in message:
            log(f"tracking stopped: {message}")
            _write(path, list(merged.values()))
            return "stopped"
        raise
    _write(path, list(merged.values()))
    pq.write_table(
        pa.table({"fetched_at": [datetime.now(timezone.utc).isoformat()], "rows": [len(merged)]}),
        meta,
        compression="zstd",
    )
    return "ok"


def _write(path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        path.with_suffix(".prev.parquet").write_bytes(path.read_bytes())
    table = pa.Table.from_pylist(rows, schema=_SCHEMA) if rows else pa.table(
        {field.name: pa.array([], type=field.type) for field in _SCHEMA}
    )
    pq.write_table(table, path, compression="zstd")
