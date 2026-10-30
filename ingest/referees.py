"""Referee crews and game environment for foul and pace adjustments.

Live crews come from the public NBA officials assignments page, at most once
per day. History comes from stats.nba.com box score summaries (one game at a
time). Compact parquet only — HTML and JSON stay in memory. A failed fetch
keeps the last good file and does not raise into daily.py.

Credit: NBA.com official assignments and stats.nba.com box scores.
"""

from __future__ import annotations

import re
import shutil
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable

import pyarrow as pa
import pyarrow.parquet as pq
import requests
from nba_api.stats.library.http import STATS_HEADERS

from nba_sim.settings import Settings
from nba_sim.storage import data_file, read_rows

LogFn = Callable[[str], None]
SleepFn = Callable[[float], None]

USER_AGENT = "nba-sim/1.0 (personal noncommercial NBA research)"
ASSIGNMENTS_URL = "https://official.nba.com/referee-assignments/"
STATS_BASE = "https://stats.nba.com/stats"
BLOCKED_STATUS = frozenset({401, 403, 429})
CREW_ROLES = ("crew_chief", "referee", "umpire")
HISTORY_START_YEAR = 2023

_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
_DATE_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+(\d{1,2}),\s+(\d{4})\b",
    re.I,
)
_OFFICIAL_RE = re.compile(r"^(?P<name>.*?)\s*\(#(?P<num>\d+)\)\s*$")
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

# City or nickname as printed on the assignments page → abbreviation.
_CITY_ABBR: dict[str, str] = {
    "atlanta": "ATL",
    "boston": "BOS",
    "brooklyn": "BKN",
    "charlotte": "CHA",
    "chicago": "CHI",
    "cleveland": "CLE",
    "dallas": "DAL",
    "denver": "DEN",
    "detroit": "DET",
    "golden state": "GSW",
    "houston": "HOU",
    "indiana": "IND",
    "la clippers": "LAC",
    "los angeles clippers": "LAC",
    "clippers": "LAC",
    "la lakers": "LAL",
    "los angeles lakers": "LAL",
    "lakers": "LAL",
    "memphis": "MEM",
    "miami": "MIA",
    "milwaukee": "MIL",
    "minnesota": "MIN",
    "new orleans": "NOP",
    "new york": "NYK",
    "oklahoma city": "OKC",
    "orlando": "ORL",
    "philadelphia": "PHI",
    "phoenix": "PHX",
    "portland": "POR",
    "sacramento": "SAC",
    "san antonio": "SAS",
    "toronto": "TOR",
    "utah": "UTA",
    "washington": "WAS",
}


class RefereeAccessBlocked(Exception):
    """The host refused automated access. Do not retry."""

    def __init__(self, status: int, url: str) -> None:
        super().__init__(f"HTTP {status} from {url}")
        self.status = status
        self.url = url


@dataclass(frozen=True)
class RefereeRefreshStatus:
    fetched_live: bool
    officials_written: int
    stopped_status: int | None
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class AssignmentGame:
    game_date: date
    away_abbr: str
    home_abbr: str
    crew_chief: str
    referee: str
    umpire: str
    crew_chief_jersey: str
    referee_jersey: str
    umpire_jersey: str


def external_dir(settings: Settings):
    path = settings.data_dir / "external" / "referees"
    path.mkdir(parents=True, exist_ok=True)
    return path


def officials_path(settings: Settings):
    return external_dir(settings) / "game_officials.parquet"


def gaps_path(settings: Settings):
    return external_dir(settings) / "officials_gaps.parquet"


def fouls_path(settings: Settings):
    return external_dir(settings) / "game_fouls.parquet"


def environment_path(settings: Settings):
    return external_dir(settings) / "game_environment.parquet"


def assignments_path(settings: Settings):
    return external_dir(settings) / "assignments.parquet"


def meta_path(settings: Settings):
    return external_dir(settings) / "referees_meta.parquet"


def history_seasons(current: str) -> tuple[str, ...]:
    """2023-24 through the configured current season, inclusive."""
    end = int(str(current)[:4])
    labels = []
    year = HISTORY_START_YEAR
    while year <= end:
        labels.append(f"{year}-{str(year + 1)[-2:]}")
        year += 1
    return tuple(labels)


