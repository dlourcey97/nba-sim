from __future__ import annotations

from dataclasses import replace

import pytest

from nba_sim.settings import load_settings


@pytest.fixture
def settings(tmp_path):
    loaded = load_settings()
    return replace(
        loaded,
        data_dir=tmp_path / "data",
        archive_dir=tmp_path / "archive",
        max_bytes=50_000_000,
    )
