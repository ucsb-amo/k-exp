"""coil_zabbix_server.py — pushes the magnet coil temperature to Zabbix.

Launched by the server dashboard as a subprocess; can also be run by hand:

    python -m kexp.util.guis.zabbix.coil_zabbix_server

Every ``PUSH_INTERVAL_S`` it sends the coil-temperature readings the
interlock server has appended to ``%data%/interlock_logs/YYYY-MM-DD.csv``
since the last push (``waxa.climate.coil.CoilTemperaturePusher``).  It only
reads those files: it never talks to the interlock server, the PLC or the
relay.

One instance for the whole lab.  The server beacons ``zabbix_coil``; a
second one started while that beacon is on the network logs where the
first is running and exits, so two dashboards never push the same reading
twice.  On start it asks Zabbix (guest, read-only) for the time of the last
value it holds and resumes from there, so a restart leaves no gap.

TCP wire format (text + JSON, newline-terminated):
    GET_SNAPSHOT            -> JSON snapshot dict
    SHUTDOWN                -> {"status":"ok"} then the process exits
"""

from __future__ import annotations

import json
import logging
import signal
import socket
import sys
import threading
import time
from typing import Callable, Optional

from beacon.discovery.server import NetServer

from waxa.climate.coil import (
    DEFAULT_KEY, DEFAULT_ZABBIX_HOST, CoilTemperaturePusher, last_pushed_clock, latest_reading,
)

LOGGER = logging.getLogger("kexp.dashboard.server.zabbix_coil")

SERVER_ID = "zabbix_coil"
PUSH_INTERVAL_S = 60.0

# Grace period between answering SHUTDOWN and signalling main() so the JSON
# reply is on the wire before the listening socket closes.
_SHUTDOWN_REPLY_GRACE_S = 0.2


class CoilPushService:
    """The push loop and its status.  No sockets of its own: testable offline."""

    NAME = "coil"   # in log messages; subclasses (other pushed quantities) override

    def __init__(self, pusher: CoilTemperaturePusher, interval_s: float = PUSH_INTERVAL_S):
        self._pusher = pusher
        self.interval_s = float(interval_s)
        self._lock = threading.Lock()
        self._started = time.time()
        self._last_attempt: Optional[float] = None
        self._last_success: Optional[float] = None
        self._last_info = ""
        self._last_error = ""
        self._sent = 0
        self._refused = 0
        self._link_down = False
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def push_once(self) -> None:
        """One push; never raises (a failed push must not end the loop)."""
        now = time.time()
        try:
            result = self._pusher.push_new(now)
        except ConnectionError as exc:
            if not self._link_down:
                LOGGER.warning("%s; readings are kept and sent when it is back", exc)
            with self._lock:
                self._link_down = True
                self._last_attempt = now
                self._last_error = str(exc)
            return
        except Exception as exc:  # noqa: BLE001 - keep the loop alive
            LOGGER.exception("%s push failed", self.NAME)
            with self._lock:
                self._last_attempt = now
                self._last_error = repr(exc)
            return
        if self._link_down:
            LOGGER.info("Zabbix reachable again")
        with self._lock:
            self._link_down = False
            self._last_attempt = now
            if result is None:
                return   # nothing new in the interlock log
            self._sent += result.processed
            self._refused += result.failed
            self._last_info = "; ".join(result.info)
            if result.processed:
                self._last_success = now
            self._last_error = "" if result.ok else f"Zabbix refused {result.failed} of {result.total}"

    def _reading_fields(self, now: float) -> dict:
        """The newest reading in the log, for the snapshot."""
        try:
            reading = latest_reading(self._pusher.log_dir)
        except Exception:  # noqa: BLE001 - status only
            reading = None
        return {
            "temperature_c": reading.temperature_c if reading else None,
            "reading_age_s": round(now - reading.epoch, 1) if reading else None,
        }

    def get_snapshot(self) -> dict:
        now = time.time()
        reading_fields = self._reading_fields(now)
        with self._lock:
            return {
                "zabbix_server": f"{self._pusher.sender.server}:{self._pusher.sender.port}",
                "zabbix_host": self._pusher.host,
                "zabbix_key": self._pusher.key,
                "log_dir": str(self._pusher.log_dir),
                "interval_s": self.interval_s,
                "uptime_s": round(now - self._started, 1),
                **reading_fields,
                "last_attempt_age_s": (round(now - self._last_attempt, 1)
                                       if self._last_attempt else None),
                "last_success_age_s": (round(now - self._last_success, 1)
                                       if self._last_success else None),
                "sent": self._sent,
                "refused": self._refused,
                "pending": self._pusher.pending,
                "zabbix_reachable": not self._link_down,
                "last_info": self._last_info,
                "last_error": self._last_error,
            }

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="zabbix-coil-push", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self._pusher.sender.timeout + 2.0)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.push_once()
            self._stop.wait(self.interval_s)


