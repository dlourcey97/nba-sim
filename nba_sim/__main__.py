"""Print the DATA_DIR storage report and exit non-zero when the cap is exceeded."""

from __future__ import annotations

import sys

from nba_sim.errors import StorageCapExceeded
from nba_sim.settings import load_settings
from nba_sim.storage import finish_run


def main() -> int:
    settings = load_settings()
    try:
        finish_run(settings)
    except StorageCapExceeded as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
