"""Archive Dunks & Threes exports under DATA_DIR/external/dunks.

EPM files already carry nba_id. A minutes file may carry a name instead, and
that name is matched to the current roster. daily.py reads the inbox. A file
whose ratings already match the stored day is not written again. Raw CSVs
stay where the user put them; they are not copied into the repository.
"""

from __future__ import annotations

import csv
import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from nba_sim.settings import Settings

_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")
_EPM_FLOATS = (
    "p_mpg",
    "p_usg",
    "oepm",
    "depm",
    "epm",
    "p_pts_100",
    "p_tspct",
    "p_fg2a_100",
    "p_fg2pct",
    "p_fg3a_100",
    "p_fg3pct",
    "p_fta_100",
    "p_ftpct",
    "p_orb_100",
    "p_drb_100",
    "p_ast_100",
    "p_tov_100",
    "p_stl_100",
    "p_blk_100",
)
_BOX_FLOATS = (
    "minutes",
    "pts",
    "reb",
    "ast",
    "stl",
    "blk",
    "tov",
    "oreb",
    "dreb",
    "fg3a",
)


@dataclass
class LoadReport:
    source: str
    kind: str
    as_of: str
    rows: int
    status: str
    unmatched: list[str] = field(default_factory=list)

    def line(self) -> str:
        extra = f" unmatched={len(self.unmatched)}" if self.unmatched else ""
        return (
            f"{self.kind} {self.as_of} {self.status} rows={self.rows} "
            f"source={self.source}{extra}"
        )


def archive_dir(settings: Settings) -> Path:
    return Path(settings.data_dir) / "external" / "dunks"


def inbox_dir(settings: Settings) -> Path:
    return archive_dir(settings) / "inbox"


def normalize_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    text = text.lower().replace("'", "").replace(".", "")
    text = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", text)
    return re.sub(r"\s+", " ", text).strip()


def ingest_inbox(settings: Settings, slate_date: date) -> str:
    """Load CSVs dropped in the inbox for this slate. Missing inbox is empty."""
    inbox = inbox_dir(settings)
    inbox.mkdir(parents=True, exist_ok=True)
    paths = sorted(path for path in inbox.glob("*.csv") if path.is_file())
    if not paths:
        return "dunks inbox empty"
    names = roster_names(settings)
    reports = [
        load_csv(path, archive_dir(settings), as_of=_stamp(path, slate_date), names=names)
        for path in paths
    ]
    write_manifest(archive_dir(settings))
    return "dunks " + "; ".join(report.line() for report in reports)


def load_csv(
    path: Path,
    dest_dir: Path,
    *,
    as_of: date,
    names: dict[tuple[str, str], int] | None = None,
) -> LoadReport:
    """Write one EPM, minutes, or team-rating CSV into the dated archive."""
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        raw = list(reader)
    dest_dir.mkdir(parents=True, exist_ok=True)
    archived_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if {"nba_id", "oepm", "p_mpg"} <= columns:
        return _load_epm(path, raw, dest_dir, as_of, archived_at, names or {})
    if {"team_alias", "ortg", "drtg"} <= columns:
        return _load_teams(path, raw, dest_dir, as_of, archived_at)
    if "minutes" in columns and ({"player_id", "name", "player"} & columns):
        return _load_box(path, raw, dest_dir, as_of, archived_at, names or {})
    return LoadReport(path.name, "unknown", as_of.isoformat(), len(raw), "skipped")


def roster_names(settings: Settings) -> dict[tuple[str, str], int]:
    from nba_sim.storage import read_rows

    rows = read_rows(settings, "current_rosters", settings.current_season)
    index: dict[tuple[str, str], int] = {}
    for row in rows:
        index[(normalize_name(str(row["player_name"])), str(row["team_abbr"]))] = int(
            row["player_id"]
        )
    return index


def roster_gaps(settings: Settings, as_of: date) -> list[str]:
    """EPM names whose nba_id is not on the current roster. They still archive."""
    from nba_sim.storage import read_rows

    path = _latest(archive_dir(settings), "epm_", as_of)
    if path is None:
        return []
    roster = {
        int(row["player_id"])
        for row in read_rows(settings, "current_rosters", settings.current_season)
    }
    missing = []
    for row in pq.read_table(path).to_pylist():
        if int(row["nba_id"]) not in roster:
            missing.append(f"{row['name']} ({row['team']})")
    return sorted(missing)


def write_manifest(dest_dir: Path) -> Path:
    """One row per stored snapshot: kind, date, archive time, rows."""
    rows = []
    for path in sorted(dest_dir.glob("*.parquet")):
        if path.name == "manifest.parquet":
            continue
        match = _DATE.search(path.name)
        if match is None:
            continue
        kind = path.name.split("_", 1)[0]
        table = pq.read_table(path)
        archived = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        rows.append(
            {
                "kind": kind,
                "as_of": match.group(1),
                "archived_at": archived.isoformat(timespec="seconds"),
                "rows": table.num_rows,
                "file": path.name,
            }
        )
    out = dest_dir / "manifest.parquet"
    pq.write_table(pa.Table.from_pylist(rows), out)
    return out


