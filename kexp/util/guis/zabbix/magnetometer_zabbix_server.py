"""magnetometer_zabbix_server.py — pushes the HMR magnetometer field to Zabbix.

Launched by the server dashboard as a subprocess; can also be run by hand:

    python -m kexp.util.guis.zabbix.magnetometer_zabbix_server

Every ``PUSH_INTERVAL_S`` it sends the field readings the magnetometer
server has appended to ``%data%/magnetometer_data/hmr2300_YYYY-MM-DD.csv``
since the last push (``waxa.climate.magnetometer.MagnetometerPusher``): one
reading per ``MIN_SPACING_S``, each a log row as written (gauss), to the
trapper items ``k.magnetometer.bx`` / ``.by`` / ``.bz`` / ``.btot`` on the
K host.  It only reads those files: it never talks to the magnetometer
server or the sensor.

One instance for the whole lab.  The server beacons ``zabbix_magnetometer``;
a second one started while that beacon is on the network logs where the
first is running and exits.  On start it asks Zabbix (guest, read-only) for
the time of the last value it holds and resumes from there, so a restart
leaves no gap.

TCP wire format: as ``coil_zabbix_server`` (GET_SNAPSHOT, SHUTDOWN).
"""

from __future__ import annotations

import logging
import signal
import socket
import sys
import threading
import time
from typing import Optional

from waxa.climate.magnetometer import (
    DEFAULT_KEYS, DEFAULT_ZABBIX_HOST, MagnetometerPusher, last_pushed_clocks, latest_reading,
)

from kexp.config.ip import MAGNETOMETER_LOG_DIR
from kexp.util.guis.zabbix.coil_zabbix_server import CoilPushService, CoilZabbixTCPServer

LOGGER = logging.getLogger("kexp.dashboard.server.zabbix_magnetometer")

SERVER_ID = "zabbix_magnetometer"
PUSH_INTERVAL_S = 60.0
# Send at most one reading per this many seconds (the field log has one per second).
MIN_SPACING_S = 10.0


class MagnetometerPushService(CoilPushService):
    """The coil push loop, around a :class:`MagnetometerPusher`."""

    NAME = "magnetometer"

    def _reading_fields(self, now: float) -> dict:
        try:
            reading = latest_reading(self._pusher.log_dir)
        except Exception:  # noqa: BLE001 - status only
            reading = None
        return {
            "field_g": dict(reading.fields) if reading else None,
            "reading_age_s": round(now - reading.epoch, 1) if reading else None,
        }


class MagnetometerZabbixTCPServer(CoilZabbixTCPServer):
    BEACON_ID = SERVER_ID
    NAME = "Magnetometer"


def _resume_point() -> Optional[float]:
    """Time of the newest magnetometer value Zabbix holds; None if unknown."""
    keys = list(DEFAULT_KEYS.values())
    try:
        clocks = last_pushed_clocks(DEFAULT_ZABBIX_HOST, keys)
    except Exception as exc:  # noqa: BLE001 - best effort; start from the newest reading
        LOGGER.warning("Could not ask Zabbix for the last magnetometer reading (%r); "
                       "starting from the newest one in the log", exc)
        return None
    missing = [k for k, c in clocks.items() if c is None]
    if missing:
        LOGGER.warning("Zabbix has no value yet for item(s) %s on host %r (do the trapper "
                       "items exist?)", ", ".join(missing), DEFAULT_ZABBIX_HOST)
    held = [c for c in clocks.values() if c is not None]
    if not held:
        LOGGER.info("Starting from the newest reading in the log")
        return None
    # The newest of them: an item that lags is left with a gap rather than
    # the others being sent values they already hold.
    clock = max(held)
    LOGGER.info("Zabbix holds magnetometer readings up to %s; resuming after that",
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(clock)))
    return clock


def main() -> int:
    from waxx.util.dashboard.logging_setup import configure_server_logging  # noqa: PLC0415
    from beacon.discovery.client import discover  # noqa: PLC0415

    log_path = configure_server_logging(SERVER_ID)
    LOGGER.info("Magnetometer -> Zabbix server starting (host=%s, log=%s)",
                socket.gethostname(), log_path)

    other = discover(SERVER_ID, timeout=2.0)
    if other is not None:
        LOGGER.warning("Another magnetometer -> Zabbix server is already running at %s:%s; "
                       "not starting a second one", *other)
        return 0

    pusher = MagnetometerPusher(log_dir=MAGNETOMETER_LOG_DIR, min_interval_s=MIN_SPACING_S,
                                resume_after=_resume_point())
    LOGGER.info("Pushing %s -> %s:%s host=%r keys=%s every %.0f s",
                pusher.log_dir, pusher.sender.server, pusher.sender.port,
                pusher.host, pusher.key, PUSH_INTERVAL_S)
    service = MagnetometerPushService(pusher, PUSH_INTERVAL_S)

    stop_event = threading.Event()
    tcp = MagnetometerZabbixTCPServer(service, on_shutdown_request=stop_event.set)
    tcp.start()
    service.start()

    def _sig(_signum, _frame):
        LOGGER.info("Signal received; shutting down")
        stop_event.set()

    try:
        signal.signal(signal.SIGINT, _sig)
        signal.signal(signal.SIGTERM, _sig)
    except Exception:
        pass

    try:
        while not stop_event.wait(1.0):
            pass
    except KeyboardInterrupt:
        pass
    finally:
        LOGGER.info("Shutting down")
        tcp.stop()
        service.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
