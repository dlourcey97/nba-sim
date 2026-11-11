"""Before/after check for the box-usage realignment. Not a model input."""

from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import copy
from collections import defaultdict
from dataclasses import replace
from datetime import date

from duckdb import connect

from nba_sim.settings import load_settings
from projections.blend import available_season_window, load_season_bundle
from projections.build import ProjectionCache, build_game_projections
from sim.engine import simulate_game


def _settings(align: bool):
    settings = load_settings()
    config = copy.deepcopy(settings.config)
    config["blending"]["align_box_usage"] = align
    return replace(settings, config=config)


def main() -> None:
    settings = load_settings()
    data = settings.data_dir
    season = settings.current_season
    con = connect()

    def pq(name: str) -> str:
        return str(data / name / f"season={season}" / "data.parquet")

    # Stored table versus the box line, top scorers.
    print("TABLE vs BOX", flush=True)
    rows = con.execute(
        f"""
        SELECT l.player_id, any_value(l.player_name) nm,
               avg(l.pts) ppg, avg(l.minutes) mpg,
               avg(r.usage) usg,
               avg((l.fga + 0.44 * l.fta + l.tov) / nullif(t.pace * l.minutes / 48.0, 0)) box,
               count(*) n
        FROM read_parquet('{pq("player_game_logs")}') l
        JOIN read_parquet('{pq("player_game_rates")}') r
          ON l.game_id = r.game_id AND l.player_id = r.player_id
        JOIN read_parquet('{pq("team_game_results")}') t
          ON t.game_id = l.game_id AND t.team_id = l.team_id
        WHERE l.minutes >= 20 AND t.pace > 0
        GROUP BY l.player_id
        HAVING count(*) >= 8
        ORDER BY ppg DESC
        LIMIT 12
        """
    ).fetchall()
    for row in rows:
        print(
            f"  {row[1]:24} ppg {row[2]:5.1f} table {row[4]:.3f} box {row[5]:.3f}",
            flush=True,
        )

    window = available_season_window(
        settings, season, list(settings.config["blending"]["season_weights"]["seasons_back"])
    )
    if season not in window:
        window = [season] + window
    print("loading", window, flush=True)
    bundles = [load_season_bundle(settings, label) for label in window]

    dates = [
        date(2026, 11, 2),
        date(2026, 11, 4),
        date(2026, 11, 5),
        date(2026, 11, 6),
        date(2026, 11, 7),
        date(2026, 11, 8),
        date(2026, 11, 9),
    ]
    games = con.execute(
        f"""
        SELECT game_id, game_date, away_abbr, home_abbr
        FROM read_parquet('{pq("schedule")}')
        WHERE status = 'final' AND game_date BETWEEN DATE '2026-11-02' AND DATE '2026-11-09'
        ORDER BY game_date, game_id
        """
    ).fetchall()
    print(f"games {len(games)}", flush=True)

    season_ppg = {
        int(row[0]): (float(row[2]), float(row[3]), row[1])
        for row in con.execute(
            f"""
            SELECT player_id, any_value(player_name), avg(pts), avg(minutes)
            FROM read_parquet('{pq("player_game_logs")}')
            WHERE minutes >= 8
            GROUP BY player_id
            HAVING count(*) >= 8
            """
        ).fetchall()
    }
    top30 = [
        pid
        for pid, _ in sorted(season_ppg.items(), key=lambda item: -item[1][0])[:30]
    ]
    actual = {
        (str(row[0]), int(row[1])): (float(row[2]), float(row[3]), float(row[4]))
        for row in con.execute(
            f"""
            SELECT game_id, player_id, pts, minutes, team_id
            FROM read_parquet('{pq("player_game_logs")}')
            WHERE game_date BETWEEN DATE '2026-11-02' AND DATE '2026-11-09'
            """
        ).fetchall()
    }
    team_actual = {
        (str(row[0]), int(row[1])): float(row[2])
        for row in con.execute(
            f"""
            SELECT game_id, team_id, pts
            FROM read_parquet('{pq("team_game_results")}')
            WHERE game_date BETWEEN DATE '2026-11-02' AND DATE '2026-11-09'
            """
        ).fetchall()
    }

    def run(align: bool) -> None:
        local = _settings(align)
        cache = ProjectionCache()
        # player -> list of (median, mean, minute median, actual pts) for top 30 with minutes right
        star_rows = []
        under = []
        actual_under = []
        team_gaps = []
        watched = {1629029: "Luka", 1630595: "Cade", 1630178: "Maxey"}
        for game_id, game_date, away, home in games:
            if game_date not in dates and not isinstance(game_date, date):
                continue
            try:
                projection = build_game_projections(
                    local,
                    season=season,
                    game_id=str(game_id),
                    as_of=game_date if isinstance(game_date, date) else date.fromisoformat(str(game_date)),
                    bundles=bundles,
                    cache=cache,
                )
            except ValueError as exc:
                print(" skip", game_id, exc, flush=True)
                continue
            sim = simulate_game(projection, runs=1000, seed=1, config=local.config)
            by_id = {int(p.player_id): p for p in projection.players}
            team_ids = {}
            side_mean = defaultdict(float)
            side_med_players = defaultdict(float)
            for index, pid in enumerate(sim.player_ids):
                pid = int(pid)
                player = by_id.get(pid)
                if player is None:
                    continue
                pts = sim.pts[index]
                minutes = sim.minutes[index]
                med = float(sorted(pts)[len(pts) // 2])
                mean = float(pts.mean())
                min_med = float(sorted(minutes)[len(minutes) // 2])
                team_ids[pid] = int(player.team_id)
                side_mean[int(player.team_id)] += mean
                side_med_players[int(player.team_id)] += med
                if pid in watched:
                    print(
                        f"  {watched[pid]:8} {game_date} align={align} "
                        f"usg {player.rates.usage:.3f} min {min_med:.1f} "
                        f"pts med {med:.1f} mean {mean:.1f}",
                        flush=True,
                    )
                season_line = season_ppg.get(pid)
                if season_line is None:
                    continue
                ppg, mpg, _name = season_line
                act = actual.get((str(game_id), pid))
                if pid in top30 and min_med >= 30 and mpg > 0:
                    star_rows.append((med - ppg, mean - ppg, min_med - mpg))
                if pid in top30 and ppg > 0:
                    cut = 0.5 * ppg
                    under.append(float((pts < cut).mean()))
                    if act is not None:
                        actual_under.append(1.0 if act[0] < cut else 0.0)
            home_team = next(
                (int(p.team_id) for p in projection.players if p.home_away == "H"),
                None,
            )
            for team_id, proj_mean in side_mean.items():
                act_pts = team_actual.get((str(game_id), team_id))
                if act_pts is None:
                    continue
                scores = sim.home_pts if team_id == home_team else sim.away_pts
                team_med = float(sorted(scores)[len(scores) // 2])
                team_gaps.append(
                    (
                        side_med_players[team_id] - act_pts,
                        proj_mean - act_pts,
                        team_med - act_pts,
                        float(scores.mean()) - act_pts,
                    )
                )
            print(f"  done {game_date} {away}@{home} align={align}", flush=True)
        if star_rows:
            n = len(star_rows)
            print(
                f"ALIGN {align} high-minute top30 n={n} "
                f"med {sum(r[0] for r in star_rows)/n:+.2f} "
                f"mean {sum(r[1] for r in star_rows)/n:+.2f} "
                f"min {sum(r[2] for r in star_rows)/n:+.2f}",
                flush=True,
            )
        if under:
            print(
                f"ALIGN {align} P(sim < 50% season) {sum(under)/len(under):.3f} "
                f"actual {sum(actual_under)/len(actual_under):.3f} n={len(under)}",
                flush=True,
            )
        if team_gaps:
            n = len(team_gaps)
            print(
                f"ALIGN {align} teams n={n} "
                f"sum_med {sum(r[0] for r in team_gaps)/n:+.2f} "
                f"sum_mean {sum(r[1] for r in team_gaps)/n:+.2f} "
                f"team_med {sum(r[2] for r in team_gaps)/n:+.2f} "
                f"team_mean {sum(r[3] for r in team_gaps)/n:+.2f}",
                flush=True,
            )

    run(False)
    run(True)
    print("CHECK DONE", flush=True)


if __name__ == "__main__":
    main()
