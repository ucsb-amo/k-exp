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
4. COM5 unplugged → counts as "data stopped".
5. Relay unreachable when trip needed → retry forever, ``CRITICAL`` every 10
   attempts.  PLC hardware interlock is backstop.
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

from kexp.util.guis.interlock import interlock_safe_mode as _sm


_LOG = logging.getLogger("kexp.dashboard.server.interlock")
_COM_LOG = logging.getLogger("kexp.dashboard.server.interlock.com")


# PLC stream checksum primes (one per expected message type).  Identical to
# the values in the original interlock_gui.py.
_CHECKSUM_PRIMES = (2, 3, 5, 7, 11)


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
    heartbeat_path: Optional[str] = None
    email_recipient: Optional[str] = None
    email_credentials_filepath: Optional[str] = None
    reset_debounce_s: float = 5.0


@dataclass
class _Sample:
    """One PLC message worth of structured readings."""
    epoch: float
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
        self._reconnect_attempts = 0
        self._has_emailed_for_current_outage = False

        # Monotonic timers (IT8 - clock-jump immunity).
        self._last_valid_data_monotonic = time.monotonic()
        self._last_loop_iteration_monotonic = time.monotonic()
        self._service_started_monotonic = time.monotonic()
        self._warmup_active = True

        # Serial.  Opened lazily on the poll thread.
        self._serial: Optional[serial.Serial] = None
        self._serial_lock = threading.Lock()

        # Relay lock.
        self._relay_lock = threading.Lock()

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

    def validate_config(self) -> Optional[str]:
        """Return None if config valid; else a short reason string.

        Causes the caller to enter safe mode if the result is non-None.
        """
        ports = {p.device for p in serial.tools.list_ports.comports()}
        if self._cfg.com_port not in ports:
            return f"{_sm.REASON_BAD_COM_PORT}: {self._cfg.com_port} not in {sorted(ports)}"
        try:
            with self._relay_lock:
                _ = self._relay.read_magnet_status()
        except Exception as exc:
            return f"{_sm.REASON_RELAY_UNREACHABLE_AT_BOOT}: {exc!r}"
        return None

    def enter_safe_mode(self, reason: str) -> None:
        """IT15: refuse to operate; try once to drop magnets."""
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

    # --- start / stop -----------------------------------------------

    def start(self) -> bool:
        """Begin polling.  Returns True on success."""
        if not self.acquire_singleton_mutex():
            return False
        # IT15: validate config before doing anything else.
        bad = self.validate_config()
        if bad is not None:
            self.enter_safe_mode(bad)
            # Even in safe mode, run the watchdog + heartbeat so observers see life.
            self._start_watchdog_and_heartbeat()
            return True  # service is "running" but in safe mode

        # Preserve current magnet state (IT10) — do NOT auto-enable.
        try:
            with self._relay_lock:
                state = self._relay.read_magnet_status()
            _LOG.info("Startup: current relay magnet-enabled state preserved as %s", state)
        except Exception:
            _LOG.exception("Could not read initial relay state; continuing")

        # Treat the warmup window (IT11): require fresh PLC data within
        # warmup_seconds, else trip.  Mark warmup active.
        with self._state_lock:
            self._warmup_active = True
            self._last_valid_data_monotonic = time.monotonic()
            self._state = _sm.STATE_WARMUP
            self._message = f"warmup ({self._cfg.warmup_seconds:.0f}s)"

        self._stop_event.clear()
        self._poll_thread = threading.Thread(
            target=self._poll_loop, name="ilock-poll", daemon=True
        )
        self._poll_thread.start()
        self._start_watchdog_and_heartbeat()
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
        if self._watchdog_thread is not None:
            self._watchdog_thread.join(timeout=2.0)
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=2.0)
        try:
            self._email_executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        self._close_serial()
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
            reconnect_attempts = self._reconnect_attempts
            safe_reason = self._safe_mode_reason
        # Read magnet state best-effort; never block trip path.
        magnets_enabled = None
        try:
            with self._relay_lock:
                magnets_enabled = bool(self._relay.read_magnet_status())
        except Exception as exc:
            _LOG.debug("read_magnet_status in snapshot failed: %r", exc)
        return {
            "state": state,                    # ok | tripped | warmup | safe_mode | unknown
            "message": message,
            "safe_mode_reason": safe_reason,
            "last_data_age_s": round(last_data_age, 2),
            "stale_threshold_s": self._cfg.stale_threshold_s,
            "warmup_active": warmup,
            "magnets_enabled": magnets_enabled,
            "reconnect_attempts": reconnect_attempts,
            "uptime_s": round(now - self._service_started_monotonic, 1),
            "temperature_c": sample.temperature_c if sample else None,
            "flow_v": dict(sample.flow_v) if sample else {},
            "plc_tripped": sample.plc_tripped if sample else False,
        }

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
                if self._serial is None or not self._serial.is_open:
                    raise IOError("serial port not open")
                self._serial.write(b"O")
            _LOG.info("reset_interlock issued by %s (wrote 'O' to PLC)", client_addr)
            with self._state_lock:
                self._has_emailed_for_current_outage = False
            return {"status": "ok"}
        except Exception as exc:
            _LOG.exception("reset_interlock write failed")
            return {"status": "error", "message": repr(exc)}

    def enable_magnets(self, client_addr: str = "?") -> dict:
        """IT10: explicit RPC; refused in safe mode or while tripped."""
        with self._state_lock:
            if self._state == _sm.STATE_SAFE_MODE:
                return {"status": "refused", "reason": "safe_mode"}
            if self._state == _sm.STATE_TRIPPED:
                return {"status": "refused", "reason": "tripped"}
            last_plc_tripped = bool(self._last_sample and self._last_sample.plc_tripped)
        if last_plc_tripped:
            return {"status": "refused", "reason": "plc_still_tripped"}
        try:
            with self._relay_lock:
                self._relay.enable_magnets()
            _LOG.info("enable_magnets executed (requested by %s)", client_addr)
            return {"status": "ok"}
        except Exception as exc:
            _LOG.exception("enable_magnets failed")
            return {"status": "error", "message": repr(exc)}

    def disable_magnets(self, client_addr: str = "?") -> dict:
        """Manual magnet kill.  Always allowed."""
        try:
            with self._relay_lock:
                self._relay.kill_magnets()
            _LOG.warning("disable_magnets executed by %s", client_addr)
            return {"status": "ok"}
        except Exception as exc:
            _LOG.exception("disable_magnets failed")
            return {"status": "error", "message": repr(exc)}

    # ------------------------------------------------------------------
    # Internal: poll loop
    # ------------------------------------------------------------------

    def _open_serial(self) -> None:
        with self._serial_lock:
            if self._serial is not None and self._serial.is_open:
                return
            _COM_LOG.info("Open attempt: port=%s baud=%s", self._cfg.com_port, self._cfg.com_baud)
            t0 = time.monotonic()
            try:
                self._serial = serial.Serial(
                    port=self._cfg.com_port,
                    baudrate=self._cfg.com_baud,
                    timeout=self._cfg.com_timeout_s,
                )
                _COM_LOG.info("Open success: port=%s elapsed_ms=%d",
                              self._cfg.com_port, int(1000 * (time.monotonic() - t0)))
            except Exception as exc:
                _COM_LOG.error("Open failure: port=%s exc=%r", self._cfg.com_port, exc)
                self._serial = None
                raise

    def _close_serial(self) -> None:
        with self._serial_lock:
            if self._serial is None:
                return
            try:
                self._serial.close()
            except Exception:
                _COM_LOG.exception("close raised (ignored)")
            self._serial = None

    def _poll_loop(self) -> None:
        # Open serial on this thread (transparency rule).
        try:
            self._open_serial()
        except Exception:
            _LOG.warning("Initial serial open failed; entering reconnect loop")

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
        with self._serial_lock:
            ser = self._serial
            if ser is None or not ser.is_open:
                # Try to reopen.
                pass
            else:
                try:
                    buffer = ser.read(200)
                except Exception as exc:
                    _COM_LOG.error("read failure: %r", exc)
                    self._serial = None  # force reopen
        if not buffer:
            # No data this cycle — check stale and try reopen.
            self._check_stale()
            self._try_reopen_if_needed()
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
                    sample.temperature_c = float(m.group(1)) - 273.0
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
            should_email = (self._consecutive_stale_windows >= 3
                            and not self._has_emailed_for_current_outage)
        _LOG.error("PLC data stale: age=%.1fs threshold=%.1fs", age, self._cfg.stale_threshold_s)
        self._trip(reason=f"no valid PLC data for {age:.1f}s")
        if should_email:
            self._queue_email("K-Interlock: PLC silence",
                              f"No valid PLC data for {age:.1f} s (threshold {self._cfg.stale_threshold_s:.1f} s).")
            with self._state_lock:
                self._has_emailed_for_current_outage = True

    def _try_reopen_if_needed(self) -> None:
        with self._serial_lock:
            if self._serial is not None and self._serial.is_open:
                return
        # Backoff schedule: 1, 2, 5, 10, 30, 30, ... seconds.
        backoffs = (1.0, 2.0, 5.0, 10.0, 30.0)
        delay = backoffs[min(self._reconnect_attempts, len(backoffs) - 1)]
        self._reconnect_attempts += 1
        _COM_LOG.warning("Reconnect attempt %d in %.1fs", self._reconnect_attempts, delay)
        if self._stop_event.wait(delay):
            return
        try:
            self._open_serial()
            _COM_LOG.info("Reconnect success after %d attempts", self._reconnect_attempts)
            self._reconnect_attempts = 0
        except Exception:
            pass  # Already logged in _open_serial.

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
        threading.Thread(
            target=self._kill_magnets_persistent,
            name="ilock-trip",
            daemon=True,
        ).start()

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


__all__ = ["InterlockService", "InterlockConfig"]