class CoilZabbixTCPServer(NetServer):
    """Threaded TCP status server + UDP beacon for the CoilPushService."""

    BEACON_ID = SERVER_ID   # subclasses (other pushed quantities) override
    NAME = "Coil"

    def __init__(self, service: CoilPushService, *, host: str = "0.0.0.0", port: int = 0,
                 on_shutdown_request: Optional[Callable[[], None]] = None):
        NetServer.__init__(self, self.BEACON_ID, port)
        self._service = service
        self._host = host
        self._port = int(port)
        self._sock: Optional[socket.socket] = None
        self._accept_thread: Optional[threading.Thread] = None
        self._running = False
        self._on_shutdown_request = on_shutdown_request
        self._shutdown_requested = False

    def start(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind((self._host, self._port))
        sock.listen(8)
        sock.settimeout(1.0)
        self._sock = sock
        self._port = sock.getsockname()[1]
        self._waxx_port = self._port
        LOGGER.info("%s -> Zabbix status server listening on %s:%s",
                    self.NAME, self._host, self._port)
        self._start_beacon()
        self._running = True
        self._accept_thread = threading.Thread(target=self._accept_loop,
                                               name="zabbix-coil-accept", daemon=True)
        self._accept_thread.start()

    def stop(self) -> None:
        self._running = False
        self._stop_beacon()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        if self._accept_thread is not None:
            self._accept_thread.join(timeout=2.0)

    def _accept_loop(self) -> None:
        while self._running:
            try:
                client, _addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                if self._running:
                    LOGGER.exception("accept failed")
                break
            threading.Thread(target=self._handle_client, args=(client,), daemon=True).start()

    def _handle_client(self, client: socket.socket) -> None:
        try:
            client.settimeout(5.0)
            data = client.recv(4096).decode("utf-8", errors="replace").strip()
            if data:
                client.sendall((self.dispatch(data) + "\n").encode("utf-8"))
        except Exception:
            LOGGER.exception("client error")
        finally:
            try:
                client.close()
            except OSError:
                pass

    def dispatch(self, raw: str) -> str:
        cmd = raw.strip().upper()
        try:
            if cmd == "GET_SNAPSHOT":
                return json.dumps(self._service.get_snapshot())
            if cmd == "SHUTDOWN":
                return json.dumps(self._request_shutdown())
            return json.dumps({"status": "error", "message": f"unknown command: {cmd}"})
        except Exception as exc:
            LOGGER.exception("RPC handler raised for %s", cmd)
            return json.dumps({"status": "error", "message": repr(exc)})

    def _request_shutdown(self) -> dict:
        if self._on_shutdown_request is None:
            return {"status": "error", "message": "shutdown not wired in this process"}
        if not self._shutdown_requested:
            self._shutdown_requested = True
            LOGGER.info("Process shutdown requested over TCP")

            def _worker() -> None:
                time.sleep(_SHUTDOWN_REPLY_GRACE_S)
                self._on_shutdown_request()

            threading.Thread(target=_worker, name="zabbix-coil-shutdown", daemon=True).start()
        return {"status": "ok"}


def _resume_point() -> Optional[float]:
    """Time of the newest coil reading Zabbix holds; None if unknown."""
    try:
        clock = last_pushed_clock(DEFAULT_ZABBIX_HOST, DEFAULT_KEY)
    except Exception as exc:  # noqa: BLE001 - best effort; start from the newest reading
        LOGGER.warning("Could not ask Zabbix for the last coil reading (%r); "
                       "starting from the newest one in the log", exc)
        return None
    if clock is None:
        LOGGER.warning("Zabbix has no value yet for item %r on host %r (does the trapper "
                       "item exist?); starting from the newest reading in the log",
                       DEFAULT_KEY, DEFAULT_ZABBIX_HOST)
    else:
        LOGGER.info("Zabbix holds coil readings up to %s; resuming after that",
                    time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(clock)))
    return clock


def main() -> int:
    from waxx.util.dashboard.logging_setup import configure_server_logging  # noqa: PLC0415
    from beacon.discovery.client import discover  # noqa: PLC0415

    log_path = configure_server_logging(SERVER_ID)
    LOGGER.info("Coil -> Zabbix server starting (host=%s, log=%s)", socket.gethostname(), log_path)

    other = discover(SERVER_ID, timeout=2.0)
    if other is not None:
        LOGGER.warning("Another coil -> Zabbix server is already running at %s:%s; "
                       "not starting a second one", *other)
        return 0

    pusher = CoilTemperaturePusher(resume_after=_resume_point())
    LOGGER.info("Pushing %s -> %s:%s host=%r key=%r every %.0f s",
                pusher.log_dir, pusher.sender.server, pusher.sender.port,
                pusher.host, pusher.key, PUSH_INTERVAL_S)
    service = CoilPushService(pusher)

    stop_event = threading.Event()
    tcp = CoilZabbixTCPServer(service, on_shutdown_request=stop_event.set)
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