def city_to_abbr(text: str) -> str | None:
    key = _WS_RE.sub(" ", text.strip().lower())
    return _CITY_ABBR.get(key)


def parse_official_cell(text: str) -> tuple[str, str]:
    """Return (name, jersey). Empty name when the cell is blank."""
    cleaned = _WS_RE.sub(" ", text).strip()
    if not cleaned:
        return "", ""
    match = _OFFICIAL_RE.match(cleaned)
    if match is None:
        return cleaned, ""
    return match.group("name").strip(), match.group("num")


def parse_assignment_page(html: str) -> list[AssignmentGame]:
    """NBA crews only. The WNBA table on the same page is ignored."""
    nba_html = re.split(r"WNBA\s+Referee\s+Assignments", html, maxsplit=1, flags=re.I)[0]
    events: list[tuple[int, str, str]] = []
    for match in _DATE_RE.finditer(nba_html):
        events.append((match.start(), "date", match.group(0)))
    for match in re.finditer(r"<table[\s\S]*?</table>", nba_html, flags=re.I):
        events.append((match.start(), "table", match.group(0)))
    events.sort(key=lambda item: item[0])
    dated: list[tuple[date | None, str]] = []
    current: date | None = None
    pending: list[str] = []
    for _pos, kind, payload in events:
        if kind == "date":
            current = _parse_long_date(payload)
            for table in pending:
                dated.append((current, table))
            pending = []
        else:
            if current is None:
                pending.append(payload)
            else:
                dated.append((current, payload))
    games: list[AssignmentGame] = []
    for slate, table in dated:
        if slate is None:
            continue
        games.extend(_parse_crew_table(table, slate))
    return games


def _parse_long_date(text: str) -> date | None:
    match = _DATE_RE.search(text)
    if match is None:
        return None
    month = _MONTHS[match.group(1).lower()]
    return date(int(match.group(3)), month, int(match.group(2)))


def _parse_crew_table(table_html: str, slate: date) -> list[AssignmentGame]:
    rows = re.findall(r"<tr[\s\S]*?</tr>", table_html, flags=re.I)
    games: list[AssignmentGame] = []
    for row in rows:
        cells = re.findall(r"<t[dh][^>]*>([\s\S]*?)</t[dh]>", row, flags=re.I)
        text = [_WS_RE.sub(" ", _TAG_RE.sub(" ", cell)).strip() for cell in cells]
        if len(text) < 4:
            continue
        if text[0].lower() == "game":
            continue
        matchup = _split_matchup(text[0])
        if matchup is None:
            continue
        away, home = matchup
        chief, chief_no = parse_official_cell(text[1])
        referee, ref_no = parse_official_cell(text[2])
        umpire, ump_no = parse_official_cell(text[3])
        if not chief or not referee or not umpire:
            continue
        games.append(
            AssignmentGame(
                game_date=slate,
                away_abbr=away,
                home_abbr=home,
                crew_chief=chief,
                referee=referee,
                umpire=umpire,
                crew_chief_jersey=chief_no,
                referee_jersey=ref_no,
                umpire_jersey=ump_no,
            )
        )
    return games


def _split_matchup(text: str) -> tuple[str, str] | None:
    if "@" not in text:
        return None
    away_text, home_text = text.split("@", 1)
    away = city_to_abbr(away_text)
    home = city_to_abbr(home_text)
    if away is None or home is None:
        return None
    return away, home


