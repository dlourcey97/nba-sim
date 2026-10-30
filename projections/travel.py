"""Travel and schedule density from games already played.

No website. Arena locations are fixed. A slate on date D uses only games
with game_date < D. The pace adjustment is zero unless travel_enabled is on.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# team abbr -> latitude, longitude, IANA zone, altitude feet.
ARENAS: dict[str, tuple[float, float, str, int]] = {
    "ATL": (33.7573, -84.3963, "America/New_York", 1050),
    "BOS": (42.3662, -71.0621, "America/New_York", 20),
    "BKN": (40.6826, -73.9754, "America/New_York", 30),
    "CHA": (35.2251, -80.8392, "America/New_York", 750),
    "CHI": (41.8807, -87.6742, "America/Chicago", 590),
    "CLE": (41.4965, -81.6882, "America/New_York", 650),
    "DAL": (32.7905, -96.8103, "America/Chicago", 430),
    "DEN": (39.7487, -105.0077, "America/Denver", 5280),
    "DET": (42.3411, -83.0553, "America/Detroit", 600),
    "GSW": (37.7680, -122.3877, "America/Los_Angeles", 10),
    "HOU": (29.7508, -95.3621, "America/Chicago", 50),
    "IND": (39.7639, -86.1555, "America/Indiana/Indianapolis", 720),
    "LAC": (33.9454, -118.3417, "America/Los_Angeles", 100),
    "LAL": (34.0430, -118.2673, "America/Los_Angeles", 270),
    "MEM": (35.1382, -90.0506, "America/Chicago", 330),
    "MIA": (25.7814, -80.1870, "America/New_York", 10),
    "MIL": (43.0451, -87.9172, "America/Chicago", 580),
    "MIN": (44.9795, -93.2761, "America/Chicago", 830),
    "NOP": (29.9490, -90.0821, "America/Chicago", 3),
    "NYK": (40.7505, -73.9934, "America/New_York", 30),
    "OKC": (35.4634, -97.5151, "America/Chicago", 1200),
    "ORL": (28.5392, -81.3839, "America/New_York", 80),
    "PHI": (39.9012, -75.1720, "America/New_York", 40),
    "PHX": (33.4457, -112.0712, "America/Phoenix", 1086),
    "POR": (45.5316, -122.6668, "America/Los_Angeles", 50),
    "SAC": (38.5802, -121.4997, "America/Los_Angeles", 30),
    "SAS": (29.4270, -98.4375, "America/Chicago", 650),
    "TOR": (43.6435, -79.3791, "America/Toronto", 250),
    "UTA": (40.7683, -111.9011, "America/Denver", 4226),
    "WAS": (38.8981, -77.0209, "America/New_York", 25),
}
HIGH_ALTITUDE = {"DEN", "UTA"}
_EARTH_MILES = 3958.8


@dataclass(frozen=True)
class TravelState:
    miles: float
    tz_hours: float
    games_last_4: int
    games_last_6: int
    road_trip: int
    altitude_arrival: bool


def _coords(abbr: str) -> tuple[float, float]:
    lat, lon, _zone, _alt = ARENAS[abbr]
    return lat, lon


def haversine_miles(origin: str, dest: str) -> float:
    lat1, lon1 = _coords(origin)
    lat2, lon2 = _coords(dest)
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * _EARTH_MILES * math.asin(math.sqrt(a))


def _tz_hours(origin: str, dest: str, game_date: date) -> float:
    moment = datetime(game_date.year, game_date.month, game_date.day, 18, tzinfo=timezone.utc)
    origin_off = moment.astimezone(ZoneInfo(ARENAS[origin][2])).utcoffset()
    dest_off = moment.astimezone(ZoneInfo(ARENAS[dest][2])).utcoffset()
    if origin_off is None or dest_off is None:
        return 0.0
    return (dest_off - origin_off).total_seconds() / 3600.0


def _as_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def travel_state(
    schedule: list[dict],
    *,
    team_id: int,
    team_abbr: str,
    game_date: date,
    home_away: str,
    opponent_abbr: str,
) -> TravelState:
    """Fatigue inputs from this team's games strictly before game_date."""
    game_date = _as_date(game_date)
    prior: list[tuple[date, str, bool]] = []
    for row in schedule:
        when = _as_date(row["game_date"])
        if when >= game_date:
            continue
        home = int(row["home_team_id"]) == int(team_id)
        away = int(row["away_team_id"]) == int(team_id)
        if not home and not away:
            continue
        location = str(row["home_abbr"]) if home else str(row["away_abbr"])
        # Away team's location is the opponent's arena, which is the home abbr.
        if away:
            location = str(row["home_abbr"])
        prior.append((when, location, away))
    prior.sort()
    here = team_abbr if home_away == "H" else opponent_abbr
    if not prior:
        return TravelState(0.0, 0.0, 0, 0, 1 if home_away == "A" else 0, False)
    last_date, last_loc, _last_away = prior[-1]
    miles = 0.0 if last_loc == here else haversine_miles(last_loc, here)
    tz = 0.0 if last_loc == here else _tz_hours(last_loc, here, game_date)
    games_4 = sum(1 for when, _loc, _away in prior if game_date - timedelta(days=4) <= when < game_date)
    games_6 = sum(1 for when, _loc, _away in prior if game_date - timedelta(days=6) <= when < game_date)
    road = 1 if home_away == "A" else 0
    if home_away == "A":
        for _when, _loc, was_away in reversed(prior):
            if not was_away:
                break
            road += 1
    arrival = here in HIGH_ALTITUDE and last_loc not in HIGH_ALTITUDE
    return TravelState(miles, tz, games_4, games_6, road, arrival)


def travel_pace_delta(state: TravelState, *, enabled: bool) -> float:
    """Negative pace shift, clipped at 1.5%. Zero when the flag is off."""
    if not enabled:
        return 0.0
    load = (
        min(state.miles / 1000.0, 2.5) * 0.004
        + min(abs(state.tz_hours), 3.0) * 0.003
        + max(0, state.games_last_4 - 1) * 0.003
        + max(0, state.road_trip - 1) * 0.002
        + (0.004 if state.altitude_arrival else 0.0)
    )
    return -min(0.015, load)
