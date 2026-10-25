"""Fetch published RAPM datasets from nbarapm.com into DATA_DIR/external/.

The timedecay and six-factor pages expose a "Download CSV" button that builds a
CSV in the browser from a published JSON file under ``/load/...``. This module
downloads those JSON data files only (never scrapes HTML), at most once every
``nbarapm_fetch_interval_days`` (default 7). Credit: https://nbarapm.com

Layout under ``{DATA_DIR}/external/``:

- ``nbarapm_timedecay.parquet`` / ``nbarapm_timedecay.prev.parquet``
- ``nbarapm_six_factor.parquet`` / ``nbarapm_six_factor.prev.parquet``
- ``nbarapm_meta.parquet`` — last fetch timestamps + site ``as_of`` dates

On fetch/format failure we keep the last good copy, log a warning, and never
raise into ``daily.py``.
"""

from __future__ import annotations

import json
import shutil
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pyarrow as pa
import pyarrow.parquet as pq

from nba_sim.settings import Settings

LogFn = Callable[[str], None]

# Published data files the dataset pages load (same payload the CSV button uses).
NBARAPM_DATASETS: dict[str, dict[str, str]] = {
    "timedecay": {
        "url": "https://nbarapm.com/load/timedecay",
        "stem": "nbarapm_timedecay",
    },
    "six_factor": {
        # Six-factor page loads SCALEDOUTPUT_SMALLER (same body as /load/six_factor).
        "url": "https://nbarapm.com/load/SCALEDOUTPUT_SMALLER",
        "stem": "nbarapm_six_factor",
    },
}

USER_AGENT = (
    "nba-sim/1.0 (+https://github.com/local/nba-sim; research RAPM ingest; "
    "contact: local nightly pipeline)"
)
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_INTERVAL_DAYS = 7


@dataclass(frozen=True)
class RapmFetchStatus:
    """Summary of one weekly refresh attempt."""

    fetched: bool
    skipped_fresh: bool
    dataset_ages: dict[str, str]
    warnings: tuple[str, ...]


def external_dir(settings: Settings) -> Path:
    path = settings.data_dir / "external"
    path.mkdir(parents=True, exist_ok=True)
    return path


def meta_path(settings: Settings) -> Path:
    return external_dir(settings) / "nbarapm_meta.parquet"


def dataset_paths(settings: Settings, stem: str) -> tuple[Path, Path]:
    root = external_dir(settings)
    return root / f"{stem}.parquet", root / f"{stem}.prev.parquet"


