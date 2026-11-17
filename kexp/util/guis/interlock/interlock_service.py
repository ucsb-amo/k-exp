"""InterlockService — Qt-free safety-critical service for the K interlock.

This is the secondary safety layer (the PLC hardware interlock is primary).
Owns ALL serial I/O on COM5 and ALL ``EthernetRelay`` calls.  Implements the
15 IT mitigations described in the implementation plan.

Threading model
---------------
* Main poll thread: reads PLC stream, parses, updates ``last_valid_data_time``,
  triggers ``_trip()`` on stale data or explicit "I TRIPPED" message.
* Watchdog thread (IT2): every 5 s, checks main poll thread updated
  ``last_loop_iteration_monotonic`` within the last 10 s.  If not, calls
  ``_emergency_trip()`` and ``os._exit(EXIT_WATCHDOG)``.
* Heartbeat thread (IT14): every 5 s writes liveness info to a heartbeat file.
* Trip-execution: the ``_kill_magnets_persistent`` loop runs on its own thread
  (called once per trip event) so it does not block the poll thread.
* Email thread (IT5): a single-worker ``ThreadPoolExecutor`` queue.
* History thread: appends every good sample to ``<history_dir>/YYYY-MM-DD.csv``
  (``waxx.util.daily_csv``).  The poll thread only queues the row; it never
  waits on the file.

Locks
-----
* ``_relay_lock`` — serializes all ``EthernetRelay`` calls.
* ``_state_lock`` — guards mutable status fields read by ``get_snapshot()``.
* No lock is ever held across a sleep or an RPC entry/exit.

Safety invariants (must always hold; see plan §"Safety invariants")
1. Server crash → magnets stay off if previously tripped (relay state
   persists in hardware; restart never auto-enables).
2. PLC "I TRIPPED" → ``_trip()`` within 1 s.
3. PLC silence > ``stale_threshold_s`` → ``_trip()``.
4. COM5 unplugged → counts as "data stopped" (so does the COM link held
   by a person's Disconnect, in error, or reconnecting).
4a. COM5 missing at startup → magnets killed once; the COM link keeps
   retrying the port; Enable is refused until a good PLC frame arrives.
   A reconnect never enables the magnets or resets the interlock.
5. Relay unreachable when trip needed → retry forever, ``CRITICAL`` every 10
   attempts.  PLC hardware interlock is backstop.
5a. Relay not answering (at startup or later) → the server keeps running and
   reports ``state="relay_down"`` (address + since when) in the snapshot;
   Enable is refused until it answers.  A background thread re-checks it;
   when it answers the magnet relay is left as it is (as at a normal
   startup), except a startup kill owed for a missing COM port is done then.
6. Reset has no effect if PLC still reports trip.
7. Email never blocks the trip (queued to background executor).
8. No silent failure path: every trip-suppressing branch logs ``WARNING``+.
"""

from __future__ import annotations

import codecs
import concurrent.futures
import csv
import logging
import os
import re
import socket
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

# sympy is heavy; reproduce the checksum-prime check inline to avoid the dep.
# Original code used sympy.ntheory.factorint(received_valid_data).keys().

import serial
import serial.tools.list_ports

from waxx.util.comms_server.com_link import ComLink, ComLinkRefused
from waxx.util.daily_csv import DailyCsvLog
from kexp.util.guis.interlock import interlock_safe_mode as _sm


_LOG = logging.getLogger("kexp.dashboard.server.interlock")
_COM_LOG = logging.getLogger("kexp.dashboard.server.interlock.com")


# PLC stream checksum primes (one per expected message type).  Identical to
# the values in the original interlock_gui.py.
_CHECKSUM_PRIMES = (2, 3, 5, 7, 11)

# Magnet-status read done from get_snapshot(): one attempt, short timeout,
# so the RPC answers well inside the GUI client's 1.5 s budget.
_SNAPSHOT_RELAY_RETRIES = 0
_SNAPSHOT_RELAY_TIMEOUT_S = 0.5
# ...and at most this often.  Every GUI/dashboard poll used to open a fresh
# TCP connection to the relay board (>1/s across pollers); the board then
# intermittently took >0.5 s to accept, and each miss logged an ERROR.
# Service-initiated enable/kill force a fresh read on the next snapshot.
_SNAPSHOT_RELAY_MIN_INTERVAL_S = 5.0
# Startup relay read: a few short attempts, so the server is up and answering
# the panel within seconds when the relay does not answer (a refused connect
# takes ~2 s on Windows unless the timeout cuts it short).
_STARTUP_RELAY_RETRIES = 2
_STARTUP_RELAY_TIMEOUT_S = 1.0
# The relay is reported down after this many failed contacts in a row (one
# slow accept is not an outage); one success clears it.
_RELAY_DOWN_AFTER_FAILURES = 2
# While it is reported down, a background thread re-checks it this often.
_RELAY_RECHECK_INTERVAL_S = 5.0

# Daily history files.  temperature_plc_k is the PLC's reading as sent;
# temperature_c is the value shown on the panel (plc_k - 273.0, the
# conversion the original GUI used).
_HISTORY_HEADER = ("epoch", "local_time", "temperature_plc_k", "temperature_c",
                   "flow1_v", "flow2_v", "flow3_v", "flow4_v", "plc_tripped")


def _ints_factor_into(n: int, primes: tuple[int, ...]) -> bool:
    """Return True if every prime in *primes* divides *n*."""
    if n <= 0:
        return False
    for p in primes:
        if n % p != 0:
            return False
    return True


