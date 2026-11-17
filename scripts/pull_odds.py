"""Cache a DraftKings board. The sim never reads this file.

One call is the morning board (summary.json). A second call, about 30 minutes
before tip, is the close (close_summary.json) used for closing line value.
The key stays in the environment and is not printed. Stop when less than 20%
of the quota is left.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nba_sim.settings import load_settings

API = "https://api.the-odds-api.com/v4/sports/basketball_nba"
PROP_MARKETS = {
    "player_points": "pts",
    "player_rebounds": "reb",
    "player_assists": "ast",
}
ABBR = {
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
    "Los Angeles Clippers": "LAC",
    "LA Clippers": "LAC",
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


def _key() -> str:
    settings = load_settings()
    del settings
    value = os.environ.get("ODDS_API_KEY", "").strip()
    if not value:
        raise SystemExit("ODDS_API_KEY is missing")
    return value


def _get(path: str, params: dict, key: str) -> tuple[object, dict]:
    params = dict(params)
    params["apiKey"] = key
    url = API + path + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url)
    try:
        response = urllib.request.urlopen(request, timeout=60)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"odds request failed status={exc.code}") from None
    with response:
        quota = {
            "remaining": int(response.headers.get("x-requests-remaining") or 0),
            "used": int(response.headers.get("x-requests-used") or 0),
            "last": int(response.headers.get("x-requests-last") or 0),
        }
        body = json.loads(response.read().decode("utf-8"))
    return body, quota


def _room(quota: dict) -> float:
    total = quota["remaining"] + quota["used"]
    if total <= 0:
        return 1.0
    return quota["remaining"] / total


def _report(label: str, quota: dict) -> None:
    print(
        f"quota {label} remaining={quota['remaining']} used={quota['used']} "
        f"last={quota['last']} left={100 * _room(quota):.1f}%",
        flush=True,
    )


def _props_for_event(event: dict, key: str) -> tuple[list[dict], dict]:
    body, quota = _get(
        f"/events/{event['id']}/odds",
        {
            "regions": "us",
            "markets": ",".join(PROP_MARKETS),
            "oddsFormat": "american",
        },
        key,
    )
    players = []
    for book in body.get("bookmakers") or []:
        if book.get("key") != "draftkings":
            continue
        for market in book.get("markets") or []:
            stat = PROP_MARKETS.get(market.get("key"))
            if stat is None:
                continue
            by_player: dict[str, dict] = {}
            for outcome in market.get("outcomes") or []:
                name = outcome.get("description") or outcome.get("name")
                side = str(outcome.get("name") or "").lower()
                if not name or outcome.get("point") is None:
                    continue
                row = by_player.setdefault(
                    name,
                    {"player": name, "market": stat, "point": float(outcome["point"])},
                )
                if side in {"over", "under"}:
                    row[side] = int(outcome.get("price") or 0)
            for row in by_player.values():
                if row.get("over") is not None and row.get("under") is not None:
                    players.append(row)
    return players, quota


def pull(date: str, *, close: bool, event_ids: set[str] | None = None) -> dict:
    settings = load_settings()
    key = _key()
    events, quota = _get(
        "/odds",
        {"regions": "us", "markets": "h2h,spreads,totals", "oddsFormat": "american"},
        key,
    )
    _report("lines", quota)
    if _room(quota) < 0.20:
        raise SystemExit("quota below 20%, stopped before props")
    wanted = set()
    for row in __import__("nba_sim.storage", fromlist=["read_rows"]).read_rows(
        settings, "schedule", settings.current_season
    ):
        if str(row.get("game_date"))[:10] == date:
            wanted.add((row["away_abbr"], row["home_abbr"]))
    matched = []
    for event in events:
        away = ABBR.get(event.get("away_team"))
        home = ABBR.get(event.get("home_team"))
        if (away, home) not in wanted:
            continue
        if event_ids is not None and event.get("id") not in event_ids:
            continue
        books = [book.get("key") for book in event.get("bookmakers") or []]
        matched.append(
            {
                "event_id": event.get("id"),
                "away": away,
                "home": home,
                "commence_time": event.get("commence_time"),
                "draftkings": "draftkings" in books,
            }
        )
    props = []
    stopped = None
    for event in matched:
        if _room(quota) < 0.20:
            stopped = "quota"
            break
        full = next(item for item in events if item.get("id") == event["event_id"])
        players, quota = _props_for_event(full, key)
        _report(f"props {event['away']}@{event['home']}", quota)
        props.append(
            {
                "event_id": event["event_id"],
                "away": event["away"],
                "home": event["home"],
                "commence_time": event["commence_time"],
                "book": "draftkings",
                "players": players,
            }
        )
    payload = {
        "pulled_at": datetime.now(timezone.utc).isoformat(),
        "kind": "close" if close else "open",
        "draftkings": any(item["draftkings"] for item in matched),
        "book_used": "draftkings",
        "quota": quota,
        "matched": len(props),
        "props_stopped": stopped,
        "props": props,
    }
    folder = Path(settings.data_dir) / "odds_cache" / date
    folder.mkdir(parents=True, exist_ok=True)
    name = "close_summary.json" if close else "summary.json"
    target = folder / name
    if close and target.exists() and event_ids is not None:
        previous = json.loads(target.read_text(encoding="utf-8"))
        kept = [block for block in previous.get("props") or [] if block.get("event_id") not in event_ids]
        payload["props"] = kept + props
        payload["matched"] = len(payload["props"])
    target.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    print(f"wrote {target} games={payload['matched']} stopped={stopped}", flush=True)
    return payload


def close_before_tip(date: str) -> None:
    """Pull each tip cluster 30 minutes before the first game in it."""
    settings = load_settings()
    open_path = Path(settings.data_dir) / "odds_cache" / date / "summary.json"
    if not open_path.exists():
        pull(date, close=False)
    board = json.loads(open_path.read_text(encoding="utf-8"))
    clusters: list[list[dict]] = []
    ordered = sorted(board.get("props") or [], key=lambda row: row.get("commence_time") or "")
    for block in ordered:
        stamp = block.get("commence_time")
        if not stamp:
            continue
        tip = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if clusters and tip - datetime.fromisoformat(
            clusters[-1][0]["commence_time"].replace("Z", "+00:00")
        ) <= timedelta(minutes=20):
            clusters[-1].append(block)
        else:
            clusters.append([block])
    for cluster in clusters:
        tip = datetime.fromisoformat(cluster[0]["commence_time"].replace("Z", "+00:00"))
        when = tip - timedelta(minutes=30)
        wait = (when - datetime.now(timezone.utc)).total_seconds()
        label = ",".join(f"{row['away']}@{row['home']}" for row in cluster)
        if wait > 0:
            print(f"close {label} sleeps until {when.isoformat()} ({wait/60:.0f} min)", flush=True)
            time.sleep(wait)
        else:
            print(f"close {label} window already open, pulling now", flush=True)
        pull(date, close=True, event_ids={row["event_id"] for row in cluster})


def main() -> None:
    date = "2026-11-17"
    close = False
    wait = False
    args = sys.argv[1:]
    for arg in args:
        if arg == "--close":
            close = True
        elif arg == "--close-before-tip":
            wait = True
        elif arg.startswith("--date="):
            date = arg.split("=", 1)[1]
    if wait:
        close_before_tip(date)
    else:
        pull(date, close=close)


if __name__ == "__main__":
    main()
