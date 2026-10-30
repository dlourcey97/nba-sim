"""BBall Index fetch guards and feature math. No live HTTP."""

from __future__ import annotations

import io
import urllib.error
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from ingest.bball_index import (
    BballIndexStop,
    DATASETS,
    _atomic_replace,
    _dataobj_absolute,
    _extract_dataobj_path,
    _request_retry,
    _rows_to_table,
    _sockjs_is_open,
    frame_shiny_message,
    metric_column,
    normalize_player_name,
    parse_table_rows,
    redact,
    refresh_bball_index,
)
from projections.bball_features import apply_opponent_defense_grades, apply_play_type_ppp
from projections.context import apply_opponent_position_defense
from projections.minutes import MinutesProjection
from projections.rates import RateVector


def _settings(tmp_path: Path):
    from nba_sim.settings import Settings

    return Settings(
        repo_root=tmp_path,
        data_dir=tmp_path / "data",
        archive_dir=None,
        max_bytes=2_000_000_000,
        current_season="2026-27",
        config={
            "context": {
                "bball_index_enabled": True,
                "bball_index_fetch_interval_days": 7,
            },
            "http": {"timeout_seconds": 5},
        },
    )


def _http_error(status: int) -> urllib.error.HTTPError:
    headers = EmailMessage()
    return urllib.error.HTTPError(
        "https://bball-index.shinyapps.io/SoulYOLO3Lose/",
        status,
        "no",
        headers,
        io.BytesIO(b"nope"),
    )


class _Opener:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.calls = 0

    def open(self, request, timeout=None):  # noqa: ANN001
        self.calls += 1
        raise self.exc


def test_frame_matches_leaderboard_socket():
    payload = '{"method":"update","data":{"Years":[2025,2025]}}'
    assert frame_shiny_message(11, payload) == f"B#0|m|{payload}"


def test_dataobj_url_uses_app_root():
    rel = "session/abcdef12/dataobj/query_table?w=abc12345&nonce=def67890"
    url = _dataobj_absolute(
        "https://bball-index.shinyapps.io/SoulYOLO3Lose", rel, "abc12345"
    )
    assert url == "https://bball-index.shinyapps.io/SoulYOLO3Lose/_w_abc12345/" + rel
    prefixed = _dataobj_absolute(
        "https://bball-index.shinyapps.io/SoulYOLO3Lose",
        "_w_abc12345/" + rel,
        "abc12345",
    )
    assert prefixed.count("/_w_") == 1


def test_extracts_double_escaped_dataobj_url():
    raw = (
        'a["0#0|m|{\\"url\\":\\"session\\\\/abcdef\\\\/dataobj\\\\/query_table'
        '?w=abc123\\\\u0026nonce=def456\\"}"]'
    )
    found = _extract_dataobj_path(raw)
    assert found == "session/abcdef/dataobj/query_table?w=abc123&nonce=def456"


def test_extracts_quad_escaped_nonhex_dataobj_url():
    raw = (
        "session\\\\\\\\/not-hex_1\\\\\\\\/dataobj\\\\\\\\/query_table"
        "?w=worker\\\\\\\\u0026nonce=n-1"
    )
    found = _extract_dataobj_path(raw)
    assert "session/not-hex_1/dataobj/query_table?" in found
    assert "nonce=n-1" in found
    assert "\\" not in found


def test_sockjs_open_frame_follows_prelude():
    assert not _sockjs_is_open("h" * 2048)
    assert _sockjs_is_open("h" * 2048 + "\no\n")
    assert _sockjs_is_open("o\n")


def test_normalize_player_name_strips_accents():
    assert normalize_player_name("Nikola Jokić") == normalize_player_name("Nikola Jokic")
    assert normalize_player_name("Luka Dončić") == "luka doncic"


def test_metric_column_is_stable():
    assert metric_column("% of Time as Guard *") == "pct_of_time_as_guard"
    assert metric_column("Rim dFG% vs Expected *") == "rim_dfg_pct_vs_expected"


def _raw_row(index: int, metrics: tuple[str, ...]) -> list:
    base = [
        str(index),
        "2024-25",
        f"Player {index}",
        25,
        "BOS",
        1000,
        "Starter",
        "Primary Ball Handler",
        "Chaser",
    ]
    base.extend([0.1 * (offset + 1) for offset in range(len(metrics))])
    return base


def test_parse_table_rows_keeps_identity_and_metrics():
    metrics = DATASETS["playmaking"][:2]
    raw = [_raw_row(i, metrics) for i in range(120)]
    rows = parse_table_rows(raw, metrics, expected_season="2024-25")
    assert len(rows) == 120
    assert rows[0]["offensive_role"] == "Primary Ball Handler"
    assert rows[0][metric_column(metrics[0])] == 0.1