@dataclass
class InterlockConfig:
    """Static configuration; constructed once at startup."""
    com_port: str = "COM5"
    com_baud: int = 9600
    com_timeout_s: float = 1.0
    stale_threshold_s: float = 15.0
    warmup_seconds: float = 20.0
    watchdog_loop_grace_s: float = 10.0
    watchdog_check_interval_s: float = 5.0
    heartbeat_interval_s: float = 5.0
    csv_path: Optional[str] = None
    history_dir: Optional[str] = None
    history_flush_interval_s: float = 10.0
    heartbeat_path: Optional[str] = None
    email_recipient: Optional[str] = None
    email_credentials_filepath: Optional[str] = None
    reset_debounce_s: float = 5.0
    relay_label: str = "ethernet relay"   # shown in the relay-down message


@dataclass
class _Sample:
    """One PLC message worth of structured readings."""
    epoch: float
    temperature_k: Optional[float] = None   # as the PLC sent it
    temperature_c: Optional[float] = None
    flow_v: dict[int, float] = field(default_factory=dict)
    plc_tripped: bool = False


class InterlockService:
    """Headless safety service; no Qt, no UI."""

    # ------------------------------------------------------------------
    # Construction / lifecycle
    # ------------------------------------------------------------------

    def __init__(
        self,
        relay,                                # kexp.EthernetRelay (duck-typed)
        config: InterlockConfig,
        *,
        email_sender: Optional[Callable[[str, str], None]] = None,
    ):
        self._relay = relay
        self._cfg = config
        self._email_sender = email_sender   # callable(subject, body) -> None

        # Mutable state guarded by _state_lock.
        self._state_lock = threading.Lock()
        self._state = _sm.STATE_UNKNOWN
        self._message = "initializing"
        self._last_sample: Optional[_Sample] = None
        self._last_reset_monotonic: float = 0.0
        self._safe_mode_reason: Optional[str] = None
        self._consecutive_stale_windows = 0
        self._has_emailed_for_current_outage = False

        # Monotonic timers (IT8 - clock-jump immunity).
        self._last_valid_data_monotonic = time.monotonic()
        self._last_loop_iteration_monotonic = time.monotonic()
        self._service_started_monotonic = time.monotonic()
        self._warmup_active = True

        # Serial.  Owned by self._link (created at the end of __init__), which
        # opens it on its own thread and reopens it on its backoff.  The link
        # holds _serial_lock (re-entrant: the link's io_lock) while it opens
        # or closes the port, so a close never lands mid-read.
        self._serial_lock = threading.RLock()
        # False while the port did not enumerate at startup and has not been
        # opened since (snapshot "com"["config_valid"]).
        self._com_config_valid = True
        # Beacon forwarding: the link reports its state to this service
        # (set_com_state); the TCP server, attached later, beacons it.
        self._beacon_server = None
        self._com_beacon_state: Optional[tuple[str, Optional[str]]] = None

        # Relay lock.
        self._relay_lock = threading.Lock()
        # Last magnet state actually read from the relay (by any path), so
        # get_snapshot() can answer without waiting on _relay_lock.
        self._magnets_enabled_cached: Optional[bool] = None
        self._magnets_read_monotonic: Optional[float] = None
        # Earliest time get_snapshot() may probe the relay again (successful
        # or not); 0 = probe on the next snapshot.
        self._next_snapshot_probe_monotonic: float = 0.0
        # Relay health, from the outcome of every relay call (startup read,
        # snapshot probe, kills, enables, re-checks); guarded by _state_lock.
        self._relay_failures = 0
        self._relay_error: Optional[str] = None
        self._relay_down_since: Optional[float] = None   # wall time; None = answering
        # COM port missing at startup while the relay was down: the startup
        # magnet kill is done when the relay first answers.
        self._startup_kill_owed = False
        self._relay_thread: Optional[threading.Thread] = None
        # At most one persistent-kill thread at a time (PLC repeats
        # "I TRIPPED" every frame while tripped).
        self._kill_thread: Optional[threading.Thread] = None
        self._kill_thread_lock = threading.Lock()

        # Threads.
        self._stop_event = threading.Event()
        self._poll_thread: Optional[threading.Thread] = None
        self._watchdog_thread: Optional[threading.Thread] = None
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._email_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="ilock-email"
        )

        # Mutex (IT3) - held for the process lifetime.
        self._win_mutex = None

        # Buffered samples for CSV (small; bounded).
        self._samples: list[_Sample] = []
        self._samples_lock = threading.Lock()
        self._samples_max = 4096

        # Append-only daily history (every good sample, kept indefinitely).
        self._history: Optional[DailyCsvLog] = None
        if config.history_dir:
            self._history = DailyCsvLog(
                config.history_dir, _HISTORY_HEADER,
                name="ilock-history", logger=_LOG,
            )

        # The PLC COM link (last: it reports its first state at once).
        self._link = _PLCLink(self)

    # --- COM link state -> beacon -------------------------------------

    def set_com_state(self, state: str, port: Optional[str] = None) -> None:
        """The link's state changes land here (ComLink ``server``); they are
        forwarded to the TCP server's beacon once it is attached."""
        self._com_beacon_state = (state, port)
        server = self._beacon_server
        if server is not None:
            server.set_com_state(state, port)

    def attach_beacon_server(self, server) -> None:
        """Advertise the COM link's state in *server*'s beacon
        (``NetServer.set_com_state``) from now on, starting with the current one."""
        self._beacon_server = server
        current = self._com_beacon_state
        if current is not None:
            server.set_com_state(*current)

    # --- mutex (Windows only; degrades gracefully on other OSes) -----

    def acquire_singleton_mutex(self) -> bool:
        """IT3: prevent two interlock servers from running simultaneously."""
        if sys.platform != "win32":
            _LOG.warning("Singleton mutex only enforced on Windows; running on %s", sys.platform)
            return True
        try:
            import ctypes  # noqa: PLC0415
            from ctypes import wintypes  # noqa: PLC0415
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            CreateMutex = kernel32.CreateMutexW
            CreateMutex.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
            CreateMutex.restype = wintypes.HANDLE
            ERROR_ALREADY_EXISTS = 183
            handle = CreateMutex(None, True, "Global\\kexp_interlock_server")
            last = ctypes.get_last_error()
            if not handle:
                _LOG.critical("CreateMutex failed; cannot enforce singleton (err=%d)", last)
                return False
            if last == ERROR_ALREADY_EXISTS:
                _LOG.critical("Another interlock_server is already running (mutex held)")
                kernel32.CloseHandle(handle)
                return False
            self._win_mutex = handle
            return True
        except Exception:
            _LOG.exception("Singleton mutex check raised; refusing to start for safety")
            return False

    def release_singleton_mutex(self) -> None:
        if self._win_mutex is None:
            return
        try:
            import ctypes  # noqa: PLC0415
            ctypes.WinDLL("kernel32").CloseHandle(self._win_mutex)
        except Exception:
            _LOG.exception("Releasing singleton mutex failed (continuing)")
        self._win_mutex = None

    # --- startup validation (IT15) -----------------------------------

    def com_port_missing_reason(self) -> Optional[str]:
        """None if the configured COM port enumerates; else a short reason
        (also when the port list cannot be read: the stricter answer)."""
        try:
            ports = {p.device for p in serial.tools.list_ports.comports()}
        except Exception as exc:
            return f"{_sm.REASON_BAD_COM_PORT}: port list unreadable ({exc!r})"
        if self._cfg.com_port not in ports:
            return f"{_sm.REASON_BAD_COM_PORT}: {self._cfg.com_port} not in {sorted(ports)}"
        return None

    def enter_safe_mode(self, reason: str) -> None:
        """IT15: refuse to operate; try once to drop magnets.  Nothing calls
        this at present (a relay that does not answer is ``relay_down``)."""
        _LOG.critical("Entering SAFE MODE: %s", reason)
        with self._state_lock:
            self._state = _sm.STATE_SAFE_MODE
            self._message = reason
            self._safe_mode_reason = reason
        # Best-effort one-shot magnet kill.
        try:
            with self._relay_lock:
                self._relay.kill_magnets()
            _LOG.critical("Safe-mode magnet kill: success")
        except Exception:
            _LOG.exception("Safe-mode magnet kill: FAILED — hardware interlock is sole defense")

    def _kill_magnets_without_com(self, reason: str) -> None:
        """COM port missing at startup: drop the magnets once, exactly as safe
        mode did, but keep running -- the COM link keeps retrying the port.
        Enable stays refused until a good PLC frame arrives (warmup)."""
        _LOG.critical("COM port missing at startup (%s): killing magnets once; the COM "
                      "link keeps retrying, and Enable is refused until PLC data flows", reason)
        try:
            with self._relay_lock:
                self._relay.kill_magnets()
            self._note_relay_ok()
            _LOG.critical("Startup magnet kill (no COM port): success")
        except Exception as exc:
            self._note_relay_failed(exc)
            _LOG.exception("Startup magnet kill (no COM port): FAILED — hardware interlock "
                           "is sole defense")
        self._next_snapshot_probe_monotonic = 0.0

    # --- relay health ---------------------------------------------------

    def _note_relay_ok(self) -> None:
        with self._state_lock:
            was_down = self._relay_down_since is not None
            self._relay_failures = 0
            self._relay_error = None
            self._relay_down_since = None
        if was_down:
            _LOG.warning("Relay %s is answering again", self._cfg.relay_label)

    def _note_relay_failed(self, exc: BaseException, *, down_now: bool = False) -> None:
        """Count a failed relay contact; report the relay down after
        ``_RELAY_DOWN_AFTER_FAILURES`` in a row (or at once with *down_now*)."""
        with self._state_lock:
            self._relay_failures += 1
            self._relay_error = repr(exc)
            newly_down = (self._relay_down_since is None
                          and (down_now or self._relay_failures >= _RELAY_DOWN_AFTER_FAILURES))
            if newly_down:
                self._relay_down_since = time.time()
        if newly_down:
            _LOG.critical(
                "RELAY NOT ANSWERING (%s): %r.  Magnet relay state unknown; the software "
                "cannot switch the magnets until it answers (the PLC hardware interlock "
                "still can).  Enable is refused meanwhile; re-checking every %.0f s.",
                self._cfg.relay_label, exc, _RELAY_RECHECK_INTERVAL_S)
        else:
            _LOG.debug("relay contact failed: %r", exc)

    def _relay_recheck_loop(self) -> None:
        """While the relay is reported down (or the startup kill is owed),
        try it once every ``_RELAY_RECHECK_INTERVAL_S`` with one short
        attempt.  When it answers: the owed startup kill if any, else the
        magnet relay is left as it is (as at a normal startup, IT10)."""
        while not self._stop_event.wait(_RELAY_RECHECK_INTERVAL_S):
            with self._state_lock:
                down = self._relay_down_since is not None
            if not (down or self._startup_kill_owed):
                continue
            if not self._relay_lock.acquire(timeout=1.0):
                continue   # a kill/enable holds it; its outcome is noted there
            try:
                enabled = bool(self._relay.read_magnet_status(
                    retries=0, timeout=_STARTUP_RELAY_TIMEOUT_S))
                if self._startup_kill_owed:
                    self._relay.kill_magnets()
                    enabled = bool(self._relay.read_magnet_status(
                        retries=0, timeout=_STARTUP_RELAY_TIMEOUT_S))
                    if not enabled:
                        self._startup_kill_owed = False
                        _LOG.critical("Startup magnet kill (no COM port at startup), "
                                      "done once the relay answered: success")
            except Exception as exc:
                self._note_relay_failed(exc)
            else:
                self._note_relay_ok()
                self._note_magnet_status(enabled)
                self._next_snapshot_probe_monotonic = 0.0
            finally:
                self._relay_lock.release()

    # --- start / stop -----------------------------------------------

    def start(self) -> bool:
        """Begin polling.  Returns True on success.  Never waits for the COM
        port (the link opens it in the background) and waits only a few
        seconds for the relay (a relay that does not answer is reported as
        ``relay_down``, and the service runs anyway)."""
        if not self.acquire_singleton_mutex():
            return False
        com_missing = self.com_port_missing_reason()
        if com_missing is not None:
            self._com_config_valid = False
        try:
            with self._relay_lock:
                relay_state = self._relay.read_magnet_status(
                    retries=_STARTUP_RELAY_RETRIES, timeout=_STARTUP_RELAY_TIMEOUT_S)
            relay_exc = None
        except Exception as exc:
            relay_exc = exc

        if relay_exc is not None:
            self._note_relay_failed(relay_exc, down_now=True)
            if com_missing is not None:
                self._startup_kill_owed = True
                _LOG.critical("COM port missing at startup (%s) and the relay is not "
                              "answering: the startup magnet kill is done when the relay "
                              "answers", com_missing)
        elif com_missing is not None:
            self._note_relay_ok()
            self._kill_magnets_without_com(com_missing)
        else:
            # Preserve current magnet state (IT10) — do NOT auto-enable.
            self._note_relay_ok()
            self._note_magnet_status(relay_state)
            _LOG.info("Startup: current relay magnet-enabled state preserved as %s", relay_state)

        # Treat the warmup window (IT11): require fresh PLC data within
        # warmup_seconds, else trip.  Mark warmup active.
        with self._state_lock:
            self._warmup_active = True
            self._last_valid_data_monotonic = time.monotonic()
            self._state = _sm.STATE_WARMUP
            self._message = f"warmup ({self._cfg.warmup_seconds:.0f}s)"
            if com_missing is not None:
                self._message += f"; {self._cfg.com_port} missing at startup, magnets killed"

        self._stop_event.clear()
        self._poll_thread = threading.Thread(
            target=self._poll_loop, name="ilock-poll", daemon=True
        )
        self._poll_thread.start()
        self._link.start()
        self._relay_thread = threading.Thread(
            target=self._relay_recheck_loop, name="ilock-relay", daemon=True
        )
        self._relay_thread.start()
        self._start_watchdog_and_heartbeat()
        if self._history is not None:
            self._history.start(self._cfg.history_flush_interval_s)
            _LOG.info("Appending PLC samples to %s/YYYY-MM-DD.csv every %.0f s",
                      self._cfg.history_dir, self._cfg.history_flush_interval_s)
        _LOG.info("InterlockService started (com=%s baud=%s)", self._cfg.com_port, self._cfg.com_baud)
        return True

    def _start_watchdog_and_heartbeat(self) -> None:
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop, name="ilock-watchdog", daemon=True
        )
        self._watchdog_thread.start()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, name="ilock-heartbeat", daemon=True
        )
        self._heartbeat_thread.start()

    def stop(self) -> None:
        _LOG.info("InterlockService stopping")
        self._stop_event.set()
        if self._poll_thread is not None:
            self._poll_thread.join(timeout=3.0)
        if self._relay_thread is not None:
            self._relay_thread.join(timeout=3.0)
        if self._watchdog_thread is not None:
            self._watchdog_thread.join(timeout=2.0)
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=2.0)
        if self._history is not None:
            self._history.stop(timeout=3.0)   # final flush of queued samples
        try:
            self._email_executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        self._link.stop()
        self.release_singleton_mutex()
        _LOG.info("InterlockService stopped")

    # ------------------------------------------------------------------
    # Snapshot (read-only; safe to call from any thread)
    # ------------------------------------------------------------------

    def _note_magnet_status(self, enabled) -> None:
        self._magnets_enabled_cached = bool(enabled)
        self._magnets_read_monotonic = time.monotonic()

    def get_snapshot(self) -> dict:
        now = time.monotonic()
        with self._state_lock:
            sample = self._last_sample
            state = self._state
            message = self._message
            warmup = self._warmup_active
            last_data_age = now - self._last_valid_data_monotonic
            safe_reason = self._safe_mode_reason
        com = self._com_snapshot()
        reconnect_attempts = com["reconnect_attempts"]
        # Read magnet state best-effort; never block trip path.  If the relay
        # is busy (a kill in progress) report the last value actually read,
        # with its age, instead of queueing behind it -- queueing made the
        # GUI's 1.5 s RPC time out during trips and hid the TRIPPED state.
        # A snapshot read is single-shot with a short timeout so it can never
        # hold _relay_lock long enough to delay a kill.  Probes are rate
        # limited (_SNAPSHOT_RELAY_MIN_INTERVAL_S); in between, the cached
        # value and its age are reported.
        if (now >= self._next_snapshot_probe_monotonic
                and self._relay_lock.acquire(blocking=False)):
            self._next_snapshot_probe_monotonic = now + _SNAPSHOT_RELAY_MIN_INTERVAL_S
            try:
                self._note_magnet_status(self._relay.read_magnet_status(
                    retries=_SNAPSHOT_RELAY_RETRIES, timeout=_SNAPSHOT_RELAY_TIMEOUT_S))
                self._note_relay_ok()
            except Exception as exc:
                # Counted; the transition to "down" is logged once.  Cached
                # magnet state is reported with its age meanwhile.
                self._note_relay_failed(exc)
            finally:
                self._relay_lock.release()
        magnets_enabled = self._magnets_enabled_cached
        read_at = self._magnets_read_monotonic
        magnets_age = round(time.monotonic() - read_at, 2) if read_at is not None else None
        with self._state_lock:
            relay_down_since = self._relay_down_since
            relay_error = self._relay_error
        # The relay note takes the place of ok / warmup / unknown; a trip (or
        # safe mode) keeps its state and gets the note appended.
        shown_state, shown_message = state, message
        if relay_down_since is not None:
            note = (f"relay {self._cfg.relay_label} not answering since "
                    f"{time.strftime('%H:%M:%S', time.localtime(relay_down_since))}; "
                    "the software cannot switch the magnets")
            if state in (_sm.STATE_OK, _sm.STATE_WARMUP, _sm.STATE_UNKNOWN):
                shown_state = _sm.STATE_RELAY_DOWN
                shown_message = note if state == _sm.STATE_OK else f"{note}; {message}"
            else:
                shown_message = f"{message}; {note}"
        return {
            "com": com,
            # ok | tripped | warmup | relay_down | safe_mode | unknown
            "state": shown_state,
            "message": shown_message,
            "interlock_state": state,          # state without the relay note
            "relay_ok": relay_down_since is None,
            "relay_down_since": relay_down_since,   # epoch s, None while answering
            "relay_error": relay_error,        # last failed contact (cleared on success)
            "safe_mode_reason": safe_reason,
            "last_data_age_s": round(last_data_age, 2),
            "stale_threshold_s": self._cfg.stale_threshold_s,
            "warmup_active": warmup,
            "magnets_enabled": magnets_enabled,
            "magnets_status_age_s": magnets_age,   # None = never read
            "reconnect_attempts": reconnect_attempts,
            "uptime_s": round(now - self._service_started_monotonic, 1),
            "temperature_c": sample.temperature_c if sample else None,
            "flow_v": dict(sample.flow_v) if sample else {},
            "plc_tripped": sample.plc_tripped if sample else False,
        }

    def _com_snapshot(self) -> dict:
        """Serial-link summary: ``ComLink.snapshot()`` (``SerialSnapshot``
        shape plus ``held``).

        Never queues behind the poll thread's ``_serial_lock`` (held during a
        blocking read) and never affects the trip path.  ``config_valid`` is
        False while the port did not enumerate at startup and has not been
        opened since.
        """
        com = self._link.snapshot()
        com["config_valid"] = bool(self._com_config_valid)
        return com

    # ------------------------------------------------------------------
    # RPC entry points (call from server thread; no locks held across these)
    # ------------------------------------------------------------------

    def reset_interlock(self, client_addr: str = "?") -> dict:
        """IT9: reset PLC trip.  Debounced and refused if PLC still tripped."""
        with self._state_lock:
            if self._state == _sm.STATE_SAFE_MODE:
                _LOG.warning("reset refused (safe mode) from %s", client_addr)
                return {"status": "refused", "reason": "safe_mode", "message": self._safe_mode_reason or ""}
            now = time.monotonic()
            if now - self._last_reset_monotonic < self._cfg.reset_debounce_s:
                _LOG.info("reset debounced from %s", client_addr)
                return {"status": "ignored", "reason": "debounce"}
            last_plc_tripped = bool(self._last_sample and self._last_sample.plc_tripped)
            if last_plc_tripped:
                _LOG.warning("reset refused (PLC still tripped) from %s", client_addr)
                return {"status": "refused", "reason": "plc_still_tripped"}
            self._last_reset_monotonic = now
        # Send 'O' over serial.
        try:
            with self._serial_lock:
                ser = self._link.device
                if ser is None or not ser.is_open:
                    raise IOError(f"serial port not open ({self._link.state})")
                ser.write(b"O")
            _LOG.info("reset_interlock issued by %s (wrote 'O' to PLC)", client_addr)
            with self._state_lock:
                self._has_emailed_for_current_outage = False
            return {"status": "ok"}
        except Exception as exc:
            _LOG.exception("reset_interlock write failed")
            return {"status": "error", "message": repr(exc)}

    def enable_magnets(self, client_addr: str = "?") -> dict:
        """IT10: explicit RPC; refused in safe mode, while tripped, or before
        the first good PLC frame since startup (warmup)."""
        with self._state_lock:
            if self._state == _sm.STATE_SAFE_MODE:
                return {"status": "refused", "reason": "safe_mode"}
            if self._state == _sm.STATE_TRIPPED:
                return {"status": "refused", "reason": "tripped"}
            if self._relay_down_since is not None:
                return {"status": "refused", "reason": "relay_not_answering",
                        "message": f"relay {self._cfg.relay_label} is not answering"}
            if self._warmup_active:
                return {"status": "refused", "reason": "no_plc_data",
                        "message": "no good PLC frame received since startup"}
            last_plc_tripped = bool(self._last_sample and self._last_sample.plc_tripped)
        if last_plc_tripped:
            return {"status": "refused", "reason": "plc_still_tripped"}
        try:
            with self._relay_lock:
                self._relay.enable_magnets()
            self._note_relay_ok()
            self._next_snapshot_probe_monotonic = 0.0
            _LOG.info("enable_magnets executed (requested by %s)", client_addr)
            return {"status": "ok"}
        except Exception as exc:
            self._note_relay_failed(exc)
            _LOG.exception("enable_magnets failed")
            return {"status": "error", "message": repr(exc)}

    def disable_magnets(self, client_addr: str = "?") -> dict:
        """Manual magnet kill.  Always allowed."""
        try:
            with self._relay_lock:
                self._relay.kill_magnets()
            self._note_relay_ok()
            self._next_snapshot_probe_monotonic = 0.0
            _LOG.warning("disable_magnets executed by %s", client_addr)
            return {"status": "ok"}
        except Exception as exc:
            self._note_relay_failed(exc)
            _LOG.exception("disable_magnets failed")
            return {"status": "error", "message": repr(exc)}

    def com_connect(self, client_addr: str = "?") -> dict:
        """Dashboard Connect: release a held COM port and open it now.

        Touches nothing else: the interlock state, the trip latch and the
        magnets stay exactly as they are (data resumes on the next frame)."""
        with self._state_lock:
            if self._state == _sm.STATE_SAFE_MODE:
                _LOG.warning("COM connect refused (safe mode) from %s", client_addr)
                return {"status": "refused", "reason": "safe_mode",
                        "message": f"safe mode: {self._safe_mode_reason or ''}"}
        self._link.connect()
        _LOG.warning("COM connect requested by %s (%s)", client_addr, self._cfg.com_port)
        return {"status": "ok", "message": f"connecting {self._cfg.com_port}"}

    def com_disconnect(self, client_addr: str = "?") -> dict:
        """Dashboard Disconnect: close the COM port and hold it closed.

        Refused unless the relay reads the magnets disabled
        (``_com_disconnect_refusal``).  While held there is no PLC data, so
        the staleness check trips the interlock after ``stale_threshold_s``."""
        try:
            self._link.disconnect(hold=True)
        except ComLinkRefused as exc:
            _LOG.warning("COM disconnect refused from %s: %s", client_addr, exc)
            return {"status": "refused", "reason": "disconnect_refused", "message": str(exc)}
        except Exception as exc:
            _LOG.exception("COM disconnect failed")
            return {"status": "error", "message": repr(exc)}
        _LOG.warning("COM port %s disconnected and HELD by %s: no PLC data until Connect; "
                     "the interlock trips after %.0f s without data",
                     self._cfg.com_port, client_addr, self._cfg.stale_threshold_s)
        return {"status": "ok", "message": f"{self._cfg.com_port} disconnected and held"}

    def _com_disconnect_refusal(self) -> Optional[str]:
        """Why the COM port may not be disconnected now, or None.

        The authority on "magnets enabled" is the relay's magnet-inhibit
        channel (``EthernetRelay.read_magnet_status``) -- the PLC stream
        carries no magnet state -- so it is read fresh here.  When it cannot
        be read, the disconnect is refused too (the stricter answer)."""
        if not self._relay_lock.acquire(timeout=_SNAPSHOT_RELAY_TIMEOUT_S):
            return ("magnet state unknown (relay busy; a magnet kill may be in progress): "
                    "cannot confirm the magnets are disabled, so the interlock's COM port "
                    "stays connected")
        try:
            enabled = bool(self._relay.read_magnet_status(
                retries=_SNAPSHOT_RELAY_RETRIES, timeout=_SNAPSHOT_RELAY_TIMEOUT_S))
        except Exception as exc:
            self._note_relay_failed(exc)
            return (f"magnet state unknown (relay read failed: {exc!r}): cannot confirm the "
                    "magnets are disabled, so the interlock's COM port stays connected")
        finally:
            self._relay_lock.release()
        self._note_relay_ok()
        self._note_magnet_status(enabled)
        if enabled:
            return ("magnets are enabled: disable them before disconnecting the "
                    "interlock's COM port")
        return None

    def _on_com_connected(self) -> None:
        """The link opened the port (first time or reconnect).  Bookkeeping
        only: never enables the magnets, never resets the interlock, never
        refreshes the staleness clock (only a good PLC frame does)."""
        self._com_config_valid = True

    # ------------------------------------------------------------------
    # Internal: poll loop
    # ------------------------------------------------------------------

    def _open_serial(self) -> serial.Serial:
        """Open the PLC port (the link's ``_open``; runs on the link's thread
        with ``_serial_lock`` held).  Raises on failure; the link retries."""
        _COM_LOG.info("Open attempt: port=%s baud=%s", self._cfg.com_port, self._cfg.com_baud)
        t0 = time.monotonic()
        try:
            ser = serial.Serial(
                port=self._cfg.com_port,
                baudrate=self._cfg.com_baud,
                timeout=self._cfg.com_timeout_s,
            )
        except Exception as exc:
            _COM_LOG.error("Open failure: port=%s exc=%r", self._cfg.com_port, exc)
            raise
        _COM_LOG.info("Open success: port=%s elapsed_ms=%d",
                      self._cfg.com_port, int(1000 * (time.monotonic() - t0)))
        return ser

    def _poll_loop(self) -> None:
        # The COM port is opened (and reopened) by self._link on its own thread.
        while not self._stop_event.is_set():
            self._last_loop_iteration_monotonic = time.monotonic()
            try:
                self._poll_once()
            except Exception:
                _LOG.exception("poll_once raised; continuing")
            # Sleep a short interval; the PLC sends at its own rate.
            self._stop_event.wait(0.25)

    def _poll_once(self) -> None:
        # Read up to 200 bytes (mirrors original code).
        buffer = b""
        read_exc: Optional[BaseException] = None
        if self._link.device is None:
            # Port not open (connecting / error / held): the link reopens it on
            # its own thread.  Wait as long as a silent read would, so the
            # loop keeps its timing, then count this cycle as "no data".
            self._stop_event.wait(self._cfg.com_timeout_s)
        else:
            with self._serial_lock:
                ser = self._link.device   # re-read: a close may have landed
                if ser is not None:
                    try:
                        if not ser.is_open:
                            raise IOError("serial port closed")
                        buffer = ser.read(200)
                    except Exception as exc:
                        _COM_LOG.error("read failure: %r", exc)
                        read_exc = exc
        if read_exc is not None:
            self._link.report_error(read_exc, where="read")   # closes; link reopens
        if buffer:
            self._link.note_rx()
        if not buffer:
            # No data this cycle — check stale (the link handles reopening).
            self._check_stale()
            return

        sample = self._parse_plc_buffer(buffer)
        if sample is None:
            # Bad/incomplete frame; counted toward stale, not toward "good".
            _LOG.warning("PLC frame failed checksum; not refreshing last_valid_data")
            self._check_stale()
            return

        # We have a good frame.
        with self._state_lock:
            self._last_valid_data_monotonic = time.monotonic()
            self._last_sample = sample
            self._consecutive_stale_windows = 0
            # Exit warmup on first good frame.
            if self._warmup_active:
                self._warmup_active = False
                self._state = _sm.STATE_OK
                self._message = "monitoring"
                _LOG.info("Warmup complete; first good PLC frame received")
            elif self._state == _sm.STATE_UNKNOWN:
                self._state = _sm.STATE_OK
                self._message = "monitoring"

        # Save sample for CSV buffer.
        with self._samples_lock:
            self._samples.append(sample)
            if len(self._samples) > self._samples_max:
                self._samples = self._samples[-self._samples_max:]
        if self._history is not None:
            self._history.add(sample.epoch, _history_row(sample))

        # Did the PLC explicitly report tripped?
        if sample.plc_tripped:
            self._trip(reason="PLC reported I TRIPPED")

    def _parse_plc_buffer(self, buffer: bytes) -> Optional[_Sample]:
        # Mirror original parsing; produce structured _Sample only if checksum
        # primes are all hit (good frame).
        try:
            decoded = codecs.decode(buffer, "utf-8", errors="replace")
        except Exception:
            return None

        sample = _Sample(epoch=time.time())
        checksum = 1
        for segment in re.split(r"/", decoded):
            if "Flowmeter" in segment:
                m = re.search(r"Flowmeter (\d) reads ([\d\.]+)V", segment)
                if m:
                    meter = int(m.group(1))
                    if 1 <= meter <= len(_CHECKSUM_PRIMES) - 1:
                        checksum *= _CHECKSUM_PRIMES[meter - 1]
                        sample.flow_v[meter] = float(m.group(2))
            elif "Temp" in segment:
                m = re.search(r"Temp is ([\d\.]+)k", segment)
                if m:
                    checksum *= _CHECKSUM_PRIMES[4]
                    sample.temperature_k = float(m.group(1))
                    sample.temperature_c = sample.temperature_k - 273.0
            elif "TRIPPED" in segment:
                if re.search(r"I TRIPPED", segment):
                    sample.plc_tripped = True
                    # Original code set checksum to 2310 = 2*3*5*7*11 to bypass
                    # the prime check when PLC trips.  Preserve that.
                    checksum = 2310

        if not _ints_factor_into(checksum, _CHECKSUM_PRIMES):
            return None
        return sample

    def _check_stale(self) -> None:
        with self._state_lock:
            if self._state == _sm.STATE_SAFE_MODE:
                return
            age = time.monotonic() - self._last_valid_data_monotonic
            stale = age > self._cfg.stale_threshold_s
            if not stale:
                return
            self._consecutive_stale_windows += 1
        _LOG.error("PLC data stale: age=%.1fs threshold=%.1fs", age, self._cfg.stale_threshold_s)
        # _trip() will queue a single "K-Interlock Tripped" email containing
        # the stale-data reason; do not send a separate "PLC silence" email.
        self._trip(reason=f"no valid PLC data for {age:.1f}s")

    # ------------------------------------------------------------------
    # Trip path
    # ------------------------------------------------------------------

    def _trip(self, reason: str) -> None:
        with self._state_lock:
            already_tripped = self._state == _sm.STATE_TRIPPED
            self._state = _sm.STATE_TRIPPED
            self._message = reason
        if not already_tripped:
            _LOG.critical("TRIPPING INTERLOCK: %s", reason)
            self._queue_email("K-Interlock Tripped",
                              f"K interlock tripped: {reason}")
        # Spawn the persistent kill on a separate thread so the poll loop
        # keeps running (IT4: relay-unreachable retry must not freeze poll).
        # While one is still retrying, don't stack another: they would only
        # serialize on _relay_lock.  Once it has confirmed the kill, the next
        # "I TRIPPED" frame starts a fresh one (re-kills if re-enabled).
        with self._kill_thread_lock:
            if self._kill_thread is not None and self._kill_thread.is_alive():
                return
            self._kill_thread = threading.Thread(
                target=self._kill_magnets_persistent,
                name="ilock-trip",
                daemon=True,
            )
            self._kill_thread.start()

    def _kill_magnets_persistent(self) -> None:
        """IT4: retry forever with 200 ms gap; CRITICAL every 10 attempts."""
        attempt = 0
        t0 = time.monotonic()
        while not self._stop_event.is_set():
            attempt += 1
            try:
                with self._relay_lock:
                    self._relay.kill_magnets()
                    still_on = bool(self._relay.read_magnet_status())
                self._note_magnet_status(still_on)
                self._note_relay_ok()
                if not still_on:
                    _LOG.warning("Magnets confirmed killed after %d attempt(s) in %.2fs",
                                 attempt, time.monotonic() - t0)
                    return
            except Exception as exc:
                self._note_relay_failed(exc)
                if attempt % 10 == 0:
                    _LOG.critical(
                        "RELAY UNREACHABLE: %d attempts over %.1fs; latest: %r",
                        attempt, time.monotonic() - t0, exc,
                    )
            if self._stop_event.wait(0.2):
                return

    def _emergency_trip(self, reason: str) -> None:
        """Called by watchdog (IT2) and any other out-of-band trip path."""
        _LOG.critical("EMERGENCY TRIP: %s", reason)
        # Synchronous one-shot from this thread; watchdog will exit() after.
        try:
            with self._relay_lock:
                self._relay.kill_magnets()
        except Exception:
            _LOG.exception("Emergency trip relay call failed")

    # ------------------------------------------------------------------
    # Watchdog (IT2)
    # ------------------------------------------------------------------

    def _watchdog_loop(self) -> None:
        # First check after one full interval, so a slow start doesn't trip us.
        while not self._stop_event.wait(self._cfg.watchdog_check_interval_s):
            if self._poll_thread is None:
                # No poll loop was started (safe mode): nothing to watch.  It
                # used to "freeze" here and exit the server ~1 min after start.
                continue
            age = time.monotonic() - self._last_loop_iteration_monotonic
            if age <= self._cfg.watchdog_loop_grace_s:
                continue
            _LOG.critical("WATCHDOG: poll loop frozen for %.1fs (grace=%.1fs)",
                          age, self._cfg.watchdog_loop_grace_s)
            self._emergency_trip(_sm.REASON_WATCHDOG_FORCED)
            # Dump tracebacks of all threads to the log file so we can debug.
            try:
                import faulthandler  # noqa: PLC0415
                faulthandler.dump_traceback()
            except Exception:
                pass
            # Give logging a moment to flush, then exit hard for supervisor restart.
            time.sleep(1.0)
            os._exit(_sm.EXIT_WATCHDOG)

    # ------------------------------------------------------------------
    # Heartbeat (IT14)
    # ------------------------------------------------------------------

    def _heartbeat_loop(self) -> None:
        path = self._cfg.heartbeat_path
        if not path:
            return
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            _LOG.warning("Could not create heartbeat dir for %s", path)
            return
        while not self._stop_event.wait(self._cfg.heartbeat_interval_s):
            try:
                now = time.monotonic()
                snap = (
                    f"pid={os.getpid()}\n"
                    f"host={socket.gethostname()}\n"
                    f"uptime_s={now - self._service_started_monotonic:.1f}\n"
                    f"last_valid_data_age_s={now - self._last_valid_data_monotonic:.1f}\n"
                    f"state={self._state}\n"
                    f"timestamp={time.time():.0f}\n"
                )
                Path(path).write_text(snap)
            except Exception as exc:
                _LOG.warning("Heartbeat write failed: %r", exc)

    # ------------------------------------------------------------------
    # Email (IT5)
    # ------------------------------------------------------------------

    def _queue_email(self, subject: str, body: str) -> None:
        if self._email_sender is None:
            return
        try:
            self._email_executor.submit(self._email_sender, subject, body)
        except Exception:
            _LOG.exception("Email queueing failed (continuing)")

    # ------------------------------------------------------------------
    # CSV (IT7)
    # ------------------------------------------------------------------

    def flush_csv(self) -> None:
        """Best-effort: write current sample buffer to CSV.  IT7: never raises."""
        path = self._cfg.csv_path
        if not path:
            return
        try:
            with self._samples_lock:
                samples = list(self._samples)
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["epoch", "temperature_c", "flow1_v", "flow2_v", "flow3_v", "flow4_v", "plc_tripped"])
                for s in samples:
                    writer.writerow([
                        f"{s.epoch:.3f}",
                        "" if s.temperature_c is None else f"{s.temperature_c:.3f}",
                        s.flow_v.get(1, ""), s.flow_v.get(2, ""),
                        s.flow_v.get(3, ""), s.flow_v.get(4, ""),
                        int(s.plc_tripped),
                    ])
        except Exception:
            _LOG.exception("CSV flush failed (continuing)")


