"""Permanent reconciliation guardrail (league totals + starter role shares)."""

from __future__ import annotations

import pytest

from backtest.reconcile import check_reconcile_guardrail
from nba_sim.settings import load_settings


@pytest.mark.slow
def test_reconcile_guardrail_midseason():
    """Mid-season 2025-26 slice must stay within ±3% on ALL totals and roles.

    Any team or starter-share flag (including MIN) fails. Marked slow:
    ~2–4 minutes with 80 games × 80 runs. Run in CI / nightly.
    """
    settings = load_settings()
    report = check_reconcile_guardrail(
        settings,
        runs=80,
        max_games=80,
        skip_games=400,
        seed=1,
        threshold_pct=3.0,
    )
    assert report.passed, (
        f"reconcile guardrail failed team={report.team_flags} "
        f"role={report.role_flags} "
        f"team_delta={ {k: round(report.team_delta_pct.get(k, 0), 1) for k in report.team_flags} } "
        f"role_delta={ {k: round(report.role_delta_pct.get(k, 0), 1) for k in report.role_flags} }"
    )


def test_reconcile_guardrail_smoke_small():
    """Fast smoke: guardrail plumbing runs without raising."""
    settings = load_settings()
    report = check_reconcile_guardrail(
        settings,
        runs=20,
        max_games=8,
        skip_games=500,
        seed=1,
        threshold_pct=50.0,  # loose — only checks the path works
    )
    assert report.games >= 1
    assert "pts" in report.sim_team
    assert "reb" in report.team_delta_pct
