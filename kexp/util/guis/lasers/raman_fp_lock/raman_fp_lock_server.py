"""Launcher for the Raman FP-lock server (the Server Dashboard runs it).

    python -m kexp.util.guis.lasers.raman_fp_lock.raman_fp_lock_server

Owns RAMAN_FP_LOCK_COM while it runs (a terminal cannot open the port then;
use the panel's console).  Exits on SIGINT / SIGTERM or the dashboard's
shutdown request; on the way out the firmware is put back to its table
printout (fmt 1).
"""

from __future__ import annotations

import signal
import sys
import threading


def main() -> int:
    from waxx.util.dashboard.logging_setup import configure_server_logging  # noqa: PLC0415
    configure_server_logging("raman_fp_lock")

    import logging  # noqa: PLC0415

    from kexp.config.ip import RAMAN_FP_LOCK_COM, RAMAN_FP_LOCK_LOG_DIR  # noqa: PLC0415
    from kexp.util.guis.lasers.raman_fp_lock import (  # noqa: PLC0415
        EDGE_MARGIN_MS, RIGHT_EDGE_MS, SERVER_ID,
    )
    from waxx.util.guis.fp_lock.fp_lock_protocol import EdgeConfig  # noqa: PLC0415
    from waxx.util.guis.fp_lock.fp_lock_server import FPLockServer  # noqa: PLC0415

    log = logging.getLogger("kexp.raman_fp_lock")
    stop = threading.Event()
    server = FPLockServer(SERVER_ID, RAMAN_FP_LOCK_COM, log_dir=RAMAN_FP_LOCK_LOG_DIR or None,
                          edge=EdgeConfig(RIGHT_EDGE_MS, EDGE_MARGIN_MS),
                          on_shutdown_request=stop.set)

    def _sig(_signum, _frame):
        stop.set()

    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(s, _sig)
        except (ValueError, OSError):
            pass
    server.start()
    log.info("Raman FP lock server up (%s, log %s)", RAMAN_FP_LOCK_COM, RAMAN_FP_LOCK_LOG_DIR)
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
