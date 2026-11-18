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

* Relay poll thread: reads all four relays every ``_RELAY_POLL_INTERVAL_S``
  (the cache snapshots answer from; relay health) and does a startup kill
  owed for a missing COM port once the relay answers.

The ethernet relay
------------------
This server is the relay's only user (the board takes one connection at a
time); everyone else sends it requests (``relay_status`` / ``relay_set`` /
``artiq_restart``, ``ENABLE_MAGNETS`` / ``DISABLE_MAGNETS``).  All relay I/O
goes through ``self._owner`` (:class:`RelayOwner`): bounded single contacts,
magnet kills ahead of everything else, every kill retried until the relay
reads it back off.

Locks
-----
* ``self._owner.lock`` — serializes all relay contacts; kills go first.
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
   A reconnect never enables the magnets and never writes to the PLC.
4b. After a COM (re)connect the PLC's own report decides a tripped status:
   ``_PLC_CLEAR_S`` of unbroken PLC data with no trip text in it → the
   status returns to ok (the magnets stay off until a person's Enable).
   A PLC still latched keeps printing "I TRIPPED", so the status stays
   tripped.  Without a reconnect a trip stays latched in the server.
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
from kexp.control.ethernet_relay import (
    ARTIQ_MAIN_RELAY_IDX, ARTIQ_SATELLITES_RELAY_IDX, CHANNEL_INDEX, CHANNEL_NAMES,
    MAGNET_INHIBIT_IDX,
)
from kexp.util.guis.interlock import interlock_safe_mode as _sm
from kexp.util.guis.interlock.relay_owner import RelayBusy, RelayOwner


_LOG = logging.getLogger("kexp.dashboard.server.interlock")
_COM_LOG = logging.getLogger("kexp.dashboard.server.interlock.com")


# PLC stream checksum primes (one per expected message type).  Identical to
# the values in the original interlock_gui.py.
_CHECKSUM_PRIMES = (2, 3, 5, 7, 11)

# The relay poll thread reads all four relays this often (whether or not
# anyone asks for a snapshot; snapshots answer from the cache).  Until
# 11-17 a snapshot request probed the relay, and every dashboard's relay
# panel opened its own connection every 5 s besides; the board takes one
# connection at a time and refused the overlaps.
_RELAY_POLL_INTERVAL_S = 5.0
# Startup relay read: this many single contacts, so the server is up and
# answering within seconds when the relay does not answer.
_STARTUP_RELAY_ATTEMPTS = 2
# The relay is reported down after this many failed contacts in a row (its
# usual short refusals last 3-6 s, i.e. one or two polls); one success
# clears it.  A trip's kill never waits for this flag.
_RELAY_DOWN_AFTER_FAILURES = 3
# Every magnet kill retries contacts until the relay reads the magnets off,
# for at most this long; one that is still not confirmed hands over to the
# persistent kill thread (which retries forever).
_EMERGENCY_KILL_BUDGET_S = 8.0     # the watchdog's kill, just before os._exit
_STARTUP_KILL_BUDGET_S = 10.0      # COM port missing at startup
_RPC_KILL_BUDGET_S = 5.0           # DISABLE_MAGNETS (answers inside the client's 10 s)
_SAFE_MODE_KILL_BUDGET_S = 5.0
# A COM Disconnect waits this long for the relay lock to read the magnets fresh.
_REFUSAL_READ_LOCK_WAIT_S = 0.5
# relay_status(fresh=True): a read now, at most this often (else the cache).
_FRESH_READ_MIN_INTERVAL_S = 2.0
# How long a write request waits for the relay lock.
_WRITE_LOCK_WAIT_S = 5.0
# stop(): how long it waits for a running ARTIQ restart to restore power.
_STOP_JOB_ABORT_S = 3.0
# The PLC stream: text that means the PLC has tripped (the sketch prints
# "SHUTTING OFF POWER SUPPLY ..." when it trips and "I TRIPPED" every loop,
# ~1 s, while latched).  Searched across read boundaries (a line split
# between two reads is still found): the last _PLC_TAIL_BYTES of each read
# are kept for the next.
_PLC_TRIP_TEXTS = (b"TRIPPED", b"SHUTTING OFF")
_PLC_TAIL_BYTES = 16
# The PLC counts as no longer tripped after this long of unbroken PLC data
# (good frames, no empty read, no reconnect) with no trip text: several PLC
# loops, since one ~1 s read can miss the "I TRIPPED" line and still pass
# the checksum.  After a COM (re)connect, this decides a tripped status.
_PLC_CLEAR_S = 5.0
# Channels relay_set may switch (the magnet relay only via ENABLE/DISABLE_MAGNETS).
_SETTABLE_CHANNELS = ("source_on", "artiq_main_power_cut", "artiq_satellites_power_cut")

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
        relay,                                # the board: EthernetRelayDirect (duck-typed)
        config: InterlockConfig,
        *,
        email_sender: Optional[Callable[[str, str], None]] = None,
    ):
        # Every relay contact goes through the owner (raises TypeError if
        # handed the interlock *client*, which would ask this very server).
        self._owner = RelayOwner(relay, on_contact=self._on_relay_contact)
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
        # The PLC stream (_track_plc_stream; guarded by _state_lock).
        self._plc_rx_tail = b""                       # end of the previous read
        self._plc_latched = False                     # trip text seen, not yet cleared
        self._plc_clean_since: Optional[float] = None # start of the current clean run
        # Set by a COM (re)connect: the first completed clean run decides a
        # tripped status (OK if the PLC reports no trip).  Wall time, for the message.
        self._plc_recheck_since: Optional[float] = None

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

        # relay_status(fresh=True): time of the last read it made.
        self._last_fresh_read_monotonic: float = 0.0
        # Relay health, from the outcome of every relay contact (startup
        # read, polls, kills, enables, writes); guarded by _state_lock.
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
        if self._owner.kill_until_off(_SAFE_MODE_KILL_BUDGET_S, self._stop_event):
            _LOG.critical("Safe-mode magnet kill: confirmed off")
        else:
            _LOG.critical("Safe-mode magnet kill: NOT confirmed in %.0f s -- the hardware "
                          "interlock is the sole defense", _SAFE_MODE_KILL_BUDGET_S)

    def _kill_magnets_without_com(self, reason: str) -> None:
        """COM port missing at startup: drop the magnets, but keep running --
        the COM link keeps retrying the port.  Enable stays refused until a
        good PLC frame arrives (warmup).  A kill not confirmed within
        ``_STARTUP_KILL_BUDGET_S`` stays owed: the relay poll thread keeps
        trying it."""
        _LOG.critical("COM port missing at startup (%s): killing magnets; the COM "
                      "link keeps retrying, and Enable is refused until PLC data flows", reason)
        if self._owner.kill_until_off(_STARTUP_KILL_BUDGET_S, self._stop_event):
            _LOG.critical("Startup magnet kill (no COM port): confirmed off")
        else:
            self._startup_kill_owed = True
            _LOG.critical("Startup magnet kill (no COM port): NOT confirmed in %.0f s; "
                          "the relay poll thread keeps trying (the hardware interlock "
                          "is the defense meanwhile)", _STARTUP_KILL_BUDGET_S)

    # --- relay health ---------------------------------------------------

    def _on_relay_contact(self, ok: bool, exc: Optional[BaseException]) -> None:
        """RelayOwner's report of every contact."""
        if ok:
            self._note_relay_ok()
        else:
            self._note_relay_failed(exc)

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
                "still can).  Enable is refused meanwhile; polling every %.0f s.",
                self._cfg.relay_label, exc, _RELAY_POLL_INTERVAL_S)
        else:
            _LOG.debug("relay contact failed: %r", exc)

    def _relay_poll_loop(self) -> None:
        """Every ``_RELAY_POLL_INTERVAL_S``: a startup kill owed (COM port
        missing at startup while the relay did not answer) if any, else read
        all four relays (the cache, relay health).  A relay that answers again
        is left as it is (as at a normal startup, IT10)."""
        while not self._stop_event.wait(_RELAY_POLL_INTERVAL_S):
            if self._startup_kill_owed:
                if self._owner.kill_until_off(0.0, self._stop_event):
                    self._startup_kill_owed = False
                    _LOG.critical("Startup magnet kill (no COM port at startup), "
                                  "done once the relay answered: confirmed off")
                continue
            try:
                self._owner.read_all(lock_timeout=_RELAY_POLL_INTERVAL_S)
            except RelayBusy:
                pass               # a kill / write holds it; its outcome is noted there
            except Exception:
                pass               # noted by _on_relay_contact
            self._owner.maybe_log_stats()

    def _read_relays_at_startup(self):
        """A few single contacts; returns (states, None) or (None, exc)."""
        exc = None
        for attempt in range(_STARTUP_RELAY_ATTEMPTS):
            if attempt:
                time.sleep(0.5)
            try:
                return self._owner.read_all(), None
            except Exception as e:
                exc = e
        return None, exc

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
        states, relay_exc = self._read_relays_at_startup()

        if relay_exc is not None:
            self._note_relay_failed(relay_exc, down_now=True)
            if com_missing is not None:
                self._startup_kill_owed = True
                _LOG.critical("COM port missing at startup (%s) and the relay is not "
                              "answering: the startup magnet kill is done when the relay "
                              "answers", com_missing)
        elif com_missing is not None:
            self._kill_magnets_without_com(com_missing)
        else:
            # Preserve current magnet state (IT10) — do NOT auto-enable.
            _LOG.info("Startup: current relay magnet-enabled state preserved as %s",
                      states[MAGNET_INHIBIT_IDX - 1])
        if states is not None:
            # A crate left unpowered (an interrupted restart, or on purpose).
            cut = [CHANNEL_NAMES[i] for i in (ARTIQ_MAIN_RELAY_IDX, ARTIQ_SATELLITES_RELAY_IDX)
                   if states[i - 1]]
            if cut:
                _LOG.warning("Startup: ARTIQ power relay(s) energised -- crate power is CUT: %s",
                             ", ".join(cut))

        # Treat the warmup window (IT11): require fresh PLC data within
        # warmup_seconds, else trip.  Mark warmup active.
        with self._state_lock:
            self._warmup_active = True
            self._last_valid_data_monotonic = time.monotonic()
            self._state = _sm.STATE_WARMUP
            self._message = f"warmup ({self._cfg.warmup_seconds:.0f}s)"
            if com_missing is not None:
                self._message += (f"; {self._cfg.com_port} missing at startup, magnets "
                                  + ("kill owed (relay not answering)" if self._startup_kill_owed
                                     else "killed"))

        self._stop_event.clear()
        self._poll_thread = threading.Thread(
            target=self._poll_loop, name="ilock-poll", daemon=True
        )
        self._poll_thread.start()
        self._link.start()
        self._relay_thread = threading.Thread(
            target=self._relay_poll_loop, name="ilock-relay", daemon=True
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
        # First, inside the dashboard's 4 s graceful stop: a running ARTIQ
        # restart restores any crate power it cut.
        self._owner.abort_job(timeout=_STOP_JOB_ABORT_S)
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
        # The relay is never contacted here: the relay poll thread (and every
        # kill / write) keeps the owner's cache, reported with its age.
        relay = self._owner.snapshot()
        magnets_enabled = self._owner.magnets_enabled
        magnets_age = relay["states_age_s"]
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
        relay["link"] = "ok" if relay_down_since is None else "down"
        relay["label"] = self._cfg.relay_label
        return {
            "com": com,
            # The ethernet relay (this server owns it): link, the four states
            # by name with their age, the last ARTIQ restart job, contact stats.
            "relay": relay,
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

    def _enable_refusal(self) -> Optional[dict]:
        """Why Enable is refused now, or None.  Checked before the request
        waits for the relay and again once it holds the relay lock, so an
        Enable can never land after a trip or kill that came first."""
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
        if self._owner.lock.kill_waiting:
            return {"status": "refused", "reason": "kill_in_progress",
                    "message": "a magnet kill is in progress"}
        return None

    def enable_magnets(self, client_addr: str = "?") -> dict:
        """IT10: explicit RPC; refused in safe mode, while tripped, before
        the first good PLC frame since startup (warmup), while the relay is
        not answering, or while a kill is in progress."""
        refusal = self._enable_refusal()
        if refusal is not None:
            _LOG.warning("enable_magnets refused (%s) for %s", refusal["reason"], client_addr)
            return refusal
        try:
            result = self._owner.set_channel(MAGNET_INHIBIT_IDX, True,
                                             lock_timeout=_WRITE_LOCK_WAIT_S,
                                             guard=self._enable_refusal)
        except RelayBusy as exc:
            return {"status": "error", "message": str(exc)}
        except Exception as exc:
            _LOG.exception("enable_magnets failed")
            return {"status": "error", "message": repr(exc)}
        if isinstance(result, dict):           # refused under the lock
            _LOG.warning("enable_magnets refused (%s) for %s", result["reason"], client_addr)
            return result
        if not result[MAGNET_INHIBIT_IDX - 1]:
            return {"status": "error", "message": "the magnet relay reads back off after Enable"}
        _LOG.info("enable_magnets executed (requested by %s)", client_addr)
        return {"status": "ok"}

    def disable_magnets(self, client_addr: str = "?") -> dict:
        """Manual magnet kill.  Always allowed.  Retried until the relay reads
        the magnets off, for up to ``_RPC_KILL_BUDGET_S``; if still not
        confirmed, the persistent kill thread takes over (retries forever)."""
        _LOG.warning("disable_magnets requested by %s", client_addr)
        if self._owner.kill_until_off(_RPC_KILL_BUDGET_S, self._stop_event):
            _LOG.warning("disable_magnets: confirmed off (requested by %s)", client_addr)
            return {"status": "ok"}
        self._start_kill_thread()
        _LOG.critical("disable_magnets: NOT confirmed in %.0f s; the server keeps retrying "
                      "(requested by %s)", _RPC_KILL_BUDGET_S, client_addr)
        return {"status": "error",
                "message": (f"magnet kill not confirmed in {_RPC_KILL_BUDGET_S:.0f} s "
                            "(relay not answering); the interlock server keeps retrying")}

    # --- the ethernet relay, for other programs ------------------------

    def _relay_reply(self, states) -> dict:
        return {"status": "ok", "states": list(states),
                "relays": {CHANNEL_NAMES[i + 1]: s for i, s in enumerate(states)}}

    def relay_status(self, fresh: bool = False, client_addr: str = "?") -> dict:
        """The four relay states.  ``fresh``: read them now (at most every
        ``_FRESH_READ_MIN_INTERVAL_S``; otherwise, or if the read fails, the
        cache with its age and ``stale``)."""
        error = None
        now = time.monotonic()
        if fresh and now - self._last_fresh_read_monotonic >= _FRESH_READ_MIN_INTERVAL_S:
            self._last_fresh_read_monotonic = now
            try:
                return {**self._relay_reply(self._owner.read_all(lock_timeout=_WRITE_LOCK_WAIT_S)),
                        "age_s": 0.0, "stale": False}
            except Exception as exc:
                error = repr(exc)
        states = self._owner.states
        if states is None:
            return {"status": "error", "message": error or "the relay has not been read yet"}
        with self._state_lock:
            down = self._relay_down_since is not None
        reply = self._relay_reply(states)
        reply.update(age_s=round(self._owner.states_age_s or 0.0, 2), stale=bool(error or down))
        if error:
            reply["error"] = error
        return reply

    def relay_set(self, channel, on, client_addr: str = "?") -> dict:
        """Switch the source or an ARTIQ power-cut relay; reads all four back.
        The magnet relay only through ENABLE/DISABLE_MAGNETS."""
        if channel == CHANNEL_NAMES[MAGNET_INHIBIT_IDX]:
            return {"status": "refused", "reason": "use_enable_or_disable",
                    "message": "the magnet relay is switched with ENABLE_MAGNETS / "
                               "DISABLE_MAGNETS (Enable goes through the interlock's checks)"}
        if channel not in _SETTABLE_CHANNELS:
            return {"status": "error", "message": f"unknown channel {channel!r}; "
                                                  f"one of {list(_SETTABLE_CHANNELS)}"}
        if not isinstance(on, bool):
            return {"status": "error", "message": "'on' must be true or false"}
        if channel != "source_on" and self._owner.job_running:
            return {"status": "refused", "reason": "artiq_restart_running",
                    "message": "an ARTIQ restart is running"}
        log = _LOG.info if channel == "source_on" else _LOG.warning
        log("relay_set %s -> %s requested by %s", channel, "on" if on else "off", client_addr)
        idx = CHANNEL_INDEX[channel]
        try:
            states = self._owner.set_channel(idx, on, lock_timeout=_WRITE_LOCK_WAIT_S)
        except Exception as exc:
            _LOG.error("relay_set %s -> %s failed: %r", channel, on, exc)
            return {"status": "error", "message": repr(exc)}
        if states[idx - 1] != on:
            return {**self._relay_reply(states), "status": "error",
                    "message": f"{channel} reads back {'off' if on else 'on'}"}
        return self._relay_reply(states)

    def artiq_restart(self, which, t_wait, t_between=0.0, client_addr: str = "?") -> dict:
        return self._owner.start_artiq_restart(which, t_wait, t_between, requested_by=client_addr)

    def relay_job(self, job_id) -> dict:
        return self._owner.job(str(job_id))

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

        Refused unless the interlock is tripped or the relay reads the
        magnets disabled (``_com_disconnect_refusal``).  While held there is no PLC data, so
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
        be read, the disconnect is refused too (the stricter answer).

        Except while the interlock is tripped: the trip already owes the
        magnet kill and its kill thread keeps at it whatever the COM port
        does, so a Disconnect changes nothing about the magnets.  The relay
        is not asked then -- while the PLC data is stale every poll restarts
        that kill, which keeps the relay lock busy nearly all the time."""
        with self._state_lock:
            tripped = self._state == _sm.STATE_TRIPPED
        if tripped:
            _LOG.warning("COM disconnect allowed: the interlock is tripped (the magnet kill "
                         "is owed and continues without the COM port)")
            return None
        try:
            # Read fresh, never the cache: an old relay panel elsewhere may
            # have enabled the magnets since the last poll.
            enabled = self._owner.read_magnet(lock_timeout=_REFUSAL_READ_LOCK_WAIT_S)
        except RelayBusy:
            return ("magnet state unknown (relay busy; a magnet kill may be in progress): "
                    "cannot confirm the magnets are disabled, so the interlock's COM port "
                    "stays connected")
        except Exception as exc:
            return (f"magnet state unknown (relay read failed: {exc!r}): cannot confirm the "
                    "magnets are disabled, so the interlock's COM port stays connected")
        if enabled:
            return ("magnets are enabled: disable them before disconnecting the "
                    "interlock's COM port")
        return None

    def _on_com_connected(self) -> None:
        """The link opened the port (first time or reconnect).  Never enables
        the magnets, never writes to the PLC, never refreshes the staleness
        clock (only a good PLC frame does).  Starts a recheck: the PLC data
        from now on decides a tripped status (``_track_plc_stream``)."""
        self._com_config_valid = True
        with self._state_lock:
            self._plc_rx_tail = b""
            self._plc_clean_since = None
            self._plc_recheck_since = time.time()

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
        self._start_kill_thread()

    def _start_kill_thread(self) -> None:
        """Spawn the persistent kill on a separate thread so the poll loop
        keeps running (IT4: relay-unreachable retry must not freeze poll).
        While one is still retrying, don't stack another: they would only
        serialize on the relay lock.  Once it has confirmed the kill, the next
        "I TRIPPED" frame starts a fresh one (re-kills if re-enabled)."""
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
                # One bounded contact (kill + read back), ahead of any other
                # waiting relay request; health is noted by the owner.
                still_on = self._owner.kill_once()
                if not still_on:
                    _LOG.warning("Magnets confirmed killed after %d attempt(s) in %.2fs",
                                 attempt, time.monotonic() - t0)
                    return
            except Exception as exc:
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
        # Synchronous, from this thread; the watchdog exits the process after,
        # and a restart preserves the magnet state (IT10) -- so retry until
        # the relay reads the magnets off, for up to _EMERGENCY_KILL_BUDGET_S.
        if self._owner.kill_until_off(_EMERGENCY_KILL_BUDGET_S):
            _LOG.critical("Emergency trip: magnets confirmed off")
        else:
            _LOG.critical("Emergency trip: magnet kill NOT confirmed in %.0f s -- the "
                          "hardware interlock is the sole defense", _EMERGENCY_KILL_BUDGET_S)

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
