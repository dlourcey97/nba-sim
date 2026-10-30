"""Fetch compact BBall Index tables from the leaderboard's JSON endpoint.

The leaderboard tool (shinyapps) fills its table from a DataTables
``session/.../dataobj/query_table`` POST. That response is JSON rows, the same
payload the page's table requests. This module does not parse standings out of
HTML and does not store a password.

Auth is only the ``BBALL_INDEX_COOKIE`` value in ``.env`` (installed in the
cookie jar, never logged). 2024-25 and 2025-26 are final and fetched once.
2026-27 is fetched at most once per ``bball_index_fetch_interval_days``.

On failure the last good parquet is left in place. Nothing here raises into
``daily.py``.

Credit: Basketball Index (bball-index.com). Personal use only — do not
redistribute these tables.
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import unicodedata
import random
import re
import shutil
import string
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode

import pyarrow as pa
import pyarrow.parquet as pq

from nba_sim.settings import Settings

LogFn = Callable[[str], None]

USER_AGENT = (
    "nba-sim/1.0 (personal NBA research; BBall Index membership tools; "
    "one request at a time)"
)
APP_URL = "https://bball-index.shinyapps.io/SoulYOLO3Lose/"
SOURCE_LABEL = "bball-index.com leaderboard dataobj/query_table"
# Defaults the leaderboard itself sends before Run Query. Missing sliders make that click fail.
DEFAULT_TEAMS = (
    "ATL", "BOS", "BRK", "CHI", "CHO", "CLE", "DAL", "DEN", "DET", "GSW",
    "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NOP", "NYK",
    "OKC", "ORL", "PHI", "PHO", "POR", "SAC", "SAS", "TOR", "UTA", "WAS",
)

# End-year on the tool's season slider. 2025 → season label 2024-25.
FINAL_SEASONS = ("2024-25", "2025-26")
WEEKLY_SEASON = "2026-27"
SEASON_END_YEAR = {"2024-25": 2025, "2025-26": 2026, "2026-27": 2027}

# Columns the leaderboard always returns, in order, before the requested metrics.
# Position is a metric ("Offense Position *"), not one of these columns.
IDENTITY = (
    "row_number",
    "season",
    "player_name",
    "age",
    "team_abbr",
    "minutes",
    "rotation_role",
    "offensive_role",
    "defensive_role",
)
IDENTITY_LEN = len(IDENTITY)
IDENTITY_HEADERS = (
    " ",
    "Season",
    "Player",
    "Age",
    "Team(s)",
    "Minutes",
    "Rotation Role",
    "Offensive Role",
    "Defensive Role",
)
# These metric labels come back as text (PG/SG/SF/PF/C), not numbers.
STRING_METRICS = {
    "Offense Position *": "offense_position",
    "Defensive Position *": "defensive_position",
    "Advanced Position *": "advanced_position",
}

# Metric labels as the tool's select lists them (star marks a component stat).
# At most 10 per query — the leaderboard drops anything past that.
DATASETS: dict[str, tuple[str, ...]] = {
    "roles": (
        "True Usage *",
        "On-Ball Action Share *",
        "Offensive Involvement Rate *",
        "Minutes Per Game *",
        "% of Time as Guard *",
        "% of Time as Wing *",
        "% of Time as Big *",
        "Offense Position *",
    ),
    "defense": (
        "Perimeter Isolation Defense *",
        "Ball Screen Navigation *",
        "Off-Ball Chaser Defense *",
        "Pickpocket Rating *",
        "Passing Lane Defense *",
        "Rim Protection *",
        "Help Defense Talent *",
        "Post Defense *",
        "Rim dFG% vs Expected *",
        "Overall Screener Defense *",
    ),
    "play_types": (
        "Stable Isolation PPP *",
        "Stable P&R Ball Handler PPP *",
        "Stable P&R Roll Man PPP *",
        "Stable Post Up PPP *",
        "Stable Spot Up PPP *",
        "Stable Handoff PPP *",
        "Stable Cut PPP *",
        "Stable Off-Ball Screen PPP *",
        "Stable Transition PPP *",
        "Stable Putbacks PPP *",
    ),
    "matchup": (
        "Matchup Difficulty *",
        "Defensive Positional Versatility *",
        "Defensive Role Versatility *",
        "Primary Defender Involvement Rate *",
        "% of Time Guarding Point Guards *",
        "% of Time Guarding Shooting Guards *",
        "% of Time Guarding Small Forwards *",
        "% of Time Guarding Power Forwards *",
        "% of Time Guarding Centers *",
    ),
    "playmaking": (
        "Playmaking Talent *",
        "Passing Creation Volume *",
        "Passing Creation Quality *",
        "Passing Efficiency *",
        "Box Creation *",
        "On-Ball Gravity *",
        "Assist Points Per 75 Possessions *",
        "P&R Creation Rate *",
    ),
    "rebounding": (
        "Offensive Rebounding Talent *",
        "Defensive Rebounding Talent *",
        "Offensive Rebounding Chances Per 75 Possessions *",
        "Defensive Rebounding Chances Per 75 Possessions *",
        "Offensive Rebounding Conversion Skill *",
        "Defensive Rebounding Conversion Skill *",
        "Adjusted Offensive Rebounding Success Rate *",
        "Adjusted Defensive Rebounding Success Rate *",
    ),
}

# Columns used by the sim. The rest stay in parquet for later checks.
PERIMETER_COLUMNS = (
    "perimeter_isolation_defense",
    "ball_screen_navigation",
    "off_ball_chaser_defense",
    "pickpocket_rating",
    "passing_lane_defense",
)
INTERIOR_COLUMNS = (
    "rim_protection",
    "help_defense_talent",
    "post_defense",
    "rim_dfg_vs_expected",
    "overall_screener_defense",
)

TEAM_ABBR_ALIASES = {"BRK": "BKN", "CHO": "CHA", "PHO": "PHX", "GS": "GSW"}
_SEASON_LABEL = re.compile(r"^\d{4}-\d{2}$")
_DATAOBJ_RE = re.compile(
    r"session/[^/?#\"'\\]+/dataobj/[^/?#\"'\\]+\?w=[^&\"'\\]+&nonce=[^&\"'\\]+"
)
_LOGIN_MARKERS = (
    "wp-login.php",
    "access-restricted",
    "woocommerce-login",
    'name="pwd"',
    "member login",
)

OFFENSIVE_ROLES = (
    "Shot Creator",
    "Slasher",
    "Primary Ball Handler",
    "Secondary Ball Handler",
    "Off Screen Shooter",
    "Movement Shooter",
    "Stationary Shooter",
    "Athletic Finisher",
    "Versatile Big",
    "Post Scorer",
    "Stretch Big",
    "Roll + Cut Big",
    "Low Minute",
)
DEFENSIVE_ROLES = (
    "Point of Attack",
    "Wing Stopper",
    "Chaser",
    "Helper",
    "Low Activity",
    "Mobile Big",
    "Anchor Big",
)
ROTATION_ROLES = (
    "Star",
    "Starter",
    "Key Rotation",
    "Rotation",
    "Garbage Time",
    "Too Few Games",
)
ADVANCED_POSITIONS = (
    "On-Ball Guard",
    "On-Ball Wing",
    "On-Ball Big",
    "Off-Ball Guard",
    "Off-Ball Wing",
    "Off-Ball Big",
    "Low Minute",
)


class BballIndexStop(Exception):
    """401/403/429 or a login wall. Do not retry and do not send another request."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass
class BballFetchStatus:
    fetched: bool
    skipped_fresh: bool
    dataset_ages: dict[str, str]
    warnings: tuple[str, ...]


@dataclass
class _HttpResponse:
    status: int
    body: bytes
    content_type: str
    url: str


def metric_column(label: str) -> str:
    """Stable snake_case column for a leaderboard metric label."""
    text = label.replace("*", " ").replace("%", " pct ").replace("&", " and ")
    chars = [ch.lower() if ch.isalnum() else "_" for ch in text]
    parts = [part for part in "".join(chars).split("_") if part]
    return "_".join(parts)


def season_label_from_end_year(year: int) -> str:
    start = int(year) - 1
    return f"{start}-{str(year)[-2:]}"


def format_shiny_id(msg_id: int) -> str:
    return format(int(msg_id), "X")


def frame_shiny_message(msg_id: int, payload: str, *, channel: str = "0") -> str:
    """Robust-connection id + multiplex frame the leaderboard socket sends."""
    return f"{format_shiny_id(msg_id)}#{channel}|m|{payload}"


def _sockjs_is_open(text: str) -> bool:
    """True once SockJS has sent the open frame.

    xhr_streaming writes a 2048-byte ``h`` prelude before the ``o`` frame, so
    the open marker is not at the start of the buffer.
    """
    return re.search(r"(?:^|\n)o(?:\n|$)", text) is not None


def external_dir(settings: Settings) -> Path:
    path = settings.data_dir / "external" / "bballindex"
    path.mkdir(parents=True, exist_ok=True)
    return path


def dataset_paths(settings: Settings, dataset: str, season: str) -> tuple[Path, Path]:
    root = external_dir(settings)
    stem = f"{dataset}_{season}"
    return root / f"{stem}.parquet", root / f"{stem}.prev.parquet"


def meta_path(settings: Settings) -> Path:
    return external_dir(settings) / "bball_index_meta.parquet"


def cookie_from_env() -> str:
    """Cookie header value. Empty when unset. Never log the return value."""
    raw = os.environ.get("BBALL_INDEX_COOKIE", "").strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {"'", '"'}:
        raw = raw[1:-1].strip()
    if raw and "=" not in raw:
        return ""
    return raw


def redact(text: str, secret: str) -> str:
    if not secret or not text:
        return text
    cleaned = text.replace(secret, "[redacted]")
    # Also drop a Cookie header if a library stringified the request.
    return re.sub(r"(?i)(cookie\s*[:=]\s*)[^;\s]+", r"\1[redacted]", cleaned)


def _sleep_between(rng: random.Random, sleep: Callable[[float], None]) -> None:
    sleep(rng.uniform(3.0, 5.0))


def _is_login_page(body: bytes, content_type: str) -> bool:
    ctype = (content_type or "").lower()
    if "json" in ctype or body[:1] in {b"{", b"[", b"o", b"a", b"h"}:
        return False
    if "html" not in ctype and body[:1] != b"<":
        return False
    text = body[:8000].decode("utf-8", "replace").lower()
    if "shiny-bound-input" in text or "dataobj" in text:
        return False
    return any(marker in text for marker in _LOGIN_MARKERS)


def install_env_cookie(jar: http.cookiejar.CookieJar, secret: str) -> None:
    """Add the env cookie to the jar. Does not replace the tool's session cookie."""
    if not secret:
        return
    for part in secret.split(";"):
        part = part.strip()
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name:
            continue
        for domain in (".bball-index.com", ".shinyapps.io"):
            jar.set_cookie(
                http.cookiejar.Cookie(
                    version=0,
                    name=name,
                    value=value,
                    port=None,
                    port_specified=False,
                    domain=domain,
                    domain_specified=True,
                    domain_initial_dot=True,
                    path="/",
                    path_specified=True,
                    secure=True,
                    expires=None,
                    discard=True,
                    comment=None,
                    comment_url=None,
                    rest={},
                )
            )