def officials_from_summary(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Crew from a BoxScoreSummaryV3 body. Alternates are dropped."""
    summary = payload.get("boxScoreSummary") if isinstance(payload, dict) else None
    rows = []
    if isinstance(summary, dict):
        raw = summary.get("officials")
        if isinstance(raw, list):
            rows = raw
    parsed: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        role = _role_for_official(row, index)
        if role not in CREW_ROLES:
            continue
        try:
            official_id = int(row.get("personId"))
        except (TypeError, ValueError):
            continue
        name = str(row.get("name") or "").strip()
        jersey = str(row.get("jerseyNum") or "").strip()
        if official_id <= 0 or not name:
            continue
        parsed.append(
            {
                "official_id": official_id,
                "official_name": name,
                "jersey": jersey,
                "role": role,
            }
        )
        if len(parsed) == 3:
            break
    return parsed


def _role_for_official(row: dict[str, Any], index: int) -> str:
    assignment = str(row.get("assignment") or "").strip().lower().replace(" ", "_")
    if assignment in {"crew_chief", "referee", "umpire", "alternate"}:
        return assignment
    if index < len(CREW_ROLES):
        return CREW_ROLES[index]
    return "alternate"


def fouls_from_league_log(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Sum both teams' personal fouls for each game. Raw rows are not stored."""
    sets = payload.get("resultSets") if isinstance(payload, dict) else None
    if not isinstance(sets, list) or not sets:
        return []
    block = sets[0]
    headers = block.get("headers") if isinstance(block, dict) else None
    rows = block.get("rowSet") if isinstance(block, dict) else None
    if not isinstance(headers, list) or not isinstance(rows, list):
        return []
    index = {str(name): pos for pos, name in enumerate(headers)}
    if "GAME_ID" not in index or "PF" not in index:
        return []
    totals: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, list):
            continue
        game_id = str(row[index["GAME_ID"]])
        try:
            fouls = int(row[index["PF"]] or 0)
        except (TypeError, ValueError):
            continue
        totals[game_id] = totals.get(game_id, 0) + fouls
    return [{"game_id": game_id, "pf": pf} for game_id, pf in sorted(totals.items())]


def format_referee_age_line(settings: Settings) -> str:
    officials = _read_rows(officials_path(settings))
    assignments = _read_rows(assignments_path(settings))
    environment = _read_rows(environment_path(settings))
    meta = _read_rows(meta_path(settings))
    live = [row for row in meta if row.get("component") == "assignments"]
    fetched = str(live[-1].get("fetched_at") or "never") if live else "never"
    games = len({str(row.get("game_id")) for row in officials})
    return (
        f"referees: {games} games with crews, {len(environment)} environment rows, "
        f"{len(assignments)} assignment rows, assignments fetched {fetched}"
    )


def refresh_referees(
    settings: Settings,
    *,
    log: LogFn = print,
    force: bool = False,
    max_games: int | None = None,
    session: requests.Session | None = None,
    sleep: SleepFn | None = None,
    today: date | None = None,
    skip_live: bool = False,
) -> RefereeRefreshStatus:
    """Live page at most once per day, then a capped historical catch-up.

    Never raises. HTTP 401, 403, and 429 stop the fetch and keep the last file.
    """
    ctx = settings.config.get("context") or {}
    if not bool(ctx.get("referees_fetch_enabled", True)):
        log("referees fetch disabled (context.referees_fetch_enabled=false)")
        return RefereeRefreshStatus(False, 0, None, ())
    warnings: list[str] = []
    fetched_live = False
    written = 0
    stopped: int | None = None
    try:
        _rebuild_environment(settings, log=log)
        client = _Client(
            settings,
            session=session or requests.Session(),
            sleep=sleep or time.sleep,
        )
        slate = today or datetime.now(timezone.utc).date()
        if skip_live:
            log("referee assignments skipped (history backfill)")
        elif force or _assignments_stale(settings, slate):
            fetched_live = _fetch_assignments(settings, client, log)
        else:
            log("referee assignments skipped (already fetched today)")
        if max_games is None:
            limit = int(ctx.get("referees_backfill_per_run", 40))
        else:
            limit = max_games
        if limit > 0:
            written = _backfill_officials(settings, client, log, limit=limit)
    except RefereeAccessBlocked as exc:
        stopped = exc.status
        warnings.append(str(exc))
        log(f"WARNING: referees stopped on HTTP {exc.status}; keeping last copy")
    except Exception as exc:  # noqa: BLE001 — daily.py must survive a bad source
        warnings.append(str(exc))
        log(f"WARNING: referees refresh failed (continuing): {exc}")
    return RefereeRefreshStatus(fetched_live, written, stopped, tuple(warnings))


def backfill_referee_history(
    settings: Settings,
    *,
    log: LogFn = print,
    limit: int | None = None,
    session: requests.Session | None = None,
    sleep: SleepFn | None = None,
) -> RefereeRefreshStatus:
    """One-time (resumable) officials history. Still never raises."""
    return refresh_referees(
        settings,
        log=log,
        force=False,
        max_games=10**9 if limit is None else limit,
        session=session,
        sleep=sleep,
        skip_live=True,
    )


