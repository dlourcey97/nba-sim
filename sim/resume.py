"""Start a simulation from a live score, clock, and box.

Used only when ``simulate_game(..., resume=...)`` is set. The pregame path
does not construct a ``ResumeState`` and does not call these helpers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from nba_sim.schema import ZONES
from sim.possession_log import PERIOD_SECONDS, REGULATION_SECONDS

# One half is about 50 possessions. A prior this large keeps tonight's
# shooting and usage from moving the pregame rates by more than a few points.
RATE_PRIOR_POSSESSIONS = 250.0
SHOT_PRIOR_FGA = 40.0
_THREE_ZONES = {"left_corner_3", "right_corner_3", "above_break_3"}


@dataclass
class PlayerLive:
    player_id: int
    name: str = ""
    team_id: int = 0
    minutes: float = 0.0
    pts: float = 0.0
    reb: float = 0.0
    ast: float = 0.0
    fouls: int = 0
    fga: float = 0.0
    fgm: float = 0.0
    fta: float = 0.0
    ftm: float = 0.0
    tov: float = 0.0
    on_court: bool = False


@dataclass
class TeamLive:
    team_id: int
    abbr: str
    score: int = 0
    fouls_this_period: int = 0
    timeouts_remaining: int = 7
    in_bonus: bool = False
    on_court: list[int] = field(default_factory=list)


@dataclass
class ResumeState:
    """Regulation state the remaining-game sim starts from.

    ``period`` is 1–4 and ``clock_seconds`` is the time left in that period.
    A horn (clock 0) is the start of the next period: end of Q2 starts Q3.
    """

    period: int
    clock_seconds: float
    home: TeamLive
    away: TeamLive
    players: dict[int, PlayerLive]
    possession_team_id: int | None = None
    rate_prior_possessions: float = RATE_PRIOR_POSSESSIONS

    @property
    def elapsed_seconds(self) -> float:
        period = min(max(int(self.period), 1), 4)
        clock = min(max(float(self.clock_seconds), 0.0), PERIOD_SECONDS)
        return (period - 1) * PERIOD_SECONDS + (PERIOD_SECONDS - clock)

    @property
    def elapsed_fraction(self) -> float:
        return float(np.clip(self.elapsed_seconds / REGULATION_SECONDS, 0.0, 1.0))

    @property
    def period_index(self) -> int:
        """0-based period the next possession belongs to. Matches the engine clock."""
        return int(np.clip(np.floor(self.elapsed_seconds / PERIOD_SECONDS), 0, 3))


def clock_to_seconds(clock: str | None) -> float:
    """Parse an ISO duration like ``PT11M49.00S`` into seconds left in the period."""
    if not clock:
        return PERIOD_SECONDS
    text = str(clock).upper().replace("PT", "")
    minutes = 0.0
    seconds = 0.0
    if "M" in text:
        min_text, text = text.split("M", 1)
        minutes = float(min_text or 0)
    if text.endswith("S"):
        text = text[:-1]
    if text:
        seconds = float(text)
    return minutes * 60.0 + seconds


def foul_minute_factor(fouls: int, period: int, clock_seconds: float) -> float:
    """Sit a player down when the foul count would get him disqualified.

    Six fouls is a disqualification. Five before the fourth quarter, or four
    in the first half, cuts the remaining minutes. The pregame draw is unchanged
    when this is not applied.
    """
    if fouls >= 6:
        return 0.0
    if fouls >= 5 and period < 4:
        return 0.15
    if fouls >= 4 and period <= 2:
        return 0.50
    if fouls >= 3 and period == 1 and clock_seconds > 360:
        return 0.75
    return 1.0


def _scale_columns(
    block: np.ndarray,
    *,
    out: np.ndarray,
    caps: np.ndarray,
    target: float,
    min_minutes: float,
) -> np.ndarray:
    """Scale every run of one team to ``target`` without a Python loop over runs."""
    result = np.maximum(np.array(block, dtype=float, copy=True), 0.0)
    flexible = (~np.asarray(out, dtype=bool)) & (np.asarray(caps, dtype=float) > 0)
    result[~flexible, :] = 0.0
    if not np.any(flexible) or target <= 0:
        return result
    cap_col = caps[:, None]
    empty = result.sum(axis=0) <= 1e-9
    if np.any(empty):
        result[:, empty] = flexible.astype(float)[:, None]
    for _ in range(6):
        result = np.minimum(np.maximum(result, 0.0), cap_col)
        result[~flexible, :] = 0.0
        if min_minutes > 0:
            positive = flexible[:, None] & (result > 0)
            result = np.where(positive, np.maximum(result, min_minutes), result)
            result = np.minimum(result, cap_col)
            result[~flexible, :] = 0.0
        totals = np.maximum(result.sum(axis=0), 1e-9)
        result *= target / totals
    result = np.minimum(np.maximum(result, 0.0), cap_col)
    result[~flexible, :] = 0.0
    return result


def apply_resume_minutes(
    minutes: np.ndarray,
    players: list,
    resume: ResumeState,
    home_idx: np.ndarray,
    away_idx: np.ndarray,
    *,
    team_target: float,
    min_minutes: float,
) -> None:
    """Turn full-game minute draws into minutes still left, in place.

    Already-played time is removed. Players who have not entered by the half
    keep only a slice of the pregame draw. Foul trouble and disqualifications
    cut further. Each side is then scaled to the minutes left in regulation.
    """
    frac = resume.elapsed_fraction
    remain_frac = max(0.0, 1.0 - frac)
    if remain_frac <= 1e-6:
        minutes[:] = 0.0
        return
    on_court = set(resume.home.on_court) | set(resume.away.on_court)
    out = np.array([bool(p.minutes.out) for p in players], dtype=bool)
    caps = np.array(
        [0.0 if p.minutes.out else float(p.minutes.max_minutes) for p in players],
        dtype=float,
    )
    for index, player in enumerate(players):
        if out[index]:
            minutes[index] = 0.0
            continue
        line = resume.players.get(int(player.player_id))
        played = 0.0 if line is None else float(line.minutes)
        fouls = 0 if line is None else int(line.fouls)
        raw = np.maximum(0.0, minutes[index] - played)
        not_in_yet = line is None or (played <= 0.5 and int(player.player_id) not in on_court)
        if not_in_yet and frac >= 0.45:
            raw *= 0.35
        if int(player.player_id) in on_court:
            raw = np.maximum(raw, 4.0 * remain_frac)
        playing = int(resume.period_index) + 1
        clock_now = float(resume.clock_seconds) if playing == int(resume.period) else PERIOD_SECONDS
        factor = foul_minute_factor(fouls, playing, clock_now)
        raw *= factor
        if factor <= 0.0:
            out[index] = True
            caps[index] = 0.0
            raw[:] = 0.0
        minutes[index] = raw
    target = float(team_target) * remain_frac
    for pool in (home_idx, away_idx):
        if pool.size == 0:
            continue
        minutes[pool] = _scale_columns(
            minutes[pool],
            out=out[pool],
            caps=caps[pool],
            target=target,
            min_minutes=min_minutes,
        )


def apply_resume_rates(packed: dict[str, np.ndarray], players: list, resume: ResumeState) -> None:
    """Pull usage, free-throw rate, and assist rate a little toward tonight.

    The weight is possessions so far over possessions so far plus a large prior,
    so a half of basketball cannot rewrite the pregame rate.
    """
    home_used = _team_used(resume, resume.home.team_id)
    away_used = _team_used(resume, resume.away.team_id)
    prior = float(resume.rate_prior_possessions)
    for index, player in enumerate(players):
        line = resume.players.get(int(player.player_id))
        if line is None:
            continue
        team_used = home_used if int(player.team_id) == int(resume.home.team_id) else away_used
        team_used = max(float(team_used), 1.0)
        weight = team_used / (team_used + prior)
        used = float(line.fga) + 0.44 * float(line.fta) + float(line.tov)
        if used > 0 and team_used > 0:
            observed = float(np.clip(used / team_used, 0.02, 0.45))
            packed["usage"][index] = (1.0 - weight) * packed["usage"][index] + weight * observed
        if used >= 1.0 and line.fta >= 0:
            observed_ft = float(np.clip(line.fta / used, 0.0, 0.80))
            packed["ft_rate"][index] = (1.0 - weight) * packed["ft_rate"][index] + weight * observed_ft
        team_fgm = _team_fgm(resume, int(player.team_id))
        teammate_makes = max(team_fgm - float(line.fgm), 1.0)
        if line.ast > 0 or team_fgm >= 4:
            observed_ast = float(np.clip(line.ast / teammate_makes, 0.0, 0.60))
            packed["ast_rate"][index] = (1.0 - weight) * packed["ast_rate"][index] + weight * observed_ast
        _nudge_shooting(packed, index, line)
    _apply_bonus(packed, players, resume)


def pin_on_court(
    grid: np.ndarray,
    pool: np.ndarray,
    on_court: list[int],
    players: list,
    period_index: int,
    rng: np.random.Generator,
    *,
    share: float = 0.55,
) -> None:
    """Keep the players who are on the floor on the floor for this period.

    Blowout lineups (bucket 2) stay on the bench rotation. Close and moderate
    lineups use the live five on ``share`` of the runs. No effect when the
    live five is not in this side's pool.
    """
    if grid.size == 0 or grid.shape[-1] != 5 or not on_court:
        return
    index = {int(player.player_id): i for i, player in enumerate(players)}
    pool_set = {int(i) for i in pool}
    slots = []
    for player_id in on_court:
        slot = index.get(int(player_id))
        if slot is None or slot not in pool_set:
            return
        slots.append(slot)
    if len(slots) != 5:
        return
    five = np.array(slots, dtype=np.int32)
    mask = rng.random(grid.shape[0]) < float(share)
    if not np.any(mask):
        return
    for bucket in (0, 1):
        grid[mask, period_index, bucket, :] = five


def seed_resume_score(
    *,
    pts: np.ndarray,
    reb: np.ndarray,
    ast: np.ndarray,
    home_pts: np.ndarray,
    away_pts: np.ndarray,
    players: list,
    resume: ResumeState,
    base_target: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray | None]:
    """Write the live box into every run and return the clock position.

    The last return is a possession mask (True = home ball), or None when the
    feed did not say who has the ball.
    """
    index = {int(player.player_id): i for i, player in enumerate(players)}
    for player_id, line in resume.players.items():
        slot = index.get(int(player_id))
        if slot is None:
            continue
        pts[slot, :] = float(line.pts)
        reb[slot, :] = float(line.reb)
        ast[slot, :] = float(line.ast)
    home_pts[:] = float(resume.home.score)
    away_pts[:] = float(resume.away.score)
    frac = resume.elapsed_fraction
    endings = np.rint(frac * base_target).astype(np.int32)
    endings = np.minimum(endings, base_target.astype(np.int32))
    n_runs = home_pts.shape[0]
    last_period = np.full(n_runs, resume.period_index, dtype=np.int32)
    period_home_start = np.full(n_runs, float(resume.home.score), dtype=float)
    period_away_start = np.full(n_runs, float(resume.away.score), dtype=float)
    offense = None
    if resume.possession_team_id:
        offense = np.full(n_runs, int(resume.possession_team_id) == int(resume.home.team_id))
    return endings, last_period, period_home_start, period_away_start, offense


def resume_foul_prob(foul_prob: float, resume: ResumeState) -> float:
    """Foul more late when the trailing side is out of timeouts.

    The engine already fouls intentionally in the last minutes of close games.
    An empty timeout wallet, with the game already in the fourth, raises that rate.
    """
    if resume.period < 4 or resume.clock_seconds > 180:
        return foul_prob
    home_trail = resume.home.score < resume.away.score
    away_trail = resume.away.score < resume.home.score
    trailing_timeouts = None
    if home_trail:
        trailing_timeouts = resume.home.timeouts_remaining
    elif away_trail:
        trailing_timeouts = resume.away.timeouts_remaining
    if trailing_timeouts is None or trailing_timeouts > 0:
        return foul_prob
    return float(min(0.55, foul_prob * 1.8))


def pregame_counting(player) -> tuple[float, float, float]:
    """Pregame points, rebounds, and assists from the rate vector and minutes.

    This is the baseline that gets scaled by time remaining. It is not a sim.
    """
    minutes = max(float(player.minutes.mean), 0.0)
    if player.minutes.out or minutes <= 0:
        return 0.0, 0.0, 0.0
    share = minutes / 48.0
    poss = float(player.expected_team_possessions) * share
    rates = player.rates
    uses = poss * float(rates.usage)
    live_uses = uses * (1.0 - float(rates.tov_rate))
    points_per_fga = 0.0
    for zone in ZONES:
        share_z = float(getattr(rates, f"{zone}_share"))
        made = float(getattr(rates, f"{zone}_fg_pct"))
        points = 3.0 if zone in _THREE_ZONES else 2.0
        points_per_fga += share_z * made * points
    fga = live_uses * 0.82
    ft_points = uses * float(rates.ft_rate) * float(rates.ft_pct)
    pts = fga * points_per_fga + ft_points
    reb = share * (float(rates.oreb_rate) * 14.0 + float(rates.dreb_rate) * 36.0)
    ast = float(rates.ast_rate) * max(poss * 0.46, 0.0)
    return float(pts), float(reb), float(ast)


def _team_used(resume: ResumeState, team_id: int) -> float:
    total = 0.0
    for line in resume.players.values():
        if int(line.team_id) != int(team_id):
            continue
        total += float(line.fga) + 0.44 * float(line.fta) + float(line.tov)
    return total


def _team_fgm(resume: ResumeState, team_id: int) -> float:
    return float(sum(line.fgm for line in resume.players.values() if int(line.team_id) == int(team_id)))


def _nudge_shooting(packed: dict[str, np.ndarray], index: int, line: PlayerLive) -> None:
    if line.fga < 1:
        return
    observed = float(line.fgm) / float(line.fga)
    weights = packed["zone_share"][index]
    percents = packed["zone_fg"][index]
    pre = float(np.sum(weights * percents))
    if pre <= 0.05:
        return
    weight = float(line.fga) / (float(line.fga) + SHOT_PRIOR_FGA)
    factor = (1.0 - weight) + weight * (observed / pre)
    factor = float(np.clip(factor, 0.88, 1.12))
    packed["zone_fg"][index] = np.clip(percents * factor, 0.15, 0.85)


def _apply_bonus(packed: dict[str, np.ndarray], players: list, resume: ResumeState) -> None:
    """A team in the bonus sends the other side to the line a bit more often."""
    boosted: set[int] = set()
    if resume.home.in_bonus:
        boosted.add(int(resume.away.team_id))
    if resume.away.in_bonus:
        boosted.add(int(resume.home.team_id))
    if not boosted:
        return
    for index, player in enumerate(players):
        if int(player.team_id) in boosted:
            packed["ft_rate"][index] = float(np.clip(packed["ft_rate"][index] * 1.08, 0.0, 0.80))
