# nba-sim

NBA Monte Carlo simulation engine. It simulates player stat distributions and game outcomes. It does not compute odds, lines, or betting edges.

Game data lives outside this repository. `DATA_DIR` and `ARCHIVE_DIR` in `.env` must be absolute paths outside the repo. The default cap is 2 GiB. A run stops instead of writing past it.

```bash
pip install -e ".[dev]"
pytest
python -m nba_sim
```

`python -m nba_sim` prints a storage report for `DATA_DIR` (bytes per table and season, plus the total) and exits with status 1 when the cap is exceeded.

Table layouts are in `SCHEMA.md`. Phase status is in `PROGRESS.md`. Tunable blend, minutes, and simulation parameters are in `config.yaml`.