class _Client:
    def __init__(self, settings: Settings, *, session: requests.Session, sleep: SleepFn) -> None:
        http = settings.config.get("http") or {}
        self.session = session
        self.sleep = sleep
        self.delay = max(1.5, float(http.get("delay_seconds", 1.5)))
        self.timeout = min(25.0, float(http.get("timeout_seconds", 25)))
        self.max_retries = min(1, int(http.get("max_retries", 1)))
        self.backoff = float(http.get("backoff_seconds", 1.0))
        self._next = 0.0
        self.headers = dict(STATS_HEADERS)
        self.headers["User-Agent"] = USER_AGENT

    def get_json(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{STATS_BASE}/{endpoint}"
        response = self._get(url, params=params, headers=self.headers)
        ctype = str(response.headers.get("content-type") or "")
        if "json" not in ctype.lower():
            raise RuntimeError(f"{endpoint} returned {ctype or 'a non-JSON body'}")
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError(f"{endpoint} returned an unexpected body")
        return payload

    def get_text(self, url: str) -> str:
        headers = {"User-Agent": USER_AGENT, "Accept": "text/html"}
        response = self._get(url, params=None, headers=headers)
        return response.text

    def _get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None,
        headers: dict[str, str],
    ) -> requests.Response:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self._wait()
            try:
                response = self.session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_error = exc
                self.sleep(self.backoff * (attempt + 1))
                continue
            if response.status_code in BLOCKED_STATUS:
                raise RefereeAccessBlocked(response.status_code, url)
            if response.status_code == 200:
                return response
            last_error = RuntimeError(f"HTTP {response.status_code} from {url}")
            self.sleep(self.backoff * (attempt + 1))
        raise RuntimeError(str(last_error) if last_error else f"failed {url}")

    def _wait(self) -> None:
        now = time.monotonic()
        if now < self._next:
            self.sleep(self._next - now)
        self._next = time.monotonic() + self.delay


def _assignments_stale(settings: Settings, today: date) -> bool:
    rows = _read_rows(meta_path(settings))
    for row in reversed(rows):
        if row.get("component") != "assignments":
            continue
        fetched = _as_date(row.get("fetched_at"))
        return fetched != today
    return True


def _fetch_assignments(settings: Settings, client: _Client, log: LogFn) -> bool:
    html = client.get_text(ASSIGNMENTS_URL)
    games = parse_assignment_page(html)
    if not games:
        log("WARNING: referee assignments page had no NBA crews; keeping last copy")
        return False
    rows: list[dict[str, Any]] = []
    for game in games:
        for role, name, jersey in (
            ("crew_chief", game.crew_chief, game.crew_chief_jersey),
            ("referee", game.referee, game.referee_jersey),
            ("umpire", game.umpire, game.umpire_jersey),
        ):
            rows.append(
                {
                    "game_date": game.game_date,
                    "away_abbr": game.away_abbr,
                    "home_abbr": game.home_abbr,
                    "role": role,
                    "official_name": name,
                    "jersey": jersey,
                }
            )
    _write_rows(assignments_path(settings), rows)
    _append_meta(
        settings,
        component="assignments",
        status="ok",
        detail=f"{len(games)} games",
        row_count=len(rows),
    )
    log(f"referee assignments stored {len(games)} NBA games")
    return True


def _backfill_officials(settings: Settings, client: _Client, log: LogFn, *, limit: int) -> int:
    seasons = history_seasons(settings.current_season)
    _ensure_fouls(settings, client, log, seasons)
    have = {str(row.get("game_id")) for row in _read_rows(officials_path(settings))}
    gaps = {str(row.get("game_id")) for row in _read_rows(gaps_path(settings))}
    pending: list[dict[str, Any]] = []
    for season in seasons:
        for row in read_rows(settings, "schedule", season):
            if str(row.get("status") or "") != "final":
                continue
            game_id = str(row.get("game_id") or "")
            if not game_id or game_id in have or game_id in gaps:
                continue
            pending.append(row)
    pending.sort(key=lambda row: (str(row.get("game_date")), str(row.get("game_id"))))
    todo = pending[:limit]
    if not todo:
        log("referee officials already stored for the requested games")
        return 0
    log(f"referee officials to fetch: {len(todo)} (missing {len(pending)})")
    existing = _read_rows(officials_path(settings))
    new_gaps = _read_rows(gaps_path(settings))
    written_games = 0
    try:
        written_games = _fetch_crew_batch(
            settings, client, log, todo=todo, existing=existing, new_gaps=new_gaps
        )
    finally:
        if existing:
            _write_rows(officials_path(settings), existing)
        if new_gaps:
            _write_rows(gaps_path(settings), new_gaps)
        _rebuild_environment(settings, log=log)
    _append_meta(
        settings,
        component="officials",
        status="ok",
        detail=f"wrote {written_games}",
        row_count=len(existing),
    )
    log(f"referee officials wrote {written_games} games")
    return written_games


