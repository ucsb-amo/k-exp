"""Headless monitor server entry point.

Launched by the dashboard as a subprocess. No GUI window — the
ready/not-ready state is surfaced through the Device Control GUI.

Everything this process writes to stderr/stdout is tagged and shown in the
server dashboard terminal, so the config constants the monitor depends on are
reported here at startup: ``MONITOR_EXPT_PATH`` / ``MONITOR_STATE_FILEPATH``
silently become ``None`` when ``%code%`` / ``%data%`` are unset for the user
the dashboard runs as (see ``kexp.config.ip._safe_join``), and handing that
``None`` to the monitor produces a much more cryptic failure later.
"""
from __future__ import annotations

import logging
import os
import sys

from waxx.util.dashboard import logging_setup
from waxx.util.device_state.run_loop import loop_specs
from waxx.util.guis.monitor_server_headless import run
from kexp.config.ip import (MONITOR_EXPT_PATH, MONITOR_STATE_FILEPATH, LOG_DIR,
                            RESET_STATE_EXPT_PATH, RUN_LOOP_EXPTS)

log = logging.getLogger(__name__)


def monitor_connections() -> tuple:
    """The connections the server holds between runs (the tweezer AWG;
    kexp.config.monitor_connections).  A failure to load them costs the
    connections, never the server."""
    try:
        from kexp.config.monitor_connections import MONITOR_CONNECTIONS  # noqa: PLC0415
    except Exception:
        log.exception("Monitor connection definitions failed to load; the server holds none.")
        return ()
    return MONITOR_CONNECTIONS


def monitor_slm_reinit():
    """The SLM's hourly reinit: the SLM server marks it due, and the monitor
    server asks for it only while the monitor is running and no run is
    starting (waxx.util.device_state.slm_reinit); the SLM server puts the last
    pattern back afterwards.  None if it fails to load -- the SLM server then
    only reports the reinit due."""
    try:
        from waxx.util.device_state.slm_reinit import SlmReinitConfig  # noqa: PLC0415
        from waxx.control.slm.slm_link import SLM_HOST, SLM_PORT  # noqa: PLC0415
    except Exception:
        log.exception("SLM reinit definition failed to load; the server will not ask for it.")
        return None
    return SlmReinitConfig(host=SLM_HOST, port=SLM_PORT, label="SLM")


def check_config() -> list[str]:
    """Return one message per unresolved kexp monitor config constant."""
    problems = []
    if MONITOR_EXPT_PATH is None:
        problems.append(
            "MONITOR_EXPT_PATH is None: the 'code' environment variable (%code%, "
            "the workspace root) is not set for this process, so the monitor "
            "experiment path could not be built. The dashboard inherits its "
            "environment from whatever launched it — check %code% there."
        )
    if MONITOR_STATE_FILEPATH is None:
        problems.append(
            "MONITOR_STATE_FILEPATH is None: the 'data' environment variable "
            "(%data%, the data drive) is not set or the drive is not mapped, so "
            "the device-state JSON path could not be built. Every device-state "
            "read/write from the Device Control GUI will fail until it is."
        )
    return problems


def main() -> int:
    logging_setup.configure(app_name="kexp", log_root=LOG_DIR, logger_namespace="kexp")
    logging_setup.configure_server_logging("monitor")
    for warning in logging_setup.pop_boot_warnings():
        log.warning("%s", warning)

    log.info("MONITOR_EXPT_PATH      = %s", MONITOR_EXPT_PATH)
    log.info("MONITOR_STATE_FILEPATH = %s", MONITOR_STATE_FILEPATH)
    problems = check_config()
    for problem in problems:
        log.error("%s", problem)
    if MONITOR_EXPT_PATH is None:
        log.error(
            "Exiting: without the monitor experiment path the monitor server "
            "could never start the monitor. Environment: %%code%% = %s, "
            "%%data%% = %s, %%db%% = %s",
            os.environ.get("code", "<UNSET>"),
            os.environ.get("data", "<UNSET>"),
            os.environ.get("db", "<UNSET>"),
        )
        return 1

    journal_dir = os.path.join(LOG_DIR, "ops_journal") if LOG_DIR else None
    log.info("OPS JOURNAL DIR        = %s", journal_dir)
    return run(MONITOR_EXPT_PATH, config_file_path=MONITOR_STATE_FILEPATH,
               journal_dir=journal_dir, reset_expt_path=RESET_STATE_EXPT_PATH,
               run_loops=loop_specs(RUN_LOOP_EXPTS), connections=monitor_connections(),
               slm_reinit=monitor_slm_reinit())


if __name__ == "__main__":
    sys.exit(main())
