"""Historical injury reports for walk-forward seasons.

2024-25 and 2025-26 files use hour-only CDN names
(Injury-Report_YYYY-MM-DD_05PM.pdf). The live getter rewrites those stamps to
HH_00PM and misses them. Raw PDFs are parsed in memory and discarded.

A player row is stored only from a report whose own clock time is strictly
before that game's tip. Both times are read from the PDF.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, time as clock
from io import BytesIO

import pyarrow as pa
import pyarrow.parquet as pq
import requests
from pypdf import PdfReader

from ingest.injuries import parse_injury_text
from nba_sim.settings import load_settings
from nba_sim.storage import read_rows

log = logging.getLogger("injury_archive")

_PRIMARY = "https://ak-static.cms.nba.com/referee/injury/Injury-Report_{date}_{stamp}.pdf"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_PUBLISH_RE = re.compile(
    r"Injury\s+Report:\s*(\d{1,2}/\d{1,2}/\d{2,4})\s+(\d{1,2}:\d{2})\s*(AM|PM)",
    re.IGNORECASE,
)
_TIP_RE = re.compile(r"(\d{1,2}:\d{2})\s*\(ET\)\s*([A-Z]{2,3}@[A-Z]{2,3})")
# Evening report first. Earlier hours are fetched only when a tip is before it.
_ANCHOR_STAMPS = ("05PM", "01PM", "06PM", "12PM", "02PM", "04PM", "07PM", "11AM", "03PM", "08PM")
_EARLIER = ("04PM", "03PM", "02PM", "01PM", "12PM", "11AM", "10AM", "09AM")
# Hour-only keys 403 starting 2025-12-22. That day's 05_30PM file is a PDF.
_MINUTE_STAMP_START = date(2025, 12, 22)
_ANCHOR_STAMPS_MINUTE = (
    "05_30PM",
    "01_30PM",
    "06_00PM",
    "12_00PM",
    "02_00PM",
    "04_00PM",
    "07_00PM",
    "11_00AM",
    "03_00PM",
    "08_00PM",
)
_EARLIER_MINUTE = (
    "04_30PM",
    "04_00PM",
    "03_30PM",
    "03_00PM",
    "02_30PM",
    "02_00PM",
    "01_30PM",
    "01_00PM",
    "12_30PM",
    "12_00PM",
    "11_30AM",
    "11_00AM",
    "10_00AM",
)
_SCHEMA = pa.schema(
    [
        ("game_date", pa.string()),
        ("matchup", pa.string()),
        ("team_abbr", pa.string()),
        ("player_name", pa.string()),
        ("status", pa.string()),
        ("reason", pa.string()),
        ("report_time", pa.string()),
        ("tip_time", pa.string()),
        ("report_stamp", pa.string()),
    ]
)


class ArchiveStopped(RuntimeError):
    """Repeated 403s. The crawl does not continue."""


@dataclass
class ParsedReport:
    stamp: str
    published: datetime
    tips: dict[str, clock]
    entries: list


def _ampm_to_clock(text: str, ampm: str) -> clock:
    hour_text, minute_text = text.split(":")
    hour = int(hour_text)
    minute = int(minute_text)
    marker = ampm.upper()
    if marker == "PM" and hour != 12:
        hour += 12
    if marker == "AM" and hour == 12:
        hour = 0
    return clock(hour, minute)


def _stamp_clock(stamp: str) -> clock:
    match = re.fullmatch(r"(\d{2})(?:_(\d{2}))?(AM|PM)", stamp.upper())
    if match is None:
        raise ValueError(stamp)
    minute = int(match.group(2) or 0)
    return _ampm_to_clock(f"{int(match.group(1)):02d}:{minute:02d}", match.group(3))


def _stamp_lists(game_date: date) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if game_date >= _MINUTE_STAMP_START:
        return _ANCHOR_STAMPS_MINUTE, _EARLIER_MINUTE
    return _ANCHOR_STAMPS, _EARLIER


def joined_pdf_text(payload: bytes) -> str:
    reader = PdfReader(BytesIO(payload))
    words: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        words.extend(line.strip() for line in text.splitlines() if line.strip())
    joined = " ".join(words)
    return re.sub(r"\s+", " ", joined).strip()


def parse_report(payload: bytes, *, game_date: date, stamp: str) -> ParsedReport | None:
    """Return the report, or None when its header date is a different day."""
    text = joined_pdf_text(payload)
    published = _published(text, game_date, stamp)
    tips = {match.group(2): _clock_on_24h(match.group(1)) for match in _TIP_RE.finditer(text)}
    if published is None or not tips:
        return None
    if published.date() != game_date:
        return None
    entries = parse_injury_text(text, report_date=game_date)
    return ParsedReport(stamp=stamp, published=published, tips=tips, entries=entries)


def _clock_on_24h(hhmm: str) -> clock:
    """Game times in the report are afternoon or evening, so 1:00 is 13:00."""
    hour_text, minute_text = hhmm.split(":")
    hour = int(hour_text)
    minute = int(minute_text)
    if hour < 11:
        hour += 12
    return clock(hour, minute)


def _published(text: str, game_date: date, stamp: str) -> datetime | None:
    match = _PUBLISH_RE.search(text)
    if match is None:
        published_clock = _stamp_clock(stamp)
        return datetime.combine(game_date, published_clock)
    year_text = match.group(1).split("/")[-1]
    year = int(year_text) + (2000 if len(year_text) == 2 else 0)
    month, day = (int(part) for part in match.group(1).split("/")[:2])
    published_clock = _ampm_to_clock(match.group(2), match.group(3))
    try:
        found = date(year, month, day)
    except ValueError:
        return None
    if found != game_date:
        return None
    return datetime.combine(game_date, published_clock)


def keep_latest_before_tip(reports: list[ParsedReport]) -> list[dict]:
    """Latest status whose report clock is strictly before that game's tip."""
    tips: dict[str, clock] = {}
    for report in reports:
        tips.update(report.tips)
    chosen: dict[tuple[str, str], dict] = {}
    ordered = sorted(reports, key=lambda report: report.published)
    for report in ordered:
        for entry in report.entries:
            matchup = entry.matchup or ""
            tip = tips.get(matchup)
            if tip is None:
                continue
            tip_at = datetime.combine(report.published.date(), tip)
            if report.published >= tip_at:
                continue
            chosen[(matchup, entry.player_name)] = {
                "game_date": report.published.date().isoformat(),
                "matchup": matchup,
                "team_abbr": entry.team_abbr or "",
                "player_name": entry.player_name,
                "status": entry.status,
                "reason": entry.reason,
                "report_time": report.published.strftime("%H:%M"),
                "tip_time": tip.strftime("%H:%M"),
                "report_stamp": report.stamp,
            }
    return list(chosen.values())