def refresh_nbarapm_rapm(
    settings: Settings,
    *,
    log: LogFn = print,
    force: bool = False,
) -> RapmFetchStatus:
    """Weekly check: download nbarapm datasets when stale; never raise."""
    ctx = settings.config.get("context") or {}
    if not bool(ctx.get("nbarapm_enabled", True)):
        log("nbarapm RAPM fetch disabled (context.nbarapm_enabled=false)")
        return RapmFetchStatus(
            fetched=False,
            skipped_fresh=False,
            dataset_ages=_age_report(settings),
            warnings=(),
        )

    interval = int(ctx.get("nbarapm_fetch_interval_days", DEFAULT_INTERVAL_DAYS))
    timeout = float(
        (settings.config.get("http") or {}).get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
    )
    warnings: list[str] = []
    meta = _read_meta(settings)
    now = datetime.now(timezone.utc)

    if not force and _meta_is_fresh(meta, now=now, interval_days=interval):
        ages = _age_report(settings, meta=meta, now=now)
        for name, age in ages.items():
            log(f"nbarapm {name}: {age} (skip fetch; within {interval}d)")
        return RapmFetchStatus(
            fetched=False,
            skipped_fresh=True,
            dataset_ages=ages,
            warnings=(),
        )

    any_ok = False
    for key, spec in NBARAPM_DATASETS.items():
        try:
            payload = _download_json(
                spec["url"],
                timeout_seconds=timeout,
                log=log,
            )
            table, source_updated = _parse_dataset(key, payload, fetched_at=now)
            _atomic_replace_parquet(settings, spec["stem"], table)
            meta[key] = {
                "dataset": key,
                "url": spec["url"],
                "fetched_at": now.isoformat(),
                "source_updated": source_updated,
                "row_count": table.num_rows,
                "status": "ok",
            }
            any_ok = True
            log(
                f"nbarapm {key}: wrote {table.num_rows} rows "
                f"(source_updated={source_updated or 'unknown'})"
            )
        except Exception as exc:  # noqa: BLE001 — daily must not break
            msg = f"nbarapm {key} fetch failed: {exc}; keeping last good copy"
            warnings.append(msg)
            log(f"WARNING: {msg}")
            prev = meta.get(key) or {}
            meta[key] = {
                "dataset": key,
                "url": spec["url"],
                "fetched_at": str(prev.get("fetched_at") or ""),
                "source_updated": str(prev.get("source_updated") or ""),
                "row_count": int(prev.get("row_count") or 0),
                "status": "failed",
                "last_error": str(exc)[:240],
                "failed_at": now.isoformat(),
            }

    if any_ok or meta:
        # Always stamp a check time so a total failure still waits 7 days.
        meta["_check"] = {
            "dataset": "_check",
            "url": "",
            "fetched_at": now.isoformat(),
            "source_updated": "",
            "row_count": 0,
            "status": "ok" if any_ok else "failed",
        }
        _write_meta(settings, meta)

    ages = _age_report(settings, meta=meta, now=now)
    for name, age in ages.items():
        log(f"nbarapm {name}: {age}")
    return RapmFetchStatus(
        fetched=any_ok,
        skipped_fresh=False,
        dataset_ages=ages,
        warnings=tuple(warnings),
    )


def load_timedecay_ratings(settings: Settings) -> dict[int, float]:
    """player_id -> net RAPM (pts/100) from the latest good timedecay parquet."""
    table = _read_dataset_table(settings, "nbarapm_timedecay", columns=["player_id", "rapm"])
    if table is None:
        return {}
    return _ratings_from_columns(table.column("player_id"), table.column("rapm"))


def load_six_factor_ratings(
    settings: Settings,
    *,
    max_latest_year: int,
    intervals: tuple[str, ...] = ("3Y", "5Y"),
) -> dict[int, float]:
    """player_id -> net RAPM from six-factor rows with ``latest_year <= max_latest_year``.

    Six-factor parquet grain is one row per (player_id, latest_year, year_interval).
    ``latest_year`` is the end-year of the rating window (e.g. 2025 = through the
    2024-25 season). Intervals present: ``3Y``, ``5Y``, and ``TD`` (TD only on the
    newest vintage, currently 2026 — same snapshot as timedecay).

    Preference order among ``intervals``: first match wins (default 3Y then 5Y).
    Never use a vintage whose ``latest_year`` exceeds ``max_latest_year`` (leakage).
    """
    table = _read_dataset_table(
        settings,
        "nbarapm_six_factor",
        columns=["player_id", "latest_year", "year_interval", "rapm"],
    )
    if table is None:
        return {}
    # Prefer earlier intervals in the tuple; within an interval take max year <= cap.
    best: dict[int, tuple[int, int, float]] = {}
    # rank: lower interval index is better; higher latest_year is better
    interval_rank = {name: i for i, name in enumerate(intervals)}
    pids = table.column("player_id").to_pylist()
    years = table.column("latest_year").to_pylist()
    ivals = table.column("year_interval").to_pylist()
    rapms = table.column("rapm").to_pylist()
    for pid, year, interval, rapm in zip(pids, years, ivals, rapms):
        if pid is None or year is None or rapm is None:
            continue
        try:
            player_id = int(pid)
            latest_year = int(year)
            value = float(rapm)
        except (TypeError, ValueError):
            continue
        if latest_year > int(max_latest_year):
            continue
        iv = str(interval or "")
        if iv not in interval_rank:
            continue
        key = (interval_rank[iv], -latest_year)
        prev = best.get(player_id)
        if prev is None or key < (prev[0], prev[1]):
            best[player_id] = (interval_rank[iv], -latest_year, value)
    return {pid: trip[2] for pid, trip in best.items()}