def test_parse_offense_position_metric():
    metrics = ("Offense Position *", "True Usage *")
    raw = []
    for index in range(120):
        row = _raw_row(index, metrics)
        row[9] = "PG"
        raw.append(row)
    rows = parse_table_rows(raw, metrics, expected_season="2024-25")
    assert rows[0]["offense_position"] == "PG"
    assert rows[0]["true_usage"] == 0.2


def test_parse_rejects_short_rows():
    try:
        parse_table_rows([[1, "2024-25", "A"]], ("True Usage *",), expected_season="2024-25")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "width" in str(exc)


def test_401_is_not_retried():
    opener = _Opener(_http_error(401))
    try:
        _request_retry(
            opener,  # type: ignore[arg-type]
            "https://bball-index.shinyapps.io/SoulYOLO3Lose/",
            data=None,
            headers={"User-Agent": "test"},
            timeout=1,
            secret="cookie-secret-value=1",
            log=lambda *_: None,
            sleep=lambda *_: None,
        )
        assert False, "expected stop"
    except BballIndexStop as exc:
        assert "401" in str(exc)
    assert opener.calls == 1


def test_429_is_not_retried():
    opener = _Opener(_http_error(429))
    try:
        _request_retry(
            opener,  # type: ignore[arg-type]
            "https://bball-index.shinyapps.io/SoulYOLO3Lose/",
            data=None,
            headers={},
            timeout=1,
            secret="",
            log=lambda *_: None,
            sleep=lambda *_: None,
        )
        assert False, "expected stop"
    except BballIndexStop as exc:
        assert "429" in str(exc)
    assert opener.calls == 1


def test_refresh_does_not_log_cookie(tmp_path: Path, monkeypatch):
    secret = "wordpress_logged_in_test=super-secret-cookie"
    monkeypatch.setenv("BBALL_INDEX_COOKIE", secret)
    settings = _settings(tmp_path)
    logs: list[str] = []

    class Boom:
        def __init__(self, **kwargs):  # noqa: ANN003
            self.secret = kwargs.get("secret", "")

        def open(self):
            raise RuntimeError(f"boom {self.secret}")

        def close(self):
            return None

    refresh_bball_index(
        settings,
        log=logs.append,
        force=True,
        datasets=("roles",),
        seasons=("2024-25",),
        sleep=lambda *_: None,
        client_factory=Boom,
    )
    text = "\n".join(logs)
    assert secret not in text
    assert "super-secret-cookie" not in text
    assert "keeping last good copy" in text