def _load_epm(path, raw, dest_dir, as_of, archived_at, names) -> LoadReport:
    unmatched: list[str] = []
    rows = []
    for row in raw:
        player_id = _player_id(row, names, unmatched)
        if player_id is None:
            continue
        stored = {
            "season": int(float(row["season"])) if row.get("season") else 0,
            "nba_id": player_id,
            "name": row.get("name") or row.get("player") or "",
            "team": row["team"],
            "as_of": as_of.isoformat(),
            "archived_at": archived_at,
        }
        for key in _EPM_FLOATS:
            stored[key] = float(row[key])
        rows.append(stored)
    dest = dest_dir / f"epm_{as_of.isoformat()}.parquet"
    status = _write_if_new(dest, rows, _epm_signature)
    return LoadReport(path.name, "epm", as_of.isoformat(), len(rows), status, unmatched)


def _load_box(path, raw, dest_dir, as_of, archived_at, names) -> LoadReport:
    unmatched: list[str] = []
    rows = []
    for row in raw:
        player_id = _player_id(row, names, unmatched)
        if player_id is None:
            continue
        team = row.get("team_abbr") or row.get("team") or ""
        stored = {
            "player_id": player_id,
            "team_abbr": team,
            "as_of": as_of.isoformat(),
            "archived_at": archived_at,
        }
        for key in _BOX_FLOATS:
            stored[key] = float(row[key])
        rows.append(stored)
    dest = dest_dir / f"box_{as_of.isoformat()}.parquet"
    status = _write_if_new(dest, rows, _box_signature)
    return LoadReport(path.name, "minutes", as_of.isoformat(), len(rows), status, unmatched)


def _load_teams(path, raw, dest_dir, as_of, archived_at) -> LoadReport:
    stamped = as_of
    if raw and raw[0].get("date"):
        stamped = date.fromisoformat(str(raw[0]["date"])[:10])
    rows = [
        {
            "team_abbr": row["team_alias"],
            "ortg": float(row["ortg"]),
            "drtg": float(row["drtg"]),
            "as_of": stamped.isoformat(),
            "archived_at": archived_at,
        }
        for row in raw
    ]
    dest = dest_dir / f"team_ratings_{stamped.isoformat()}.parquet"
    status = _write_if_new(dest, rows, _team_signature)
    return LoadReport(path.name, "team_ratings", stamped.isoformat(), len(rows), status)


def _player_id(row: dict, names: dict[tuple[str, str], int], unmatched: list[str]) -> int | None:
    raw_id = str(row.get("nba_id") or row.get("player_id") or "").strip()
    if raw_id:
        return int(float(raw_id))
    name = row.get("name") or row.get("player") or ""
    team = row.get("team") or row.get("team_abbr") or ""
    found = names.get((normalize_name(name), team))
    if found is None:
        unmatched.append(f"{name} ({team})")
        return None
    return found


def _write_if_new(dest: Path, rows: list[dict], signature) -> str:
    if dest.is_file() and signature(pq.read_table(dest).to_pylist()) == signature(rows):
        return "already"
    pq.write_table(pa.Table.from_pylist(rows), dest)
    return "wrote"


def _epm_signature(rows: list[dict]) -> str:
    bits = [
        f"{int(row['nba_id'])}:{float(row['epm']):.3f}:{row['team']}" for row in rows
    ]
    return hashlib.sha1("\n".join(sorted(bits)).encode()).hexdigest()


def _box_signature(rows: list[dict]) -> str:
    bits = [
        f"{int(row['player_id'])}:{float(row['minutes']):.2f}:{row['team_abbr']}"
        for row in rows
    ]
    return hashlib.sha1("\n".join(sorted(bits)).encode()).hexdigest()


def _team_signature(rows: list[dict]) -> str:
    bits = [
        f"{row['team_abbr']}:{float(row['ortg']):.3f}:{float(row['drtg']):.3f}"
        for row in rows
    ]
    return hashlib.sha1("\n".join(sorted(bits)).encode()).hexdigest()


def _stamp(path: Path, slate_date: date) -> date:
    match = _DATE.search(path.name)
    if match is None:
        return slate_date
    return date.fromisoformat(match.group(1))


def _latest(directory: Path, prefix: str, as_of: date) -> Path | None:
    best: tuple[date, Path] | None = None
    if not directory.is_dir():
        return None
    for path in directory.glob(f"{prefix}*.parquet"):
        match = _DATE.search(path.name)
        if match is None or path.name == "manifest.parquet":
            continue
        stamped = date.fromisoformat(match.group(1))
        if stamped <= as_of and (best is None or stamped > best[0]):
            best = (stamped, path)
    return None if best is None else best[1]