def timedecay_safe_for_season(settings: Settings, season: str) -> bool:
    """True when the timedecay snapshot cannot include games from ``season``.

    Approx season start = Oct 1 of the label's first year (e.g. 2025-26 → 2025-10-01).
    Safe iff that date is strictly after the snapshot ``as_of_date`` (offseason cut).
    """
    updated = load_timedecay_source_updated(settings)
    if updated is None:
        return False
    try:
        start_year = int(str(season).split("-", 1)[0])
    except ValueError:
        return False
    season_start = date(start_year, 10, 1)
    return season_start > updated


def prior_season_end_year(season: str) -> int:
    """Calendar end-year of the season before ``season`` (2025-26 → 2025)."""
    return int(str(season).split("-", 1)[0])


def load_timedecay_source_updated(settings: Settings) -> date | None:
    """Site ``as_of_date`` recorded on the timedecay parquet, if present."""
    table = _read_dataset_table(
        settings, "nbarapm_timedecay", columns=["source_updated"]
    )
    if table is None:
        return None
    values = [v for v in table.column("source_updated").to_pylist() if v]
    if not values:
        return None
    raw = str(values[0])[:10]
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _read_dataset_table(
    settings: Settings,
    stem: str,
    *,
    columns: list[str] | None = None,
) -> Any | None:
    current, prev = dataset_paths(settings, stem)
    for path in (current, prev):
        if not path.is_file():
            continue
        try:
            return pq.read_table(path, columns=columns)
        except Exception:
            continue
    return None


def _ratings_from_columns(pid_col: Any, rapm_col: Any) -> dict[int, float]:
    out: dict[int, float] = {}
    for pid, rapm in zip(pid_col.to_pylist(), rapm_col.to_pylist()):
        if pid is None or rapm is None:
            continue
        try:
            out[int(pid)] = float(rapm)
        except (TypeError, ValueError):
            continue
    return out


def format_rapm_age_line(settings: Settings, *, now: datetime | None = None) -> str:
    """One-line age summary for daily.py logs."""
    ages = _age_report(settings, now=now or datetime.now(timezone.utc))
    if not ages:
        return "nbarapm RAPM: no local copy yet"
    parts = [f"{name} {age}" for name, age in ages.items()]
    return "nbarapm RAPM age: " + "; ".join(parts)


def _download_json(
    url: str,
    *,
    timeout_seconds: float,
    log: LogFn,
) -> Any:
    """GET published JSON with one retry. No other requests to the site."""
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                raw = resp.read()
            return json.loads(raw)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            last_exc = exc
            if attempt == 0:
                log(f"nbarapm download retry after error: {exc}")
                time.sleep(1.0)
    assert last_exc is not None
    raise last_exc


def _parse_dataset(
    key: str,
    payload: Any,
    *,
    fetched_at: datetime,
) -> tuple[pa.Table, str]:
    if key == "timedecay":
        return _parse_timedecay(payload, fetched_at=fetched_at)
    if key == "six_factor":
        return _parse_six_factor(payload, fetched_at=fetched_at)
    raise ValueError(f"unknown nbarapm dataset {key!r}")