def test_failed_fetch_keeps_previous_parquet(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("BBALL_INDEX_COOKIE", raising=False)
    settings = _settings(tmp_path)
    metrics = DATASETS["roles"]
    rows = parse_table_rows(
        [_raw_row(i, metrics) for i in range(120)],
        metrics,
        expected_season="2024-25",
    )
    _atomic_replace(settings, "roles", "2024-25", _rows_to_table(rows))
    current, prev = (
        settings.data_dir / "external" / "bballindex" / "roles_2024-25.parquet",
        settings.data_dir / "external" / "bballindex" / "roles_2024-25.prev.parquet",
    )
    assert current.is_file()
    before = pq.read_table(current).num_rows

    class Boom:
        def __init__(self, **kwargs):  # noqa: ANN003
            return None

        def open(self):
            raise RuntimeError("network down")

        def close(self):
            return None

    refresh_bball_index(
        settings,
        log=lambda *_: None,
        force=True,
        datasets=("roles",),
        seasons=("2024-25",),
        sleep=lambda *_: None,
        client_factory=Boom,
    )
    assert pq.read_table(current).num_rows == before
    assert not prev.is_file() or pq.read_table(current).num_rows == before


def test_final_season_is_not_fetched_again(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("BBALL_INDEX_COOKIE", raising=False)
    settings = _settings(tmp_path)
    table = pa.table({"player_name": ["A"] * 120, "season": ["2024-25"] * 120})
    _atomic_replace(settings, "roles", "2024-25", table)
    opened: list[str] = []

    class Boom:
        def __init__(self, **kwargs):  # noqa: ANN003
            opened.append("init")

        def open(self):
            opened.append("open")

        def close(self):
            return None

    status = refresh_bball_index(
        settings,
        log=lambda *_: None,
        datasets=("roles",),
        seasons=("2024-25",),
        sleep=lambda *_: None,
        client_factory=Boom,
    )
    assert status.skipped_fresh
    assert opened == []


def test_redact_strips_cookie_header():
    secret = "sessionid=abc123secret"
    assert "abc123secret" not in redact(f"Cookie: {secret}", secret)
    assert "[redacted]" in redact("failed " + secret, secret)


def test_position_override_replaces_guard_heuristic():
    allowed = {
        "SG": {"pts_per_36": 10.0, "reb_per_36": 3.0, "ast_per_36": 3.0},
        "C": {"pts_per_36": 20.0, "reb_per_36": 10.0, "ast_per_36": 2.0},
    }
    base = RateVector()
    same = apply_opponent_position_defense(
        base,
        position="G",
        opp_allowed=allowed,
        league_allowed=allowed,
        weight=1.0,
    )
    # G with no reb/ast maps to SG, and SG allowed equals league, so FG is unchanged.
    assert same.restricted_area_fg_pct == base.restricted_area_fg_pct
    shifted = apply_opponent_position_defense(
        base,
        position="G",
        opp_allowed=allowed,
        league_allowed={
            "SG": allowed["SG"],
            "C": {"pts_per_36": 10.0, "reb_per_36": 3.0, "ast_per_36": 3.0},
        },
        weight=1.0,
        position_override="C",
    )
    assert shifted.restricted_area_fg_pct > base.restricted_area_fg_pct


def _player(pid: int, minutes: float, fg: float = 0.50):
    from projections.build import PlayerProjection

    return PlayerProjection(
        player_id=pid,
        player_name=f"P{pid}",
        team_id=1,
        team_abbr="BOS",
        opponent_team_id=2,
        opponent_abbr="NYK",
        home_away="H",
        position="G",
        started=True,
        rates=RateVector(restricted_area_fg_pct=fg, above_break_3_fg_pct=fg),
        minutes=MinutesProjection(mean=minutes, sd=1, min_minutes=0, max_minutes=40, out=False),
        expected_team_possessions=100,
        rest_days=1,
        status="Available",
        depth_rank=0,
    )


def test_positive_defense_grade_lowers_fg():
    offense = {1: _player(1, 30)}
    defense = {2: _player(2, 30)}
    before = offense[1].rates.restricted_area_fg_pct
    apply_opponent_defense_grades(
        offense,
        defense,
        perimeter={2: 1.5},
        interior={2: 1.5},
        weight=0.02,
    )
    assert offense[1].rates.restricted_area_fg_pct < before
    assert offense[1].rates.above_break_3_fg_pct < before


def test_play_type_ppp_above_league_raises_fg():
    players = {1: _player(1, 30)}
    before = players[1].rates.restricted_area_fg_pct
    apply_play_type_ppp(
        players,
        play_ppp={1: {"stable_isolation_ppp": 1.2}},
        league_ppp={"stable_isolation_ppp": 1.0},
        weight=1.0,
    )
    assert players[1].rates.restricted_area_fg_pct > before


def test_weekly_check_stamp_skips_another_session(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("BBALL_INDEX_COOKIE", raising=False)
    settings = _settings(tmp_path)
    from ingest.bball_index import _stamp_meta, _write_meta

    meta: dict = {}
    _stamp_meta(
        meta,
        "roles",
        "2026-27",
        now=datetime.now(timezone.utc),
        status="unpublished",
        row_count=0,
        error="",
    )
    _write_meta(settings, meta)
    opened: list[str] = []

    class Boom:
        def __init__(self, **kwargs):  # noqa: ANN003
            opened.append("init")

        def open(self):
            opened.append("open")

        def close(self):
            return None

    status = refresh_bball_index(
        settings,
        log=lambda *_: None,
        datasets=("roles",),
        seasons=("2026-27",),
        sleep=lambda *_: None,
        client_factory=Boom,
    )
    assert status.skipped_fresh
    assert opened == []


def test_guard_share_picks_who_actually_guards_that_position():
    import numpy as np

    from sim.engine import _primary_defender_slots

    n = 600
    offense = np.tile(np.array([0, 3, 4, 5, 6], dtype=np.int32), (n, 1))
    defense = np.tile(np.array([1, 2, 7, 8, 9], dtype=np.int32), (n, 1))
    position = np.array([4, 0, 4, 2, 2, 2, 2, 2, 2, 2], dtype=np.int8)
    share = np.full((10, 5), np.nan)
    share[1] = [5, 5, 5, 5, 80]
    share[2] = [40, 40, 10, 8, 2]
    share[7] = [20, 20, 20, 20, 20]
    share[8] = [20, 20, 20, 20, 20]
    share[9] = [20, 20, 20, 20, 20]
    picks = _primary_defender_slots(
        np.random.default_rng(1),
        off_lineups=offense,
        def_lineups=defense,
        user_slot=np.zeros(n, dtype=np.int32),
        position_code=position,
        remaining=np.ones(n, dtype=bool),
        guard_share=share,
    )
    # Slot 0 is the guard who spends his minutes on centers. Slot 1 is the
    # listed center who rarely guards them.
    assert float((picks == 0).mean()) > float((picks == 1).mean())