def _request(
    opener: urllib.request.OpenerDirector,
    url: str,
    *,
    data: bytes | None,
    headers: dict[str, str],
    timeout: float,
    method: str | None = None,
    secret: str,
) -> _HttpResponse:
    """One HTTP call. 401/403/429 and login pages raise BballIndexStop (no retry)."""
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with opener.open(req, timeout=timeout) as resp:
            status = int(getattr(resp, "status", None) or resp.getcode() or 200)
            body = resp.read()
            ctype = resp.headers.get("Content-Type", "")
            final = resp.geturl()
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        body = exc.read() if exc.fp is not None else b""
        ctype = exc.headers.get("Content-Type", "") if exc.headers else ""
        final = url
        if status in {401, 403, 429}:
            raise BballIndexStop(
                f"BBall Index HTTP {status} at {url.split('?', 1)[0]}; stopped, not retried"
            ) from None
        if status == 202:
            return _HttpResponse(status=202, body=body, content_type=ctype, url=final)
        snippet = re.sub(r"[0-9a-fA-F]{8,}", "X", body[:160].decode("utf-8", "replace"))
        snippet = " ".join(snippet.split())
        raise urllib.error.URLError(f"HTTP {status}: {snippet[:120]}") from None
    except BballIndexStop:
        raise
    except Exception as exc:
        raise urllib.error.URLError(redact(str(exc), secret)) from None
    if status in {401, 403, 429}:
        raise BballIndexStop(
            f"BBall Index HTTP {status} at {url.split('?', 1)[0]}; stopped, not retried"
        )
    if _is_login_page(body, ctype):
        raise BballIndexStop(
            "BBall Index returned a login page; stopped, not retried. "
            "Refresh BBALL_INDEX_COOKIE."
        )
    return _HttpResponse(status=status, body=body, content_type=ctype, url=final)


def _request_retry(
    opener: urllib.request.OpenerDirector,
    url: str,
    *,
    data: bytes | None,
    headers: dict[str, str],
    timeout: float,
    secret: str,
    log: LogFn,
    sleep: Callable[[float], None],
    max_tries: int = 3,
) -> _HttpResponse:
    delay = 2.0
    last: Exception | None = None
    for attempt in range(max_tries):
        try:
            resp = _request(
                opener, url, data=data, headers=headers, timeout=timeout, secret=secret
            )
            if resp.status == 202 and attempt + 1 < max_tries:
                log("bball index worker still starting (HTTP 202); backing off")
                sleep(delay)
                delay *= 2
                continue
            return resp
        except BballIndexStop:
            raise
        except Exception as exc:  # noqa: BLE001 — retry transient errors only
            if "HTTP 404" in str(exc):
                raise
            last = exc
            if attempt + 1 >= max_tries:
                break
            log(f"bball index request failed ({redact(str(exc), secret)}); retry in {delay:.0f}s")
            sleep(delay)
            delay *= 2
    assert last is not None
    raise last


def _base_headers() -> dict[str, str]:
    return {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
    }