def _parse_timedecay(payload: Any, *, fetched_at: datetime) -> tuple[pa.Table, str]:
    if not isinstance(payload, list) or not payload:
        raise ValueError("timedecay payload must be a non-empty JSON list")
    required = {"nba_id", "RAPM"}
    sample = payload[0]
    if not isinstance(sample, dict) or not required.issubset(sample):
        raise ValueError(
            f"timedecay format changed; expected keys {sorted(required)}, "
            f"got {sorted(sample)[:20] if isinstance(sample, dict) else type(sample)}"
        )
    rows: list[dict[str, Any]] = []
    source_updated = ""
    for item in payload:
        if not isinstance(item, dict):
            continue
        pid = _int_or_none(item.get("nba_id"))
        rapm = _float_or_none(item.get("RAPM") if item.get("RAPM") is not None else item.get("OVR_RAPM"))
        if pid is None or rapm is None:
            continue
        as_of = str(item.get("as_of_date") or "")[:10]
        if as_of and not source_updated:
            source_updated = as_of
        rows.append(
            {
                "player_id": pid,
                "player_name": str(item.get("player_name") or ""),
                "team_abbr": str(
                    item.get("team_abbreviation")
                    or item.get("Team")
                    or item.get("team")
                    or ""
                ),
                "year": _int_or_none(item.get("year") or item.get("Latest_Year")),
                "year_interval": str(item.get("Year_Interval") or "TD"),
                "rapm": rapm,
                "orapm": _float_or_none(item.get("ORAPM") or item.get("Off_RAPM")),
                "drapm": _float_or_none(item.get("DRAPM") or item.get("Def_RAPM")),
                "off_poss": _int_or_none(item.get("Off_Poss")),
                "minutes": _float_or_none(item.get("MP2")),
                "half_life_days": _float_or_none(item.get("half_life_days")),
                "source_updated": as_of or source_updated,
                "fetched_at": fetched_at.isoformat(),
                "source": "nbarapm.com/load/timedecay",
            }
        )
    if not rows:
        raise ValueError("timedecay parsed zero player rows")
    if not source_updated:
        source_updated = str(rows[0].get("source_updated") or "")
    return pa.Table.from_pylist(rows), source_updated


def _parse_six_factor(payload: Any, *, fetched_at: datetime) -> tuple[pa.Table, str]:
    if not isinstance(payload, list) or not payload:
        raise ValueError("six_factor payload must be a non-empty JSON list")
    required = {"nba_id", "OVR_RAPM", "Year_Interval", "Latest_Year"}
    sample = payload[0]
    if not isinstance(sample, dict) or not required.issubset(sample):
        raise ValueError(
            f"six_factor format changed; expected keys {sorted(required)}, "
            f"got {sorted(sample)[:20] if isinstance(sample, dict) else type(sample)}"
        )
    rows: list[dict[str, Any]] = []
    max_year = 0
    keep_intervals = {"TD", "3Y", "5Y"}
    for item in payload:
        if not isinstance(item, dict):
            continue
        interval = str(item.get("Year_Interval") or "")
        if interval not in keep_intervals:
            continue
        pid = _int_or_none(item.get("nba_id"))
        # Skip placeholder IDs like historical "1"
        if pid is None or pid < 100:
            continue
        rapm = _float_or_none(item.get("OVR_RAPM"))
        year = _int_or_none(item.get("Latest_Year"))
        if rapm is None or year is None:
            continue
        max_year = max(max_year, year)
        rows.append(
            {
                "player_id": pid,
                "player_name": str(item.get("player_name") or ""),
                "latest_year": year,
                "year_interval": interval,
                "rapm": rapm,
                "orapm": _float_or_none(item.get("Off_RAPM")),
                "drapm": _float_or_none(item.get("Def_RAPM")),
                "off_poss": _int_or_none(item.get("Off_Poss")),
                "sc_off_ts": _float_or_none(item.get("sc_OFF_TS")),
                "sc_off_tov": _float_or_none(item.get("sc_OFF_TOV")),
                "sc_off_reb": _float_or_none(item.get("sc_OFF_REB")),
                "sc_def_ts": _float_or_none(item.get("sc_DEF_TS")),
                "sc_def_tov": _float_or_none(item.get("sc_DEF_TOV")),
                "sc_def_reb": _float_or_none(item.get("sc_DEF_REB")),
                "sc_poss": _float_or_none(item.get("sc_POSS")),
                "source_updated": f"{year}-01-01" if year else "",
                "fetched_at": fetched_at.isoformat(),
                "source": "nbarapm.com/load/SCALEDOUTPUT_SMALLER",
            }
        )
    if not rows:
        raise ValueError("six_factor parsed zero player rows")
    source_updated = f"{max_year}-01-01" if max_year else ""
    return pa.Table.from_pylist(rows), source_updated


