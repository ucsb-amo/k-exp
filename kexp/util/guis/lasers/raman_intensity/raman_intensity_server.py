"""Launcher for the Raman intensity PID server (the Server Dashboard runs it).

    python -m kexp.util.guis.lasers.raman_intensity.raman_intensity_server

Owns RAMAN_INTENSITY_COM while it runs (a terminal cannot open the port then;
COM-disconnect it from the dashboard first).  Exits on SIGINT / SIGTERM or the
dashboard's shutdown request.
"""

from __future__ import annotations

import signal
import sys
import threading


def main() -> int:
    from waxx.util.dashboard.logging_setup import configure_server_logging  # noqa: PLC0415
    configure_server_logging("raman_intensity")

    import logging  # noqa: PLC0415

    from kexp.config.ip import RAMAN_INTENSITY_COM, RAMAN_INTENSITY_LOG_DIR  # noqa: PLC0415
    from kexp.util.guis.lasers.raman_intensity import GAINS_PATH, LOOP_NAMES, SERVER_ID  # noqa: PLC0415
    from waxx.util.guis.intensity_pid.intensity_pid_server import IntensityPIDServer  # noqa: PLC0415

    log = logging.getLogger("kexp.raman_intensity")
    stop = threading.Event()
    server = IntensityPIDServer(SERVER_ID, RAMAN_INTENSITY_COM,
                                log_dir=RAMAN_INTENSITY_LOG_DIR or None, gains_path=GAINS_PATH,
                                loop_names=LOOP_NAMES, on_shutdown_request=stop.set)

    def _sig(_signum, _frame):
        stop.set()

    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(s, _sig)
        except (ValueError, OSError):
            pass
    server.start()
    log.info("Raman intensity server up (%s, log %s, gains %s)", RAMAN_INTENSITY_COM,
             RAMAN_INTENSITY_LOG_DIR, GAINS_PATH)
    try:
        while not stop.wait(1.0):
            pass
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