def _fetch_crew_batch(settings, client, log, *, todo, existing, new_gaps) -> int:
    written_games = 0
    failures = 0
    for row in todo:
        game_id = str(row["game_id"])
        try:
            payload = client.get_json("boxscoresummaryv3", {"GameID": game_id})
        except RefereeAccessBlocked:
            raise
        except Exception as exc:
            failures += 1
            log(f"WARNING: {game_id} officials failed ({exc}); will retry on a later run")
            if failures >= 3:
                log("timeout streak; ending this batch so a fresh session can resume")
                break
            continue
        crew = officials_from_summary(payload)
        if not crew:
            new_gaps.append({"game_id": game_id})
            failures += 1
            if failures >= 8:
                _write_rows(officials_path(settings), existing)
                _write_rows(gaps_path(settings), new_gaps)
                raise RuntimeError("eight box scores in a row had no officials; stopping")
            continue
        failures = 0
        game_date = _as_date(row.get("game_date"))
        for official in crew:
            existing.append(
                {
                    "season": str(row.get("season") or ""),
                    "game_id": game_id,
                    "game_date": game_date,
                    "official_id": int(official["official_id"]),
                    "official_name": official["official_name"],
                    "jersey": official["jersey"],
                    "role": official["role"],
                    "source": "boxscoresummaryv3",
                }
            )
        written_games += 1
        if written_games % 50 == 0:
            _write_rows(officials_path(settings), existing)
            _write_rows(gaps_path(settings), new_gaps)
            log(f"referee officials stored {written_games}/{len(todo)}")
    return written_games


def _ensure_fouls(
    settings: Settings,
    client: _Client,
    log: LogFn,
    seasons: tuple[str, ...],
) -> None:
    have = _read_rows(fouls_path(settings))
    known = {str(row.get("game_id")) for row in have}
    # One request per season that is not already represented. A season is
    # complete when we have recorded its fetch in meta.
    done = {
        str(row.get("detail"))
        for row in _read_rows(meta_path(settings))
        if row.get("component") == "fouls" and row.get("status") == "ok"
    }
    for season in seasons:
        if season in done:
            continue
        payload = client.get_json(
            "leaguegamelog",
            {
                "Counter": 0,
                "Direction": "DESC",
                "LeagueID": "00",
                "PlayerOrTeam": "T",
                "Season": season,
                "SeasonType": "Regular Season",
                "Sorter": "DATE",
                "DateFrom": "",
                "DateTo": "",
            },
        )
        rows = fouls_from_league_log(payload)
        for row in rows:
            if row["game_id"] not in known:
                have.append(row)
                known.add(row["game_id"])
        _write_rows(fouls_path(settings), have)
        _append_meta(
            settings,
            component="fouls",
            status="ok",
            detail=season,
            row_count=len(rows),
        )
        log(f"referee fouls stored {len(rows)} games for {season}")