class LeaderboardClient:
    """One Shiny session. Speaks the socket only to reach the JSON table endpoint."""

    def __init__(
        self,
        *,
        opener: urllib.request.OpenerDirector,
        secret: str,
        timeout: float,
        log: LogFn,
        sleep: Callable[[float], None],
        rng: random.Random,
    ) -> None:
        self.opener = opener
        self.secret = secret
        self.timeout = timeout
        self.log = log
        self.sleep = sleep
        self.rng = rng
        self.msg_id = 0
        self.worker = ""
        self.year_max = 2026
        self._stream_text = ""
        self._send_url = ""
        self._poll_url = ""
        self._app_root = APP_URL.rstrip("/")
        self._action = 0
        self._dataobj_url = ""
        self._close_reason = ""
        self._acked_through = 0
        self.filters: dict[str, list[str]] = {}

    def open(self) -> None:
        headers = _base_headers()
        page = _request_retry(
            self.opener,
            self._app_root + "/",
            data=None,
            headers=headers,
            timeout=self.timeout,
            secret=self.secret,
            log=self.log,
            sleep=self.sleep,
        )
        html = page.body.decode("utf-8", "replace")
        worker = _parse_worker(html)
        if not worker:
            raise ValueError("leaderboard shell had no worker id")
        self.worker = worker
        self.filters = _filter_inputs(html)
        year_max = _parse_year_max(html)
        if year_max:
            self.year_max = year_max

    def _begin_session(self, year: int, metrics: list[str]) -> None:
        """One short SockJS session whose init already requests this table."""
        self._stream_text = ""
        self._dataobj_url = ""
        self._close_reason = ""
        self._acked_through = 0
        self.msg_id = 0
        headers = _base_headers()
        _sleep_between(self.rng, self.sleep)
        token_resp = _request_retry(
            self.opener,
            self._app_root + "/__token__",
            data=None,
            headers={**headers, "Accept": "text/plain"},
            timeout=self.timeout,
            secret=self.secret,
            log=self.log,
            sleep=self.sleep,
        )
        token = token_resp.body.decode("utf-8", "replace").strip()
        if not re.fullmatch(r"[0-9a-fA-F]+", token):
            raise ValueError("leaderboard token was not a hex string")
        robust = "".join(self.rng.choice(string.ascii_letters + string.digits) for _ in range(18))
        server = f"{self.rng.randint(0, 999):03d}"
        session = "".join(self.rng.choice(string.ascii_lowercase + string.digits) for _ in range(8))
        sock_root = (
            f"{self._app_root}/__sockjs__/n={robust}/t={token}/w={self.worker}/s=0/{server}/{session}"
        )
        self._send_url = sock_root + "/xhr_send"
        self._poll_url = sock_root + "/xhr"
        # One SockJS session, one request at a time. The 3–5s gap is between the
        # page, the token, and each table JSON POST. Long-polls are not given
        # that gap: a multi-minute pause makes the server close the session.
        _sleep_between(self.rng, self.sleep)
        if not self._poll_once() or not _sockjs_is_open(self._stream_text):
            raise ValueError("leaderboard socket did not open")
        # Filters and metrics go in the first message. The Run Query click is a
        # later message: sending it in this burst closes the socket.
        # Metric is sent after the select list arrives. Putting it in this first
        # message, before those choices exist, makes Run Query fail.
        init = {
            **_query_inputs(year, [], self.filters),
            ".clientdata_output_query_table_hidden": False,
            ".clientdata_pixelratio": 1,
            ".clientdata_url_protocol": "https:",
            ".clientdata_url_hostname": "bball-index.shinyapps.io",
            ".clientdata_url_port": "",
            ".clientdata_url_pathname": "/SoulYOLO3Lose/",
            ".clientdata_allowDataUriScheme": True,
        }
        open_frame = f"{format_shiny_id(self.msg_id)}#0|o|"
        self.msg_id += 1
        init_frame = frame_shiny_message(
            self.msg_id, json.dumps({"method": "init", "data": init}, separators=(",", ":"))
        )
        self.msg_id += 1
        self._send_frames([open_frame], pace=False)
        self._send_frames([init_frame], pace=False)

    def close(self) -> None:
        return None

    def _shiny_update(self, data: dict[str, Any]) -> None:
        frame = frame_shiny_message(
            self.msg_id, json.dumps({"method": "update", "data": data}, separators=(",", ":"))
        )
        self.msg_id += 1
        self._send_frames([frame], pace=False)

    def query(self, year: int, metrics: list[str]) -> list[list[Any]]:
        if year > self.year_max:
            raise ValueError(f"season end-year {year} is past the tool max {self.year_max}")
        chosen = list(metrics)[:10]
        self._begin_session(year, chosen)
        # The page shell arrives before the table. Run Query is make_table:shiny.action.
        for index in range(6):
            if len(self._stream_text) > 50_000:
                break
            if not self._poll_once(timeout=20.0 if index == 0 else 8.0):
                break
            self._ack()
        self._shiny_update(_query_inputs(year, chosen, self.filters))
        # One poll acknowledges the inputs. A second, empty long-poll drops the session.
        self._poll_once(timeout=20.0)
        self._ack()
        if self._close_reason:
            raise ValueError(f"leaderboard socket closed ({self._close_reason})")
        mark = len(self._stream_text)
        self._shiny_update({"make_table:shiny.action": 1})
        for index in range(4):
            rel = _extract_dataobj_path(self._stream_text[mark:])
            if rel:
                self._dataobj_url = _dataobj_absolute(self._app_root, rel, self.worker)
                break
            if self._close_reason:
                break
            ok = self._poll_once(timeout=45.0)
            self._ack()
            fresh = _unescape_transport(self._stream_text[mark:])
            if "An error has occurred" in fresh:
                raise ValueError("leaderboard query failed on the server")
            if not ok and "recalculating" not in fresh and "progress" not in fresh:
                break
        rel = _extract_dataobj_path(self._stream_text)
        if rel:
            self._dataobj_url = _dataobj_absolute(self._app_root, rel, self.worker)
        if not self._dataobj_url:
            if self._close_reason:
                raise ValueError(f"leaderboard socket closed ({self._close_reason})")
            raise ValueError("leaderboard did not return a query_table JSON url")
        url = self._dataobj_url
        body = _datatables_body(_table_column_names(chosen))
        headers = _base_headers()
        # Shiny matches this media type exactly. A charset parameter makes the
        # data-object handler see an empty body and return HTTP 500.
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["Accept"] = "application/json"
        headers["X-Requested-With"] = "XMLHttpRequest"
        headers["Referer"] = self._app_root + "/"
        try:
            resp = _request_retry(
                self.opener,
                url,
                data=body,
                headers=headers,
                timeout=max(self.timeout, 120.0),
                secret=self.secret,
                log=self.log,
                sleep=self.sleep,
                max_tries=1,
            )
        except urllib.error.URLError as exc:
            raise ValueError(f"query_table POST failed ({exc}) at {_redact_url(url)}") from None
        try:
            payload = json.loads(resp.body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("query_table response was not JSON") from exc
        rows = payload.get("data")
        if not isinstance(rows, list) or not rows:
            total = payload.get("recordsTotal")
            filtered = payload.get("recordsFiltered")
            err = payload.get("error")
            raise ValueError(
                f"query_table JSON had no data rows (total={total}, filtered={filtered}, error={err})"
            )
        return rows

    def _ack(self) -> None:
        """ACK robust frames so the server keeps the session open until the JSON POST."""
        ids = [
            int(item, 16)
            for item in re.findall(r'(?:a\["|",")([0-9A-F]{1,5})#0\|', self._stream_text)
        ]
        if not ids:
            return
        nxt = max(ids) + 1
        if nxt <= self._acked_through:
            return
        self._acked_through = nxt
        try:
            self._send_frames([f"ACK {format_shiny_id(nxt)}"], pace=False)
        except BballIndexStop:
            raise
        except Exception:
            return

    def _send_frames(self, frames: list[str], *, pace: bool) -> None:
        if pace:
            _sleep_between(self.rng, self.sleep)
        raw = json.dumps(frames).encode("utf-8")
        headers = _base_headers()
        headers["Content-Type"] = "text/plain;charset=UTF-8"
        try:
            _request_retry(
                self.opener,
                self._send_url,
                data=raw,
                headers=headers,
                timeout=self.timeout,
                secret=self.secret,
                log=self.log,
                sleep=self.sleep,
                max_tries=2,
            )
        except urllib.error.URLError as exc:
            raise ValueError(f"socket send failed ({exc})") from None

    def _poll_once(self, *, timeout: float = 15.0) -> bool:
        """Read one SockJS xhr batch. A quiet long-poll timeout means the queue is empty."""
        headers = _base_headers()
        headers["Content-Type"] = "text/plain;charset=UTF-8"
        try:
            resp = _request(
                self.opener,
                self._poll_url,
                data=b"",
                headers=headers,
                timeout=timeout,
                secret=self.secret,
            )
        except urllib.error.URLError as exc:
            if "timed out" in str(exc).lower():
                return False
            raise
        chunk = resp.body.decode("utf-8", "replace").replace("\\/", "/")
        self._stream_text += chunk
        if chunk.startswith("c"):
            self._close_reason = re.sub(r"[0-9A-Za-z]{12,}", "[id]", chunk[:80])
            return False
        if len(self._stream_text) > 4_000_000:
            self._stream_text = self._stream_text[-1_000_000:]
        return bool(chunk.strip())

    def _drain(self, max_polls: int) -> None:
        """Read queued socket messages, then stop when a long-poll comes back empty."""
        for index in range(max_polls):
            if not self._poll_once(timeout=20.0 if index == 0 else 8.0):
                return

def _redacted_dataobj_hint(text: str) -> str:
    index = -1
    for needle in ("dataobj/", "dataobj", "nonce="):
        index = text.find(needle)
        if index >= 0:
            break
    if index < 0:
        index = text.find("query_table")
    raw = text[max(0, index - 40) : index + 100]
    raw = re.sub(r"[0-9A-Za-z]{6,}", "[id]", raw)
    return raw.replace("\n", " ")[:160]


def _redact_url(url: str) -> str:
    safe = re.sub(r"nonce=[^&\s]+", "nonce=[redacted]", url)
    return re.sub(r"[0-9a-fA-F]{8,}", "[id]", safe)


def _dataobj_absolute(app_root: str, rel: str, worker: str = "") -> str:
    """Join the DataTables path onto the worker that owns the session."""
    if rel.startswith("http://") or rel.startswith("https://"):
        return rel
    path = rel.lstrip("/")
    path = re.sub(r"^_w_[0-9a-fA-F]+/", "", path)
    root = app_root.rstrip("/")
    if worker:
        return f"{root}/_w_{worker}/{path}"
    return f"{root}/{path}"


def _unescape_transport(text: str) -> str:
    """Collapse SockJS/JSON escaping until the table URL is plain text."""
    previous = None
    while previous != text:
        previous = text
        text = text.replace("\\\\", "\\").replace("\\/", "/").replace("\\&", "&").replace("&amp;", "&")
        text = re.sub(r"\\u([0-9a-fA-F]{4})", lambda match: chr(int(match.group(1), 16)), text)
    return text


def _extract_dataobj_path(text: str) -> str:
    """Last DataTables JSON path in a SockJS payload, or ''."""
    cleaned = _unescape_transport(text)
    found = [match.group(0) for match in _DATAOBJ_RE.finditer(cleaned)]
    marker = "/dataobj/"
    start_at = 0
    while True:
        index = cleaned.find(marker, start_at)
        if index < 0:
            break
        start = cleaned.rfind("session/", 0, index)
        nonce = cleaned.find("nonce=", index)
        if start >= 0 and nonce > index and "?w=" in cleaned[index:nonce]:
            end = nonce + len("nonce=")
            while end < len(cleaned) and cleaned[end] not in "\"'\\ <>":
                end += 1
            url = cleaned[start:end].replace("\\", "")
            if "w=" in url and "nonce=" in url and url not in found:
                found.append(url)
        start_at = index + len(marker)
    if not found:
        return ""

    def _rank(url: str) -> tuple[int, str]:
        name = url.split("/dataobj/", 1)[1].split("?", 1)[0]
        if name == "query_table":
            return (0, name)
        return (1, name)

    found.sort(key=_rank)
    best = found[0]
    name = best.split("/dataobj/", 1)[1].split("?", 1)[0]
    if name != "query_table":
        return ""
    return best


def _parse_worker(html: str) -> str:
    match = re.search(r"_w_([0-9a-fA-F]+)", html)
    return match.group(1) if match else ""


def _parse_year_max(html: str) -> int | None:
    tag = re.search(r'id="Years"[^>]*>', html)
    if not tag:
        return None
    found = re.search(r'data-max="(\d+)"', tag.group(0))
    if not found:
        return None
    return int(found.group(1))


def _query_inputs(year: int, metrics: list[str], filters: dict[str, list[str]]) -> dict[str, Any]:
    """Input values the leaderboard sends, aside from the Run Query click."""
    data: dict[str, Any] = {
        "Years": [year, year],
        "Minutes": [1, 3125],
        "Display": "Values",
        "FilterAB": "Custom",
        "Height": [67, 90],
        "Weight": [0, 360],
        "Age": [19, 43],
        "Experience": [1, 24],
        "Hand": ["Left", "Right"],
        "Team": list(DEFAULT_TEAMS),
        "Player": [],
        "filters_main": False,
        "Metric_filter": ["Minutes Per Game *"],
        "Type": "Percentiles",
        "minutes_min": [0, 3125],
        "mf_number:sw.numericRange": [0, 43.62],
        **filters,
    }
    if metrics:
        data["Metric"] = list(metrics)[:10]
    return data


def _metric_header(label: str) -> str:
    return re.sub(r"\s*\*$", "", label).strip()


def _ordered_metrics(metrics: list[str] | tuple[str, ...]) -> list[str]:
    """String metrics are rendered first. Only numeric metrics get a percentile column."""
    strings = [label for label in metrics if label in STRING_METRICS]
    numbers = [label for label in metrics if label not in STRING_METRICS]
    return [*strings, *numbers]


def _table_column_names(metrics: list[str]) -> list[str]:
    ordered = _ordered_metrics(metrics)
    numbers = [_metric_header(label) for label in ordered if label not in STRING_METRICS]
    headers = [_metric_header(label) for label in ordered]
    return [*IDENTITY_HEADERS, *headers, *[f"{label}_percentile" for label in numbers]]


def _filter_inputs(html: str) -> dict[str, list[str]]:
    """Selected filter values from the leaderboard shell. Defensive role omits Low Minute."""
    found: dict[str, list[str]] = {}
    for name in ("Archetype", "DefensiveRoles", "RotationRoles", "AdvancedPosition"):
        match = re.search(rf'<select[^>]*id="{name}"[^>]*>(.*?)</select>', html, re.S)
        if not match:
            continue
        values = re.findall(r'<option[^>]*value="([^"]*)"', match.group(1))
        if name == "DefensiveRoles":
            values = [value for value in values if value != "Low Minute"]
        if values:
            found[name] = values
    return found


def _datatables_body(column_names: list[str]) -> bytes:
    parts: dict[str, str] = {
        "draw": "1",
        "start": "0",
        "length": "-1",
        "search[value]": "",
        "search[regex]": "false",
        "escape": "false",
    }
    for index, name in enumerate(column_names):
        prefix = f"columns[{index}]"
        parts[f"{prefix}[data]"] = str(index)
        parts[f"{prefix}[name]"] = name
        parts[f"{prefix}[searchable]"] = "true"
        parts[f"{prefix}[orderable]"] = "false" if index == 0 else "true"
        parts[f"{prefix}[search][value]"] = ""
        parts[f"{prefix}[search][regex]"] = "false"
    parts["order[0][column]"] = "1"
    parts["order[0][dir]"] = "asc"
    return urlencode(parts).encode("utf-8")


def parse_table_rows(
    raw_rows: list[list[Any]],
    metrics: tuple[str, ...],
    *,
    expected_season: str,
) -> list[dict[str, Any]]:
    """Turn leaderboard JSON rows into compact dicts. Raises if the shape changed."""
    columns = [metric_column(label) for label in metrics]
    parsed: list[dict[str, Any]] = []
    for raw in raw_rows:
        if not isinstance(raw, list) or len(raw) < IDENTITY_LEN + len(columns):
            raise ValueError(
                f"leaderboard row width {len(raw) if isinstance(raw, list) else type(raw)} "
                f"< {IDENTITY_LEN + len(columns)}"
            )
        season = str(raw[1] or "")
        name = str(raw[2] or "").strip()
        if not _SEASON_LABEL.match(season) or not name:
            raise ValueError("leaderboard identity columns moved (season/player)")
        if season != expected_season:
            continue
        row: dict[str, Any] = {
            "player_id": None,
            "player_name": name,
            "season": season,
            "age": _int_or_none(raw[3]),
            "team_abbr": str(raw[4] or ""),
            "minutes": _float_or_none(raw[5]),
            "rotation_role": str(raw[6] or ""),
            "offensive_role": str(raw[7] or ""),
            "defensive_role": str(raw[8] or ""),
        }
        ordered = _ordered_metrics(metrics)
        for offset, label in enumerate(ordered):
            cell = raw[IDENTITY_LEN + offset]
            if label in STRING_METRICS:
                row[STRING_METRICS[label]] = str(cell or "").strip()
            else:
                row[metric_column(label)] = _float_or_none(cell)
        parsed.append(row)
    if len(parsed) < 100:
        raise ValueError(
            f"leaderboard returned {len(parsed)} {expected_season} rows; expected a full season"
        )
    return parsed


def normalize_player_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", name)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace(".", " ").replace("'", "").replace("-", " ")
    text = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text)
    return " ".join(text.split())


