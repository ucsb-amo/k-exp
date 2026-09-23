"""Windowed monitor server launcher (K machine).

Thin kexp wrapper around :class:`waxx.util.guis.monitor_server_gui.MonitorServerGUI`.
Its one job beyond launching is to check the kexp config constants the monitor
depends on and, if one is unresolved, say which environment variable it came
from — ``MONITOR_EXPT_PATH`` / ``MONITOR_STATE_FILEPATH`` silently become
``None`` when ``%code%`` / ``%data%`` are unset (see ``kexp.config.ip._safe_join``),
and passing that ``None`` down produces a far less obvious failure later.
"""
import logging
import os
import sys
from PyQt6.QtWidgets import QApplication

from waxx.util.guis.monitor_server_gui import MonitorServerGUI
from waxx.util.dashboard import logging_setup

from kexp.config.ip import MONITOR_EXPT_PATH, MONITOR_STATE_FILEPATH, LOG_DIR

log = logging.getLogger(__name__)


def check_config() -> list[str]:
    """Return one message per unresolved kexp monitor config constant."""
    problems = []
    if MONITOR_EXPT_PATH is None:
        problems.append(
            "MONITOR_EXPT_PATH is None: the 'code' environment variable (%code%, "
            "the workspace root) is not set in this process, so the monitor "
            "experiment path could not be built. Launch from a shell where %code% "
            "is set (or via the _bat launchers)."
        )
    if MONITOR_STATE_FILEPATH is None:
        problems.append(
            "MONITOR_STATE_FILEPATH is None: the 'data' environment variable "
            "(%data%, the data drive) is not set or the drive is not mapped, so "
            "the device-state JSON path could not be built. Every device-state "
            "read/write will fail until it is."
        )
    return problems


def main():
    import ctypes
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
            "Refusing to start the monitor server GUI: without the monitor "
            "experiment path it could never start the monitor. Environment: "
            "%%code%% = %s, %%data%% = %s, %%db%% = %s",
            os.environ.get("code", "<UNSET>"),
            os.environ.get("data", "<UNSET>"),
            os.environ.get("db", "<UNSET>"),
        )
        return 1

    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('weldlab.kexp.gui.monitor_server')
    app = QApplication(sys.argv)
    app.setStyle('Windows')
    try:
        gui = MonitorServerGUI(monitor_expt_path=MONITOR_EXPT_PATH,
                               config_file_path=MONITOR_STATE_FILEPATH)
    except Exception:
        log.exception("Monitor server GUI failed to start")
        return 1
    gui.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