def _rebuild_environment(settings: Settings, *, log: LogFn) -> None:
    seasons = history_seasons(settings.current_season)
    team_files = []
    player_files = []
    for season in seasons:
        team_path = data_file(settings.data_dir, "team_game_results", season)
        player_path = data_file(settings.data_dir, "player_game_logs", season)
        if team_path.is_file():
            team_files.append(str(team_path))
        if player_path.is_file():
            player_files.append(str(player_path))
    if not team_files or not player_files:
        log("referee environment skipped (team or player logs missing)")
        return
    fouls = {str(row["game_id"]): int(row["pf"]) for row in _read_rows(fouls_path(settings))}
    import duckdb

    with duckdb.connect(database=":memory:") as con:
        teams = con.execute(
            """
            SELECT game_id, CAST(game_date AS DATE) AS game_date, season,
                   AVG(pace) AS pace, SUM(pace) AS possessions, SUM(pts) AS pts,
                   MAX(overtime_periods) AS overtime_periods
            FROM read_parquet(?)
            GROUP BY game_id, game_date, season
            """,
            [team_files],
        ).fetchall()
        fta_rows = con.execute(
            """
            SELECT game_id, SUM(fta) AS fta
            FROM read_parquet(?)
            GROUP BY game_id
            """,
            [player_files],
        ).fetchall()
    fta_by_game = {str(game_id): float(fta or 0.0) for game_id, fta in fta_rows}
    rows: list[dict[str, Any]] = []
    for game_id, game_date, season, pace, possessions, pts, overtime in teams:
        gid = str(game_id)
        poss = float(possessions or 0.0)
        rows.append(
            {
                "game_id": gid,
                "game_date": _as_date(game_date),
                "season": str(season),
                "pace": float(pace or 0.0),
                "possessions": poss,
                "fta": float(fta_by_game.get(gid, 0.0)),
                "pf": fouls.get(gid),
                "pts": float(pts or 0.0),
                "regulation": int(overtime or 0) == 0 and poss > 0,
            }
        )
    _write_rows(environment_path(settings), rows)
    log(f"referee environment stored {len(rows)} games")


def _append_meta(
    settings: Settings,
    *,
    component: str,
    status: str,
    detail: str,
    row_count: int,
) -> None:
    rows = _read_rows(meta_path(settings))
    rows.append(
        {
            "component": component,
            "fetched_at": datetime.now(timezone.utc).date().isoformat(),
            "status": status,
            "detail": detail,
            "row_count": int(row_count),
        }
    )
    _write_rows(meta_path(settings), rows)


def _read_rows(path) -> list[dict[str, Any]]:
    prev = path.with_name(path.stem + ".prev.parquet")
    for candidate in (path, prev):
        if not candidate.is_file():
            continue
        try:
            return pq.read_table(candidate).to_pylist()
        except Exception:
            continue
    return []


_SCHEMAS = {
    "game_officials": pa.schema(
        [
            ("season", pa.string()),
            ("game_id", pa.string()),
            ("game_date", pa.date32()),
            ("official_id", pa.int64()),
            ("official_name", pa.string()),
            ("jersey", pa.string()),
            ("role", pa.string()),
            ("source", pa.string()),
        ]
    ),
    "officials_gaps": pa.schema([("game_id", pa.string())]),
    "game_fouls": pa.schema([("game_id", pa.string()), ("pf", pa.int64())]),
    "game_environment": pa.schema(
        [
            ("game_id", pa.string()),
            ("game_date", pa.date32()),
            ("season", pa.string()),
            ("pace", pa.float64()),
            ("possessions", pa.float64()),
            ("fta", pa.float64()),
            ("pf", pa.int64()),
            ("pts", pa.float64()),
            ("regulation", pa.bool_()),
        ]
    ),
    "assignments": pa.schema(
        [
            ("game_date", pa.date32()),
            ("away_abbr", pa.string()),
            ("home_abbr", pa.string()),
            ("role", pa.string()),
            ("official_name", pa.string()),
            ("jersey", pa.string()),
        ]
    ),
    "referees_meta": pa.schema(
        [
            ("component", pa.string()),
            ("fetched_at", pa.string()),
            ("status", pa.string()),
            ("detail", pa.string()),
            ("row_count", pa.int64()),
        ]
    ),
}


def _write_rows(path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    schema = _SCHEMAS.get(path.stem)
    table = pa.Table.from_pylist(rows, schema=schema) if schema is not None else pa.Table.from_pylist(rows)
    tmp = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(table, tmp, compression="zstd")
    if path.is_file():
        shutil.copy2(path, path.with_name(path.stem + ".prev.parquet"))
    tmp.replace(path)


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        return None
    text = str(value)[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def main() -> None:
    from nba_sim.settings import load_settings

    settings = load_settings()
    status = backfill_referee_history(settings, log=print, limit=None)
    print(format_referee_age_line(settings))
    if status.stopped_status is not None:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