def normalize_team_abbr(abbr: str) -> str:
    token = abbr.strip().upper()
    return TEAM_ABBR_ALIASES.get(token, token)


def attach_player_ids(settings: Settings, rows: list[dict[str, Any]], season: str) -> int:
    """Fill player_id from our game logs. Returns how many rows stayed unmatched."""
    index = _name_index(settings, season)
    unmatched = 0
    for row in rows:
        player_id = _match_player_id(index, str(row.get("player_name") or ""), str(row.get("team_abbr") or ""))
        row["player_id"] = player_id
        if player_id is None:
            unmatched += 1
    return unmatched


def _name_index(settings: Settings, season: str) -> dict[str, list[tuple[int, set[str]]]]:
    from nba_sim.storage import read_rows

    seasons = [season]
    start = int(season.split("-", 1)[0])
    seasons.append(f"{start - 1}-{str(start)[-2:]}")
    seasons.append(f"{start + 1}-{str(start + 2)[-2:]}")
    found: dict[str, dict[int, set[str]]] = {}
    for label in seasons:
        try:
            logs = read_rows(settings, "player_game_logs", label)
        except Exception:
            continue
        for log in logs:
            name = normalize_player_name(str(log.get("player_name") or ""))
            if not name:
                continue
            pid = _int_or_none(log.get("player_id"))
            if pid is None:
                continue
            team = normalize_team_abbr(str(log.get("team_abbr") or ""))
            bucket = found.setdefault(name, {})
            bucket.setdefault(pid, set())
            if team:
                bucket[pid].add(team)
    return {name: [(pid, teams) for pid, teams in ids.items()] for name, ids in found.items()}