def _get_pdf(session: requests.Session, url: str) -> tuple[int, bytes | None]:
    time.sleep(1.5)
    try:
        response = session.get(
            url,
            headers={"User-Agent": _UA, "Accept": "application/pdf,*/*"},
            timeout=25,
        )
    except requests.RequestException:
        return 0, None
    if response.status_code == 200 and response.content.startswith(b"%PDF"):
        return 200, response.content
    return response.status_code, None


def _dates(settings, season: str) -> list[date]:
    found: set[date] = set()
    for row in read_rows(settings, "schedule", season):
        if row.get("status") != "final":
            continue
        raw = row["game_date"]
        if isinstance(raw, date):
            found.add(raw)
        else:
            found.add(date.fromisoformat(str(raw)[:10]))
    return sorted(found)


def _done_dates(path) -> set[str]:
    if not path.is_file():
        return set()
    table = pq.read_table(path, columns=["game_date"])
    return set(table.column("game_date").to_pylist())


def _write(path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        previous = path.with_suffix(".prev.parquet")
        previous.write_bytes(path.read_bytes())
    table = pa.Table.from_pylist(rows, schema=_SCHEMA) if rows else pa.table(
        {field.name: pa.array([], type=field.type) for field in _SCHEMA}
    )
    pq.write_table(table, path, compression="zstd")


def _stamps_needed(anchor: ParsedReport | None, tried: set[str], game_date: date) -> list[str]:
    anchors, earlier = _stamp_lists(game_date)
    if anchor is None:
        return [stamp for stamp in anchors if stamp not in tried]
    earliest = min(anchor.tips.values())
    if anchor.published.time() < earliest:
        return []
    return [stamp for stamp in earlier if stamp not in tried and _stamp_clock(stamp) < earliest]


def archive_seasons(settings, seasons: list[str], *, max_consecutive_403: int = 8) -> dict:
    """Download pre-tip reports for final-game dates. Stops after repeated 403s."""
    directory = settings.data_dir / "external" / "injuries"
    path = directory / "reports.parquet"
    done_path = directory / "dates.parquet"
    existing = pq.read_table(path).to_pylist() if path.is_file() else []
    done = _done_dates(done_path)
    session = requests.Session()
    consecutive_403 = 0
    fetched_dates = 0
    try:
        for season in seasons:
            for game_date in _dates(settings, season):
                key = game_date.isoformat()
                if key in done:
                    continue
                reports, consecutive_403 = _reports_for_date(
                    session,
                    game_date,
                    consecutive_403,
                    max_consecutive_403,
                )
                rows = keep_latest_before_tip(reports)
                existing = [row for row in existing if row["game_date"] != key]
                existing.extend(rows)
                done.add(key)
                _write(path, existing)
                _write_dates(done_path, done)
                fetched_dates += 1
                log.info("%s kept %d rows from %d reports", key, len(rows), len(reports))
    except ArchiveStopped as exc:
        log.warning("%s", exc)
        return {"dates": fetched_dates, "rows": len(existing), "stopped": str(exc)}
    return {"dates": fetched_dates, "rows": len(existing), "stopped": ""}


def _write_dates(path, done: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.table({"game_date": pa.array(sorted(done), type=pa.string())})
    pq.write_table(table, path, compression="zstd")


def _reports_for_date(
    session: requests.Session,
    game_date: date,
    consecutive_403: int,
    max_consecutive_403: int,
) -> tuple[list[ParsedReport], int]:
    tried: set[str] = set()
    reports: list[ParsedReport] = []
    anchor: ParsedReport | None = None
    while True:
        pending = _stamps_needed(anchor, tried, game_date)
        if not pending:
            return reports, consecutive_403
        stamp = pending[0]
        tried.add(stamp)
        status, payload = _get_pdf(session, _PRIMARY.format(date=game_date.isoformat(), stamp=stamp))
        if status == 403:
            consecutive_403 += 1
            if consecutive_403 >= max_consecutive_403:
                raise ArchiveStopped(
                    f"stopped after {consecutive_403} consecutive 403 responses at {game_date} {stamp}"
                )
            continue
        if status != 200 or payload is None:
            consecutive_403 = 0
            continue
        consecutive_403 = 0
        parsed = parse_report(payload, game_date=game_date, stamp=stamp)
        del payload
        if parsed is None:
            continue
        reports.append(parsed)
        if anchor is None or parsed.published > anchor.published:
            anchor = parsed
        if len(tried) >= 8:
            return reports, consecutive_403


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    settings = load_settings()
    result = archive_seasons(settings, ["2024-25", "2025-26"])
    print(
        f"INJURY_ARCHIVE dates={result['dates']} rows={result['rows']} stopped={result['stopped'] or 'no'}",
        flush=True,
    )


if __name__ == "__main__":
    main()
