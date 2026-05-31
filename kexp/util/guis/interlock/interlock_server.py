"""interlock_server.py — runs InterlockService + TCP RPC + UDP beacon.

Launch:

    python -m kexp.util.guis.interlock.interlock_server

Or via the dashboard supervisor (see kexp.util.dashboard.server_registry).

Wire format
-----------
Newline-terminated commands; JSON responses.

Commands:
    GET_SNAPSHOT          -> JSON snapshot dict
    RESET_INTERLOCK       -> {"status": "ok"|"refused"|"ignored"|"error", ...}
    ENABLE_MAGNETS        -> {"status": ...}
    DISABLE_MAGNETS       -> {"status": ...}
    FLUSH_CSV             -> {"status": "ok"}

No authentication; LAN-trusted (matches existing protocol).
"""

from __future__ import annotations

# faulthandler MUST be registered before any heavy third-party import per IT2.
import faulthandler
import json
import logging
import os
import signal
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Optional


def _early_log_setup() -> Path:
    from waxx.util.dashboard.logging_setup import configure_server_logging  # noqa: PLC0415
    return configure_server_logging("interlock")


# Set up logging + faulthandler first.
_LOG_PATH = _early_log_setup()
faulthandler.enable()  # already enabled by logging_setup; idempotent

LOGGER = logging.getLogger("kexp.dashboard.server.interlock.runner")

# Now safe to import heavy stuff.
from waxx.util.comms_server.waxx_server import WaxxServer  # noqa: E402

from kexp import EthernetRelay  # noqa: E402
from kexp.config.ip import INTERLOCK_EMAIL_CREDENTIALS_FILEPATH  # noqa: E402
from kexp.util.guis.interlock import interlock_safe_mode as _sm  # noqa: E402
from kexp.util.guis.interlock.interlock_service import (  # noqa: E402
    InterlockConfig, InterlockService,
)


_DEFAULT_PORT = 5570  # matches lab's reserved range; reused by client.


def _build_email_sender() -> Optional[callable]:
    """Build a callable(subject, body) that sends via Gmail SMTP.

    Loads credentials from the shared-drive file referenced by
    INTERLOCK_EMAIL_CREDENTIALS_FILEPATH (existing pattern).  Returns None
    if credentials cannot be loaded; emails are then disabled but trip
    behavior is unaffected (IT5).
    """
    try:
        from waxx.util.notifications import _load_credentials  # noqa: PLC0415
        user, pw = _load_credentials(INTERLOCK_EMAIL_CREDENTIALS_FILEPATH)
    except Exception as exc:
        LOGGER.warning("SMTP credentials unavailable; email notifications disabled: %r", exc)
        return None

    recipient = "infrastructure-aaaaaxkptfownhvfr3q4he2qeu@weldlab.slack.com"

    def _send(subject: str, body: str) -> None:
        # IT5: 10 s socket timeout, no retry.
        import smtplib  # noqa: PLC0415
        from email.mime.multipart import MIMEMultipart  # noqa: PLC0415
        from email.mime.text import MIMEText  # noqa: PLC0415
        try:
            msg = MIMEMultipart()
            msg["From"] = user
            msg["To"] = recipient
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))
            server = smtplib.SMTP("smtp.gmail.com", 587, timeout=10.0)
            try:
                server.starttls()
                server.login(user, pw)
                server.sendmail(user, recipient, msg.as_string())
            finally:
                server.quit()
            LOGGER.info("Email sent: %s", subject)
        except Exception as exc:
            LOGGER.error("Email send failed: %r", exc)

    return _send