def _match_player_id(
    index: dict[str, list[tuple[int, set[str]]]],
    name: str,
    team_field: str,
) -> int | None:
    key = normalize_player_name(name)
    options = index.get(key) or []
    if not options and " " in key:
        # "Nic Claxton" vs "Nicolas Claxton": last name + first initial.
        first, _, last = key.partition(" ")
        # last token is the surname when there are multiple parts
        parts = key.split()
        if len(parts) >= 2:
            surname = parts[-1]
            initial = parts[0][:1]
            options = [
                item
                for cand, items in index.items()
                if cand.split()[-1:] == [surname] and cand[:1] == initial
                for item in items
            ]
    if not options:
        return None
    if len(options) == 1:
        return options[0][0]
    teams = {normalize_team_abbr(part) for part in team_field.split("/") if part.strip()}
    hits = [pid for pid, player_teams in options if teams & player_teams]
    if len(hits) == 1:
        return hits[0]
    return None


def _rows_to_table(rows: list[dict[str, Any]]) -> pa.Table:
    # Stable column order: identity, then metric keys in first-row order.
    keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    normalized = [{key: row.get(key) for key in keys} for row in rows]
    return pa.Table.from_pylist(normalized)


def _atomic_replace(settings: Settings, dataset: str, season: str, table: pa.Table) -> None:
    current, prev = dataset_paths(settings, dataset, season)
    tmp = current.with_suffix(".parquet.tmp")
    pq.write_table(table, tmp, compression="zstd")
    if current.is_file():
        shutil.copy2(current, prev)
    tmp.replace(current)