def _atomic_replace_parquet(settings: Settings, stem: str, table: pa.Table) -> None:
    current, prev = dataset_paths(settings, stem)
    tmp = current.with_suffix(".parquet.tmp")
    pq.write_table(table, tmp, compression="zstd")
    if current.is_file():
        shutil.copy2(current, prev)
    tmp.replace(current)


def _read_meta(settings: Settings) -> dict[str, dict[str, Any]]:
    path = meta_path(settings)
    if not path.is_file():
        return {}
    try:
        table = pq.read_table(path)
    except Exception:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in table.to_pylist():
        key = str(row.get("dataset") or "")
        if key:
            out[key] = row
    return out


def _write_meta(settings: Settings, meta: dict[str, dict[str, Any]]) -> None:
    rows = []
    for key, row in meta.items():
        rows.append(
            {
                "dataset": key,
                "url": str(row.get("url") or ""),
                "fetched_at": str(row.get("fetched_at") or ""),
                "source_updated": str(row.get("source_updated") or ""),
                "row_count": int(row.get("row_count") or 0),
                "status": str(row.get("status") or ""),
                "last_error": str(row.get("last_error") or ""),
                "failed_at": str(row.get("failed_at") or ""),
            }
        )
    if not rows:
        return
    path = meta_path(settings)
    tmp = path.with_suffix(".parquet.tmp")
    pq.write_table(pa.Table.from_pylist(rows), tmp, compression="zstd")
    tmp.replace(path)


def _meta_is_fresh(
    meta: dict[str, dict[str, Any]],
    *,
    now: datetime,
    interval_days: int,
) -> bool:
    if interval_days <= 0:
        return False
    check = meta.get("_check") or meta.get("timedecay") or {}
    raw = str(check.get("fetched_at") or "")
    if not raw:
        return False
    try:
        fetched = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return False
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    age_days = (now - fetched).total_seconds() / 86400.0
    return age_days < float(interval_days)


def _age_report(
    settings: Settings,
    *,
    meta: dict[str, dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> dict[str, str]:
    now = now or datetime.now(timezone.utc)
    meta = meta if meta is not None else _read_meta(settings)
    out: dict[str, str] = {}
    for key, spec in NBARAPM_DATASETS.items():
        current, prev = dataset_paths(settings, spec["stem"])
        path = current if current.is_file() else prev if prev.is_file() else None
        if path is None:
            out[key] = "missing"
            continue
        source_updated = str((meta.get(key) or {}).get("source_updated") or "")
        if not source_updated:
            source_updated = _source_updated_from_parquet(path)
        if source_updated:
            try:
                updated = date.fromisoformat(source_updated[:10])
                days = (now.date() - updated).days
                out[key] = f"source_updated={source_updated[:10]} ({days}d old)"
                continue
            except ValueError:
                pass
        fetched = str((meta.get(key) or {}).get("fetched_at") or "")
        if fetched:
            out[key] = f"fetched_at={fetched[:19]}Z"
        else:
            out[key] = f"local file {path.name}"
    return out


def _source_updated_from_parquet(path: Path) -> str:
    try:
        table = pq.read_table(path, columns=["source_updated"])
    except Exception:
        return ""
    values = [str(v) for v in table.column("source_updated").to_pylist() if v]
    return values[0][:10] if values else ""


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