class InterlockTCPServer(WaxxServer):
    """Threaded TCP server + UDP beacon for the InterlockService."""

    def __init__(
        self,
        service: InterlockService,
        *,
        host: str = "0.0.0.0",
        port: int = _DEFAULT_PORT,
    ):
        WaxxServer.__init__(self, "interlock", port)
        self._service = service
        self._host = host
        self._port = int(port)
        self._sock: Optional[socket.socket] = None
        self._accept_thread: Optional[threading.Thread] = None
        self._running = False

    # ------------------------------------------------------------------

    def start(self) -> None:
        # Bind FIRST so the dashboard can connect even while the service
        # is still validating config (transparency rule).
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self._host, self._port))
        sock.listen(8)
        sock.settimeout(1.0)
        self._sock = sock
        self._port = sock.getsockname()[1]
        self._waxx_port = self._port
        LOGGER.info("Interlock TCP listening on %s:%s (log=%s)",
                    self._host, self._port, _LOG_PATH)
        self._start_beacon()
        self._running = True
        self._accept_thread = threading.Thread(
            target=self._accept_loop, name="ilock-accept", daemon=True
        )
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

    # ------------------------------------------------------------------

    def _accept_loop(self) -> None:
        while self._running:
            try:
                client, addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                if self._running:
                    LOGGER.exception("accept failed")
                break
            threading.Thread(
                target=self._handle_client,
                args=(client, addr),
                daemon=True,
            ).start()

    def _handle_client(self, client: socket.socket, addr) -> None:
        client_label = f"{addr[0]}:{addr[1]}" if addr else "?"
        try:
            client.settimeout(5.0)
            data = client.recv(4096).decode("utf-8", errors="replace").strip()
            if not data:
                return
            response = self._dispatch(data, client_label)
            client.sendall((response + "\n").encode("utf-8"))
        except Exception:
            LOGGER.exception("client error (%s)", client_label)
        finally:
            try:
                client.close()
            except OSError:
                pass

    def _dispatch(self, raw: str, client_addr: str) -> str:
        cmd = raw.strip().upper()
        # Don't log snapshot polls (would spam at 1 Hz).
        if cmd != "GET_SNAPSHOT":
            LOGGER.info("RPC: %s from %s", cmd, client_addr)
        try:
            if cmd == "GET_SNAPSHOT":
                return json.dumps(self._service.get_snapshot())
            if cmd == "RESET_INTERLOCK":
                return json.dumps(self._service.reset_interlock(client_addr))
            if cmd == "ENABLE_MAGNETS":
                return json.dumps(self._service.enable_magnets(client_addr))
            if cmd == "DISABLE_MAGNETS":
                return json.dumps(self._service.disable_magnets(client_addr))
            if cmd == "FLUSH_CSV":
                self._service.flush_csv()
                return json.dumps({"status": "ok"})
            return json.dumps({"status": "error", "message": f"unknown command: {cmd}"})
        except Exception as exc:
            LOGGER.exception("RPC handler raised for %s", cmd)
            return json.dumps({"status": "error", "message": repr(exc)})


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------

def main() -> int:
    LOGGER.info("Interlock server starting (pid=%d host=%s)",
                os.getpid(), socket.gethostname())

    data_dir = os.environ.get("data") or os.environ.get("DATA_DIR") or ""
    csv_path = os.path.join(data_dir, "interlock_logs", "plot_data.csv") if data_dir else ""
    heartbeat_path = os.path.join(data_dir, "_logs", "interlock_heartbeat.txt") if data_dir else ""

    cfg = InterlockConfig(
        com_port="COM5",
        com_baud=9600,
        stale_threshold_s=15.0,
        warmup_seconds=20.0,
        csv_path=csv_path or None,
        heartbeat_path=heartbeat_path or None,
        email_credentials_filepath=INTERLOCK_EMAIL_CREDENTIALS_FILEPATH,
    )

    try:
        relay = EthernetRelay()
    except Exception:
        LOGGER.exception("Could not instantiate EthernetRelay; aborting startup")
        return _sm.EXIT_BAD_CONFIG

    email_sender = _build_email_sender()
    service = InterlockService(relay, cfg, email_sender=email_sender)
    started = service.start()
    if not started:
        LOGGER.critical("Service failed to start (singleton mutex held by another process)")
        return _sm.EXIT_ALREADY_RUNNING

    tcp = InterlockTCPServer(service)
    tcp.start()

    # Signal handling for clean shutdown.
    stop_event = threading.Event()

    def _sig(_signum, _frame):
        LOGGER.info("Signal received; shutting down")
        stop_event.set()

    try:
        signal.signal(signal.SIGINT, _sig)
        signal.signal(signal.SIGTERM, _sig)
    except Exception:
        pass

    try:
        # CSV flush every 10 minutes (matches original cadence).
        while not stop_event.wait(600.0):
            service.flush_csv()
    except KeyboardInterrupt:
        pass
    finally:
        LOGGER.info("Shutting down")
        try:
            tcp.stop()
        finally:
            service.stop()
    return _sm.EXIT_NORMAL


if __name__ == "__main__":
    sys.exit(main())