def refresh_bball_index(
    settings: Settings,
    *,
    log: LogFn = print,
    force: bool = False,
    datasets: tuple[str, ...] | None = None,
    seasons: tuple[str, ...] | None = None,
    sleep: Callable[[float], None] | None = None,
    opener: urllib.request.OpenerDirector | None = None,
    client_factory: Callable[..., LeaderboardClient] | None = None,
) -> BballFetchStatus:
    """Fetch stale BBall Index datasets. Never raises."""
    ctx = settings.config.get("context") or {}
    if not bool(ctx.get("bball_index_enabled", True)):
        log("bball index fetch disabled (context.bball_index_enabled=false)")
        return BballFetchStatus(False, False, _age_report(settings), ())

    sleep_fn = sleep or time.sleep
    rng = random.Random()
    secret = cookie_from_env()
    if not secret:
        log("bball index: BBALL_INDEX_COOKIE is unset; requesting the tool JSON without a cookie")
    wanted = datasets or tuple(DATASETS)
    season_list = seasons or (FINAL_SEASONS + (WEEKLY_SEASON,))
    interval = int(ctx.get("bball_index_fetch_interval_days", 7))
    timeout = float((settings.config.get("http") or {}).get("timeout_seconds", 60))
    now = datetime.now(timezone.utc)
    meta = _read_meta(settings)
    pending: list[tuple[str, str]] = []
    for season in season_list:
        for dataset in wanted:
            if dataset not in DATASETS:
                continue
            if _is_fresh(settings, meta, dataset, season, now=now, interval_days=interval, force=force):
                continue
            pending.append((dataset, season))
    if not pending:
        ages = _age_report(settings, meta=meta, now=now)
        for name, age in ages.items():
            log(f"bball index {name}: {age} (skip fetch)")
        return BballFetchStatus(False, True, ages, ())

    warnings: list[str] = []
    any_ok = False
    if opener is None:
        jar = http.cookiejar.CookieJar()
        install_env_cookie(jar, secret)
        http_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    else:
        http_opener = opener
    factory = client_factory or LeaderboardClient
    client: LeaderboardClient | None = None
    try:
        client = factory(
            opener=http_opener,
            secret=secret,
            timeout=timeout,
            log=lambda message: log(redact(message, secret)),
            sleep=sleep_fn,
            rng=rng,
        )
        client.open()
        for dataset, season in pending:
            year = SEASON_END_YEAR[season]
            if year > client.year_max:
                msg = (
                    f"bball index {dataset} {season}: not published "
                    f"(tool seasons through {client.year_max}); keeping last copy"
                )
                log(msg)
                _stamp_meta(
                    meta,
                    dataset,
                    season,
                    now=now,
                    status="unpublished",
                    row_count=_row_count(settings, dataset, season),
                    error="",
                )
                continue
            try:
                raw = client.query(year, list(DATASETS[dataset]))
                rows = parse_table_rows(raw, DATASETS[dataset], expected_season=season)
                unmatched = attach_player_ids(settings, rows, season)
                _atomic_replace(settings, dataset, season, _rows_to_table(rows))
                _stamp_meta(
                    meta,
                    dataset,
                    season,
                    now=now,
                    status="ok",
                    row_count=len(rows),
                    error="",
                )
                any_ok = True
                log(
                    f"bball index {dataset} {season}: wrote {len(rows)} rows "
                    f"(unmatched_names={unmatched})"
                )
            except BballIndexStop:
                raise
            except Exception as exc:  # noqa: BLE001 — keep last good copy
                msg = (
                    f"bball index {dataset} {season} failed: {redact(str(exc), secret)}; "
                    "keeping last good copy"
                )
                warnings.append(msg)
                log(f"WARNING: {msg}")
                _stamp_meta(
                    meta,
                    dataset,
                    season,
                    now=now,
                    status="failed",
                    row_count=_row_count(settings, dataset, season),
                    error=redact(str(exc), secret)[:240],
                )
    except BballIndexStop as exc:
        msg = redact(str(exc), secret)
        warnings.append(msg)
        log(f"WARNING: {msg}")
    except Exception as exc:  # noqa: BLE001
        msg = f"bball index session failed: {redact(str(exc), secret)}; keeping last good copy"
        warnings.append(msg)
        log(f"WARNING: {msg}")
    finally:
        if client is not None:
            client.close()
        if meta:
            _write_meta(settings, meta)

    ages = _age_report(settings, meta=meta, now=now)
    for name, age in ages.items():
        log(f"bball index {name}: {age}")
    return BballFetchStatus(
        fetched=any_ok,
        skipped_fresh=False,
        dataset_ages=ages,
        warnings=tuple(warnings),
    )


def format_bball_age_line(settings: Settings, *, now: datetime | None = None) -> str:
    ages = _age_report(settings, now=now or datetime.now(timezone.utc))
    if not ages:
        return "bball index: no local copy yet"
    parts = [f"{name} {age}" for name, age in ages.items()]
    return "bball index age: " + "; ".join(parts)


def load_bball_table(settings: Settings, dataset: str, season: str) -> list[dict[str, Any]]:
    """Last good rows for one dataset-season, or [] when nothing is stored."""
    current, prev = dataset_paths(settings, dataset, season)
    for path in (current, prev):
        if not path.is_file():
            continue
        try:
            return pq.read_table(path).to_pylist()
        except Exception:
            continue
    return []


def bball_source_season(settings: Settings, season: str) -> str | None:
    """Season file to use. Backtests use the previous season only.

    The live current season may use its own weekly file when one exists.
    """
    from ingest.rosters import prior_season_label

    prior = prior_season_label(season)
    if season != settings.current_season:
        return prior
    if load_bball_table(settings, "roles", season):
        return season
    return prior


@dataclass
class BballContext:
    """Leakage-safe lookup tables for one projection season."""

    source_season: str
    offense_position: dict[int, str] = field(default_factory=dict)
    # Share of minutes guarding PG, SG, SF, PF, C. Percents, not fractions.
    guard_share: dict[int, tuple[float, float, float, float, float]] = field(default_factory=dict)
    perimeter: dict[int, float] = field(default_factory=dict)
    interior: dict[int, float] = field(default_factory=dict)
    play_ppp: dict[int, dict[str, float]] = field(default_factory=dict)
    league_ppp: dict[str, float] = field(default_factory=dict)


