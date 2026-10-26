"""Compact possession-event records for a single typical-game trace.

Only one run's log is ever kept. Win probabilities are filled later from the
in-memory Monte Carlo cloud (never persisted as a full grid).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


# Outcome codes shared with the vectorized engine.
OUTCOME_NONE = 0
OUTCOME_STEAL = 1
OUTCOME_TOV = 2
OUTCOME_BONUS_FT = 3
OUTCOME_MAKE_2 = 4
OUTCOME_MAKE_3 = 5
OUTCOME_FOUL_FT = 6
OUTCOME_OREB = 7
OUTCOME_DREB = 8
OUTCOME_INT_FOUL = 9

OUTCOME_NAMES = {
    OUTCOME_STEAL: "steal",
    OUTCOME_TOV: "turnover",
    OUTCOME_BONUS_FT: "free_throws",
    OUTCOME_MAKE_2: "make_2",
    OUTCOME_MAKE_3: "make_3",
    OUTCOME_FOUL_FT: "free_throws",
    OUTCOME_OREB: "offensive_rebound",
    OUTCOME_DREB: "defensive_rebound",
    OUTCOME_INT_FOUL: "intentional_foul",
}

REGULATION_SECONDS = 2880.0
PERIOD_SECONDS = 720.0
OVERTIME_SECONDS = 300.0


@dataclass
class PossessionEvent:
    period: int
    clock_remaining: float
    offense_home: bool
    outcome: str
    shooter_id: int | None
    passer_id: int | None
    points: int
    home_pts: int
    away_pts: int
    home_win_prob: float | None = None
    game_clock: str = ""
    shooter_name: str | None = None
    passer_name: str | None = None
    offense_abbr: str | None = None
    shot_zone: str | None = None
    shot_value: int | None = None
    shot_made: bool | None = None
    fta: int = 0
    ftm: int = 0
    rebounder_id: int | None = None
    rebounder_name: str | None = None
    rebound: str | None = None
    stealer_id: int | None = None
    stealer_name: str | None = None
    turnover_id: int | None = None
    turnover_name: str | None = None
    home_lineup: list[int] = field(default_factory=list)
    away_lineup: list[int] = field(default_factory=list)
    caption: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class PossessionLog:
    """Single-run possession narrative (typical game)."""

    game_id: str
    run_index: int
    home_abbr: str
    away_abbr: str
    events: list[PossessionEvent] = field(default_factory=list)
    home_period_pts: list[int] = field(default_factory=list)
    away_period_pts: list[int] = field(default_factory=list)
    final_home_pts: int = 0
    final_away_pts: int = 0
    simulated_runs: int = 0
    players: list[dict] = field(default_factory=list)
    fit: dict | None = None

    def as_dict(self) -> dict:
        return {
            "game_id": self.game_id,
            "run_index": self.run_index,
            "home_abbr": self.home_abbr,
            "away_abbr": self.away_abbr,
            "final_home_pts": self.final_home_pts,
            "final_away_pts": self.final_away_pts,
            "home_period_pts": list(self.home_period_pts),
            "away_period_pts": list(self.away_period_pts),
            "simulated_runs": int(self.simulated_runs),
            "players": list(self.players),
            "fit": self.fit,
            "events": [event.as_dict() for event in self.events],
        }


def period_from_clock(clock_remaining: float, *, in_overtime: bool = False) -> int:
    """1-based period from seconds remaining in regulation (or OT flag)."""
    if in_overtime:
        return 5
    elapsed = max(0.0, REGULATION_SECONDS - float(clock_remaining))
    return int(min(4, max(1, int(elapsed // PERIOD_SECONDS) + 1)))


def clock_from_progress(progress: float) -> float:
    """Seconds remaining in regulation from possession-progress in [0, 1]."""
    p = max(0.0, min(1.0, float(progress)))
    return REGULATION_SECONDS * (1.0 - p)