class _PLCLink(ComLink):
    """The PLC's COM port, owned by an :class:`InterlockService`.

    Opens with the service's ``_open_serial``; holds the service's
    ``_serial_lock`` while it opens/closes; beacons through the service
    (``set_com_state``); refuses a disconnect while the magnets may be on.
    Reconnect backoff 1, 2, 5, 10, then every 30 s (``ComLink.BACKOFF_S``).
    """

    def __init__(self, service: "InterlockService"):
        cfg = service._cfg
        super().__init__(
            cfg.com_port, baud=int(cfg.com_baud), server=service,
            name=f"interlock {cfg.com_port}", io_lock=service._serial_lock,
            logger=_COM_LOG,
        )
        self._service = service

    def _open(self):
        return self._service._open_serial()

    def _close(self, device) -> None:
        device.close()

    def _on_connected(self, device) -> None:
        self._service._on_com_connected()

    def _disconnect_refusal(self) -> Optional[str]:
        return self._service._com_disconnect_refusal()


def _history_row(s: _Sample) -> list:
    """One daily-history row; blank cells are readings absent from the frame."""
    return [
        f"{s.epoch:.3f}",
        time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(s.epoch)),
        "" if s.temperature_k is None else repr(s.temperature_k),
        "" if s.temperature_c is None else f"{s.temperature_c:.3f}",
        s.flow_v.get(1, ""), s.flow_v.get(2, ""),
        s.flow_v.get(3, ""), s.flow_v.get(4, ""),
        int(s.plc_tripped),
    ]


__all__ = ["InterlockService", "InterlockConfig"]