def load_bball_context(settings: Settings, season: str) -> BballContext | None:
    source = bball_source_season(settings, season)
    if not source:
        return None
    ctx = BballContext(source_season=source)
    for row in load_bball_table(settings, "roles", source):
        pid = _int_or_none(row.get("player_id"))
        pos = str(row.get("offense_position") or "").strip().upper()
        if pid is None or pos not in {"PG", "SG", "SF", "PF", "C"}:
            continue
        ctx.offense_position[pid] = pos
    guard_columns = (
        "pct_of_time_guarding_point_guards",
        "pct_of_time_guarding_shooting_guards",
        "pct_of_time_guarding_small_forwards",
        "pct_of_time_guarding_power_forwards",
        "pct_of_time_guarding_centers",
    )
    for row in load_bball_table(settings, "matchup", source):
        pid = _int_or_none(row.get("player_id"))
        if pid is None:
            continue
        shares = [_float_or_none(row.get(column)) or 0.0 for column in guard_columns]
        if sum(shares) <= 0:
            continue
        ctx.guard_share[pid] = (shares[0], shares[1], shares[2], shares[3], shares[4])
    for row in load_bball_table(settings, "defense", source):
        pid = _int_or_none(row.get("player_id"))
        if pid is None:
            continue
        per = _mean_present(row, PERIMETER_COLUMNS)
        interior = _mean_present(row, INTERIOR_COLUMNS)
        if per is not None:
            ctx.perimeter[pid] = per
        if interior is not None:
            ctx.interior[pid] = interior
    sums: dict[str, float] = {}
    counts: dict[str, int] = {}
    ppp_columns = [metric_column(label) for label in DATASETS["play_types"]]
    for row in load_bball_table(settings, "play_types", source):
        pid = _int_or_none(row.get("player_id"))
        if pid is None:
            continue
        values: dict[str, float] = {}
        for column in ppp_columns:
            value = _float_or_none(row.get(column))
            if value is None:
                continue
            values[column] = value
            sums[column] = sums.get(column, 0.0) + value
            counts[column] = counts.get(column, 0) + 1
        if values:
            ctx.play_ppp[pid] = values
    ctx.league_ppp = {
        column: sums[column] / counts[column] for column in sums if counts.get(column)
    }
    if not ctx.offense_position and not ctx.guard_share and not ctx.perimeter and not ctx.play_ppp:
        return None
    return ctx


def _mean_present(row: dict[str, Any], columns: tuple[str, ...]) -> float | None:
    values = [value for column in columns if (value := _float_or_none(row.get(column))) is not None]
    if not values:
        return None
    return float(sum(values) / len(values))


def _is_fresh(
    settings: Settings,
    meta: dict[str, dict[str, Any]],
    dataset: str,
    season: str,
    *,
    now: datetime,
    interval_days: int,
    force: bool,
) -> bool:
    if force:
        return False
    current, prev = dataset_paths(settings, dataset, season)
    have_file = current.is_file() or prev.is_file()
    key = f"{dataset}:{season}"
    row = meta.get(key) or {}
    if season in FINAL_SEASONS and have_file and str(row.get("status") or "ok") == "ok":
        return True
    if season in FINAL_SEASONS and have_file and not row:
        return True
    fetched = str(row.get("fetched_at") or "")
    if not fetched:
        return False
    try:
        stamp = datetime.fromisoformat(fetched.replace("Z", "+00:00"))
    except ValueError:
        return False
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    age_days = (now - stamp).total_seconds() / 86400.0
    if season == WEEKLY_SEASON and age_days < float(interval_days):
        return True
    if season in FINAL_SEASONS and have_file:
        return True
    return False


def _row_count(settings: Settings, dataset: str, season: str) -> int:
    current, prev = dataset_paths(settings, dataset, season)
    path = current if current.is_file() else prev if prev.is_file() else None
    if path is None:
        return 0
    try:
        return pq.read_metadata(path).num_rows
    except Exception:
        return 0


def _stamp_meta(
    meta: dict[str, dict[str, Any]],
    dataset: str,
    season: str,
    *,
    now: datetime,
    status: str,
    row_count: int,
    error: str,
) -> None:
    meta[f"{dataset}:{season}"] = {
        "dataset": dataset,
        "season": season,
        "fetched_at": now.isoformat(),
        "row_count": int(row_count),
        "status": status,
        "last_error": error,
        "source": SOURCE_LABEL,
    }


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
        key = f"{row.get('dataset')}:{row.get('season')}"
        if row.get("dataset") and row.get("season"):
            out[key] = row
    return out


def _write_meta(settings: Settings, meta: dict[str, dict[str, Any]]) -> None:
    rows = []
    for row in meta.values():
        rows.append(
            {
                "dataset": str(row.get("dataset") or ""),
                "season": str(row.get("season") or ""),
                "fetched_at": str(row.get("fetched_at") or ""),
                "row_count": int(row.get("row_count") or 0),
                "status": str(row.get("status") or ""),
                "last_error": str(row.get("last_error") or ""),
                "source": str(row.get("source") or SOURCE_LABEL),
            }
        )
    if not rows:
        return
    path = meta_path(settings)
    tmp = path.with_suffix(".parquet.tmp")
    pq.write_table(pa.Table.from_pylist(rows), tmp, compression="zstd")
    tmp.replace(path)


def _age_report(
    settings: Settings,
    *,
    meta: dict[str, dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> dict[str, str]:
    now = now or datetime.now(timezone.utc)
    meta = meta if meta is not None else _read_meta(settings)
    out: dict[str, str] = {}
    for dataset in DATASETS:
        for season in FINAL_SEASONS + (WEEKLY_SEASON,):
            key = f"{dataset}:{season}"
            current, prev = dataset_paths(settings, dataset, season)
            path = current if current.is_file() else prev if prev.is_file() else None
            row = meta.get(key) or {}
            status = str(row.get("status") or "")
            fetched = str(row.get("fetched_at") or "")
            label = f"{dataset} {season}"
            if path is None and status == "unpublished":
                out[label] = f"not published (checked {fetched[:10]})" if fetched else "not published"
                continue
            if path is None:
                out[label] = "missing"
                continue
            if fetched:
                try:
                    stamp = datetime.fromisoformat(fetched.replace("Z", "+00:00"))
                    if stamp.tzinfo is None:
                        stamp = stamp.replace(tzinfo=timezone.utc)
                    days = int((now - stamp).total_seconds() // 86400)
                    out[label] = f"fetched {fetched[:10]} ({days}d ago, {status or 'ok'})"
                    continue
                except ValueError:
                    pass
            out[label] = f"local file {path.name}"
    return out


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
    if isinstance(value, str):
        value = value.replace(",", "").replace("%", "").strip()
        if not value or value in {"NA", "NaN", "null"}:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
