"""Headless monitor server entry point.

Launched by the dashboard as a subprocess. No GUI window — the
ready/not-ready state is surfaced through the Device Control GUI.
"""
from __future__ import annotations

import sys

from waxx.util.guis.monitor_server_headless import run
from kexp.config.ip import MONITOR_EXPT_PATH, MONITOR_STATE_FILEPATH


def main() -> int:
    return run(MONITOR_EXPT_PATH, config_file_path=MONITOR_STATE_FILEPATH)


if __name__ == "__main__":
    sys.exit(main())
