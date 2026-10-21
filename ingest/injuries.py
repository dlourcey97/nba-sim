"""Official NBA injury PDF download/parse and overrides.yaml merge.

Parsed rows stay in memory for the run. The raw PDF bytes are discarded after
parsing. overrides.yaml wins over the PDF for the same player and game date.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable, Sequence

import requests
import yaml
from pypdf import PdfReader

_STATUSES = ("Out", "Doubtful", "Questionable", "Probable", "Available")
_STATUS_SET = {status.lower() for status in _STATUSES}
_STATUS_CANON = {status.lower(): status for status in _STATUSES}

# Longest first so "Portland Trail Blazers" beats shorter fragments.
_TEAM_NAMES = tuple(
    sorted(
        (
            "Atlanta Hawks",
            "Boston Celtics",
            "Brooklyn Nets",
            "Charlotte Hornets",
            "Chicago Bulls",
            "Cleveland Cavaliers",
            "Dallas Mavericks",
            "Denver Nuggets",
            "Detroit Pistons",
            "Golden State Warriors",
            "Houston Rockets",
            "Indiana Pacers",
            "LA Clippers",
            "Los Angeles Clippers",
            "Los Angeles Lakers",
            "Memphis Grizzlies",
            "Miami Heat",
            "Milwaukee Bucks",
            "Minnesota Timberwolves",
            "New Orleans Pelicans",
            "New York Knicks",
            "Oklahoma City Thunder",
            "Orlando Magic",
            "Philadelphia 76ers",
            "Phoenix Suns",
            "Portland Trail Blazers",
            "Sacramento Kings",
            "San Antonio Spurs",
            "Toronto Raptors",
            "Utah Jazz",
            "Washington Wizards",
        ),
        key=len,
        reverse=True,
    )
)
_TEAM_NAME_RE = re.compile("|".join(re.escape(name) for name in _TEAM_NAMES))
_MATCHUP_RE = re.compile(r"\b([A-Z]{2,3})@([A-Z]{2,3})\b")
_DATE_RE = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b")
_TIME_RE = re.compile(r"\b(\d{1,2}:\d{2})\s*\(ET\)")
# Last names are one token (hyphenated OK) plus optional generational suffix
# (II, III, Jr., Sr.) so "Lively II, Dereck" / "Butler III, Jimmy" parse.
# First names are one or two tokens so reason text like
# "Surgery, Injury Recovery Wolf, Danny" does not swallow Wolf.
_PLAYER_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9'.]*(?:-[A-Z][A-Za-z0-9'.]*)*"
    r"(?:\s+(?:II|III|IV|Jr\.?|Sr\.?))?),\s+"
    r"([A-Z][A-Za-z0-9'.]*(?:-[A-Za-z0-9'.]*)*"
    r"(?:\s+(?:[A-Z]\.|[A-Z][a-z][A-Za-z0-9'.]*))?)\s+"
    r"(Out|Doubtful|Questionable|Probable|Available)\b",
)
_HEADER_RE = re.compile(
    r"Injury\s+Report:.*?Page\s+\d+\s+of\s+\d+|Game\s+Date\s+Game\s+Time\s+"
    r"Matchup\s+Team\s+Player\s+Name\s+Current\s+Status\s+Reason",
    re.IGNORECASE | re.DOTALL,
)
# CDN keys use HH_MMPM (e.g. 02_00PM, 05_30PM). Hour-only stamps still work
# via _normalize_time_token.
_REPORT_TIMES = (
    "09:00AM",
    "11:00AM",
    "11:30AM",
    "12:00PM",
    "01:00PM",
    "02:00PM",
    "02:30PM",
    "03:00PM",
    "03:30PM",
    "04:00PM",
    "05:00PM",
    "05:30PM",
    "05:45PM",
    "06:00PM",
    "06:30PM",
    "07:00PM",
    "08:00PM",
    "08:30PM",
)
# Primary CDN first. static.cms.nba.com often hangs on unpublished keys — only
# used as a single last-resort fallback after every primary miss.
_URL_TEMPLATE_PRIMARY = (
    "https://ak-static.cms.nba.com/referee/injury/Injury-Report_{date}_{time}.pdf"
)
_URL_TEMPLATE_FALLBACK = (
    "https://static.cms.nba.com/referee/injury/Injury-Report_{date}_{time}.pdf"
)
_URL_TEMPLATES = (_URL_TEMPLATE_PRIMARY, _URL_TEMPLATE_FALLBACK)


@dataclass(frozen=True)
class InjuryEntry:
    game_date: date
    matchup: str | None
    team_name: str | None
    team_abbr: str | None
    player_name: str
    player_id: int | None
    status: str
    reason: str
    minutes_cap: float | None
    source: str


class InjuryReportError(Exception):
    """Injury PDF or overrides could not be loaded."""


def load_overrides(path: Path) -> list[InjuryEntry]:
    """Load overrides.yaml. Missing file means no overrides."""
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    if loaded is None:
        return []
    if not isinstance(loaded, dict):
        raise InjuryReportError(f"{path} must be a mapping.")
    players = loaded.get("players", [])
    if players is None:
        return []
    if not isinstance(players, list):
        raise InjuryReportError(f"{path} players must be a list.")
    rows: list[InjuryEntry] = []
    for index, item in enumerate(players):
        if not isinstance(item, dict):
            raise InjuryReportError(f"{path} players[{index}] must be a mapping.")
        rows.append(_override_entry(item, path, index))
    return rows


def parse_injury_pdf_bytes(payload: bytes, *, report_date: date | None = None) -> list[InjuryEntry]:
    """Parse an official injury PDF from bytes. Does not write the PDF to disk."""
    if not payload.startswith(b"%PDF"):
        raise InjuryReportError("injury response is not a PDF.")
    reader = PdfReader(BytesIO(payload))
    words: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        words.extend(line.strip() for line in text.splitlines() if line.strip())
    joined = " ".join(words)
    joined = _HEADER_RE.sub(" ", joined)
    joined = re.sub(r"(?<=\w)- (?=\w)", "-", joined)
    joined = re.sub(r"\s+", " ", joined).strip()
    return parse_injury_text(joined, report_date=report_date)


def parse_injury_text(text: str, *, report_date: date | None = None) -> list[InjuryEntry]:
    """Parse cleaned injury-report text into entries."""
    if not text.strip():
        return []
    text = _HEADER_RE.sub(" ", text)
    text = re.sub(r"(?<=\w)- (?=\w)", "-", text)
    text = re.sub(r"\s+", " ", text).strip()
    default_date = report_date
    entries: list[InjuryEntry] = []
    # Split on matchups while keeping the delimiter.
    parts = _MATCHUP_RE.split(text)
    # parts: [prefix, away, home, middle, away, home, ...]
    if len(parts) == 1:
        return _parse_team_block(parts[0], default_date, None, None)

    prefix = parts[0]
    current_date = _latest_date(prefix, default_date)
    for index in range(1, len(parts), 3):
        away = parts[index]
        home = parts[index + 1]
        body = parts[index + 2] if index + 2 < len(parts) else ""
        matchup = f"{away}@{home}"
        dated = _latest_date(prefix if index == 1 else "", current_date)
        # Date may appear just before this matchup in the previous body.
        if index > 1:
            prev_body = parts[index - 1]
            dated = _latest_date(prev_body, dated)
        current_date = dated or current_date
        # Also scan the start of this body for a leading date/time leftover.
        body_date = _latest_date(body[:40], current_date)
        current_date = body_date or current_date
        entries.extend(_parse_team_block(body, current_date, matchup, None))
        prefix = body
    return entries


def download_injury_report(
    game_date: date,
    *,
    delay_seconds: float = 0.6,
    max_retries: int = 3,
    backoff_seconds: float = 1.0,
    timeout_seconds: float = 60.0,
    report_times: Sequence[str] | None = None,
    session: requests.Session | None = None,
    log: logging.Logger | None = None,
) -> tuple[bytes, str]:
    """Download the newest available injury PDF for a calendar date.

    Tries common report times from newest to oldest. Returns (pdf_bytes, url).
    """
    logger = log or logging.getLogger(__name__)
    client = session or requests.Session()
    times = list(report_times or _REPORT_TIMES)
    # Prefer evening reports first for a full slate.
    ordered = sorted(set(times), key=_time_sort_key, reverse=True)
    last_error: Exception | None = None

    def _try(template: str, stamp: str, *, retries: int, timeout: float) -> bytes | None:
        nonlocal last_error
        url = template.format(date=game_date.isoformat(), time=_normalize_time_token(stamp))
        try:
            payload = _get_pdf(
                client,
                url,
                delay_seconds=delay_seconds,
                max_retries=retries,
                backoff_seconds=backoff_seconds,
                timeout_seconds=timeout,
            )
        except InjuryReportError as exc:
            last_error = exc
            logger.debug("injury PDF miss %s: %s", url, exc)
            return None
        if payload:
            logger.info("downloaded injury report %s (%d bytes)", url, len(payload))
            return payload
        return None

    # Walk primary CDN across all report times before touching the slow fallback.
    for stamp in ordered:
        payload = _try(
            _URL_TEMPLATE_PRIMARY,
            stamp,
            retries=max_retries,
            timeout=timeout_seconds,
        )
        if payload:
            url = _URL_TEMPLATE_PRIMARY.format(
                date=game_date.isoformat(), time=_normalize_time_token(stamp)
            )
            return payload, url

    # One short-timeout attempt on the alternate host (newest stamp only).
    if ordered:
        stamp = ordered[0]
        payload = _try(
            _URL_TEMPLATE_FALLBACK,
            stamp,
            retries=0,
            timeout=min(12.0, float(timeout_seconds)),
        )
        if payload:
            url = _URL_TEMPLATE_FALLBACK.format(
                date=game_date.isoformat(), time=_normalize_time_token(stamp)
            )
            return payload, url

    raise InjuryReportError(
        f"no injury PDF found for {game_date.isoformat()}. Last error: {last_error}"
    )


def fetch_injuries_for_date(
    game_date: date,
    *,
    overrides_path: Path,
    delay_seconds: float = 0.6,
    max_retries: int = 3,
    backoff_seconds: float = 1.0,
    timeout_seconds: float = 60.0,
    log: logging.Logger | None = None,
) -> list[InjuryEntry]:
    """Download, parse, discard the PDF, and merge overrides."""
    overrides = load_overrides(overrides_path)
    try:
        payload, _url = download_injury_report(
            game_date,
            delay_seconds=delay_seconds,
            max_retries=max_retries,
            backoff_seconds=backoff_seconds,
            timeout_seconds=timeout_seconds,
            log=log,
        )
        report = parse_injury_pdf_bytes(payload, report_date=game_date)
        del payload
    except InjuryReportError:
        # Overrides alone are still usable when the PDF is unavailable.
        report = []
    return merge_injuries(report, overrides, game_date=game_date)


def merge_injuries(
    report: Sequence[InjuryEntry],
    overrides: Sequence[InjuryEntry],
    *,
    game_date: date | None = None,
) -> list[InjuryEntry]:
    """Combine PDF rows with overrides. Overrides win on player identity.

    PDF rows are often name-only (no player_id); overrides usually carry an id.
    Drop any report row that matches an override by player_id **or** by
    (game_date, team_abbr, normalized name) so both keys cannot coexist.
    """
    filtered_report: list[InjuryEntry] = []
    for entry in report:
        if game_date is not None and entry.game_date != game_date:
            continue
        filtered_report.append(entry)

    filtered_overrides: list[InjuryEntry] = []
    for entry in overrides:
        if game_date is not None and entry.game_date != game_date:
            continue
        filtered_overrides.append(entry)

    override_ids = {int(e.player_id) for e in filtered_overrides if e.player_id is not None}
    override_names = {
        (e.game_date, (e.team_abbr or "").upper(), _norm_name(e.player_name))
        for e in filtered_overrides
    }

    merged: dict[tuple[Any, ...], InjuryEntry] = {}
    for entry in filtered_report:
        if entry.player_id is not None and int(entry.player_id) in override_ids:
            continue
        name_key = (entry.game_date, (entry.team_abbr or "").upper(), _norm_name(entry.player_name))
        if name_key in override_names:
            continue
        merged[_entry_key(entry)] = entry
    for entry in filtered_overrides:
        merged[_entry_key(entry)] = entry
    return sorted(
        merged.values(),
        key=lambda row: (row.game_date, row.team_abbr or "", row.player_name),
    )


def active_absences(entries: Sequence[InjuryEntry]) -> list[InjuryEntry]:
    """Players who should not receive normal minutes (out/doubtful)."""
    return [entry for entry in entries if entry.status.lower() in {"out", "doubtful"}]


def minutes_caps(entries: Sequence[InjuryEntry]) -> dict[int, float]:
    """player_id -> minutes_cap for overrides that set one."""
    caps: dict[int, float] = {}
    for entry in entries:
        if entry.player_id is not None and entry.minutes_cap is not None:
            caps[int(entry.player_id)] = float(entry.minutes_cap)
    return caps


def _parse_team_block(
    body: str,
    game_date: date | None,
    matchup: str | None,
    team_name: str | None,
) -> list[InjuryEntry]:
    text = body.strip()
    if not text:
        return []
    # Drop leading times left over from the previous matchup split.
    text = re.sub(r"^\d{1,2}:\d{2}\s*\(ET\)\s*", "", text)
    text = re.sub(r"^\d{1,2}/\d{1,2}/\d{4}\s*", "", text)
    entries: list[InjuryEntry] = []
    current_team = team_name
    # Walk team-name markers and player rows inside each segment.
    markers = list(_TEAM_NAME_RE.finditer(text))
    if not markers:
        return _parse_players(text, game_date, matchup, current_team)

    # Text before the first team name is ignored (usually leftover time).
    for index, marker in enumerate(markers):
        current_team = marker.group(0)
        start = marker.end()
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        segment = text[start:end].strip()
        if segment.upper().startswith("NOT YET SUBMITTED"):
            continue
        entries.extend(_parse_players(segment, game_date, matchup, current_team))
    return entries


def _parse_players(
    segment: str,
    game_date: date | None,
    matchup: str | None,
    team_name: str | None,
) -> list[InjuryEntry]:
    if game_date is None:
        game_date = date.today()
    entries: list[InjuryEntry] = []
    matches = list(_PLAYER_RE.finditer(segment))
    for index, match in enumerate(matches):
        last = match.group(1).strip()
        first = match.group(2).strip()
        status = _STATUS_CANON[match.group(3).lower()]
        reason_start = match.end()
        reason_end = matches[index + 1].start() if index + 1 < len(matches) else len(segment)
        reason = segment[reason_start:reason_end].strip(" -;")
        reason = re.sub(r"\s+", " ", reason).strip()
        # Trim a following team name accidentally captured in the reason.
        team_hit = _TEAM_NAME_RE.search(reason)
        if team_hit and team_hit.start() > 0:
            reason = reason[: team_hit.start()].strip(" -;")
        player_name = f"{first} {last}"
        away_abbr = home_abbr = None
        if matchup and "@" in matchup:
            away_abbr, home_abbr = matchup.split("@", 1)
        team_abbr = _guess_team_abbr(team_name, away_abbr, home_abbr)
        entries.append(
            InjuryEntry(
                game_date=game_date,
                matchup=matchup,
                team_name=team_name,
                team_abbr=team_abbr,
                player_name=player_name,
                player_id=None,
                status=status,
                reason=reason,
                minutes_cap=None,
                source="injury_report",
            )
        )
    return entries


def _guess_team_abbr(team_name: str | None, away: str | None, home: str | None) -> str | None:
    if team_name is None:
        return None
    mapping = {
        "Atlanta Hawks": "ATL",
        "Boston Celtics": "BOS",
        "Brooklyn Nets": "BKN",
        "Charlotte Hornets": "CHA",
        "Chicago Bulls": "CHI",
        "Cleveland Cavaliers": "CLE",
        "Dallas Mavericks": "DAL",
        "Denver Nuggets": "DEN",
        "Detroit Pistons": "DET",
        "Golden State Warriors": "GSW",
        "Houston Rockets": "HOU",
        "Indiana Pacers": "IND",
        "LA Clippers": "LAC",
        "Los Angeles Clippers": "LAC",
        "Los Angeles Lakers": "LAL",
        "Memphis Grizzlies": "MEM",
        "Miami Heat": "MIA",
        "Milwaukee Bucks": "MIL",
        "Minnesota Timberwolves": "MIN",
        "New Orleans Pelicans": "NOP",
        "New York Knicks": "NYK",
        "Oklahoma City Thunder": "OKC",
        "Orlando Magic": "ORL",
        "Philadelphia 76ers": "PHI",
        "Phoenix Suns": "PHX",
        "Portland Trail Blazers": "POR",
        "Sacramento Kings": "SAC",
        "San Antonio Spurs": "SAS",
        "Toronto Raptors": "TOR",
        "Utah Jazz": "UTA",
        "Washington Wizards": "WAS",
    }
    abbr = mapping.get(team_name)
    if abbr is not None:
        return abbr
    return away if away and away in (away, home) else home


def _override_entry(item: dict[str, Any], path: Path, index: int) -> InjuryEntry:
    try:
        game_date = date.fromisoformat(str(item["game_date"]))
    except (KeyError, ValueError) as exc:
        raise InjuryReportError(f"{path} players[{index}] needs game_date YYYY-MM-DD.") from exc
    status_raw = str(item.get("status", "")).strip().lower()
    if status_raw not in _STATUS_SET:
        raise InjuryReportError(
            f"{path} players[{index}] status must be one of {sorted(_STATUS_SET)}."
        )
    player_id = item.get("player_id")
    if player_id is not None:
        player_id = int(player_id)
    minutes_cap = item.get("minutes_cap")
    if minutes_cap is not None:
        minutes_cap = float(minutes_cap)
    name = str(item.get("player_name") or "").strip()
    if not name and player_id is None:
        raise InjuryReportError(f"{path} players[{index}] needs player_name or player_id.")
    return InjuryEntry(
        game_date=game_date,
        matchup=item.get("matchup"),
        team_name=item.get("team_name"),
        team_abbr=str(item["team_abbr"]).upper() if item.get("team_abbr") else None,
        player_name=name or f"player:{player_id}",
        player_id=player_id,
        status=_STATUS_CANON[status_raw],
        reason=str(item.get("reason") or "override"),
        minutes_cap=minutes_cap,
        source="override",
    )


def _entry_key(entry: InjuryEntry) -> tuple[Any, ...]:
    if entry.player_id is not None:
        return (entry.game_date, "id", int(entry.player_id))
    return (
        entry.game_date,
        "name",
        (entry.team_abbr or "").upper(),
        _norm_name(entry.player_name),
    )


def _norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _latest_date(text: str, fallback: date | None) -> date | None:
    found = None
    for match in _DATE_RE.finditer(text or ""):
        found = datetime.strptime(match.group(1), "%m/%d/%Y").date()
    return found or fallback


def _normalize_time_token(stamp: str) -> str:
    """Map stamps to CDN form Injury-Report_{date}_HH_MMPM.pdf.

    2026+ CDN keys use zero-padded hour and minutes with an underscore
    (02_00PM, 05_30PM). Hour-only inputs (02PM) become HH_00PM.
    """
    cleaned = stamp.strip().upper().replace(" ", "").replace("_", ":")
    # Accept already-normalized HH_MMPM by restoring colon for the matcher.
    if re.fullmatch(r"\d{2}:\d{2}(AM|PM)", cleaned):
        pass
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?(AM|PM)", cleaned)
    if not match:
        return cleaned.replace(":", "_")
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    return f"{hour:02d}_{minute:02d}{match.group(3)}"


def _time_sort_key(stamp: str) -> tuple[int, int]:
    cleaned = stamp.strip().upper().replace(" ", "")
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?(AM|PM)", cleaned)
    if not match:
        return (0, 0)
    hour = int(match.group(1)) % 12
    if match.group(3) == "PM":
        hour += 12
    minute = int(match.group(2) or 0)
    return hour, minute


def _get_pdf(
    session: requests.Session,
    url: str,
    *,
    delay_seconds: float,
    max_retries: int,
    backoff_seconds: float,
    timeout_seconds: float,
) -> bytes | None:
    if delay_seconds > 0:
        time.sleep(delay_seconds)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/pdf,*/*",
    }
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            response = session.get(url, headers=headers, timeout=timeout_seconds)
        except requests.Timeout as exc:
            # Unpublished / dead hosts hang; treat as a miss so the caller can
            # advance to the next report time instead of burning the slate.
            last_error = exc
            return None
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(backoff_seconds * (2**attempt))
            continue
        if response.status_code in (403, 404):
            # Not posted yet (404) or CDN blocks unpublished keys (403).
            return None
        if response.status_code >= 500:
            last_error = InjuryReportError(f"HTTP {response.status_code} for {url}")
            time.sleep(backoff_seconds * (2**attempt))
            continue
        if response.status_code != 200:
            raise InjuryReportError(f"HTTP {response.status_code} for {url}")
        payload = response.content
        if not payload.startswith(b"%PDF"):
            # HTML interstitial: do not retry as if it were transient JSON.
            raise InjuryReportError(f"non-PDF body for {url}")
        return payload
    raise InjuryReportError(f"failed to download {url}: {last_error}")
