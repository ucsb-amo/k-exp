"""RelayOwner -- the interlock server's one handle on the ethernet relay.

The relay board takes one TCP connection at a time, so the interlock server is
its only user and everyone else asks the server.  This module is the server's
side of that: every relay contact goes through here.

* **One contact = one bounded attempt.**  Connect, a few commands, close,
  all inside ``contact_budget_s`` (2.5 s).  No contact retries on its own;
  the callers that must succeed (every magnet kill) loop over contacts, with
  the lock released between them.
* **Kills first.**  :class:`PriorityLock` hands the relay to a waiting kill
  before any waiting poll, write or restart step.  The longest a kill waits
  is the one contact in progress (<= ``contact_budget_s``).
* **Cache.**  Every contact that reads the relay updates the cached four
  states (with their time); snapshots answer from it.
* **ARTIQ restarts are jobs.**  A restart (satellites, main, or both) runs on
  its own thread; the lock is held per write, never across the waits.  One
  at a time.  A job that is aborted (server stop) or fails restores the power
  of any crate it had cut before it ends, and says so if it cannot.

Qt-free; no kexp GUI imports.
"""
from __future__ import annotations

import collections
import logging
import socket
import threading
import time
import uuid
from typing import Callable, Optional

from kexp.control.ethernet_relay import (
    ARTIQ_MAIN_RELAY_IDX, ARTIQ_SATELLITES_RELAY_IDX, CHANNEL_NAMES, MAGNET_INHIBIT_IDX,
    N_RELAYS,
)

_LOG = logging.getLogger("kexp.dashboard.server.interlock.relay")

CONTACT_BUDGET_S = 2.5
#: How long a restart step keeps trying one relay write.
JOB_WRITE_BUDGET_S = 10.0
#: How long an aborted/failed job keeps trying to restore a crate's power.
RESTORE_BUDGET_S = 30.0
MAX_JOB_WAIT_S = 60.0
STATS_LOG_INTERVAL_S = 600.0

_JOB_STEPS = {
    "satellites": [("satellites", ARTIQ_SATELLITES_RELAY_IDX)],
    "main": [("main", ARTIQ_MAIN_RELAY_IDX)],
    "all": [("satellites", ARTIQ_SATELLITES_RELAY_IDX), ("main", ARTIQ_MAIN_RELAY_IDX)],
}


class RelayBusy(TimeoutError):
    """The relay lock was not free within the caller's wait."""


class PriorityLock:
    """A non-reentrant lock where waiting kills go before everything else.

    ``acquire(priority=True)`` waits only while the lock is held;
    ``acquire()`` also waits while any priority acquirer is waiting."""

    def __init__(self):
        self._cond = threading.Condition(threading.Lock())
        self._held = False
        self._priority_waiting = 0

    def acquire(self, priority: bool = False, timeout: Optional[float] = None) -> bool:
        deadline = None if timeout is None else time.monotonic() + max(0.0, timeout)
        with self._cond:
            if priority:
                self._priority_waiting += 1
            try:
                while self._held or (not priority and self._priority_waiting > 0):
                    if deadline is None:
                        self._cond.wait()
                    else:
                        left = deadline - time.monotonic()
                        if left <= 0:
                            return False
                        self._cond.wait(left)
                self._held = True
                return True
            finally:
                if priority:
                    self._priority_waiting -= 1

    def release(self) -> None:
        with self._cond:
            self._held = False
            self._cond.notify_all()

    @property
    def held(self) -> bool:
        return self._held

    @property
    def kill_waiting(self) -> bool:
        return self._priority_waiting > 0


class _JobAborted(Exception):
    pass


class _Job:
    def __init__(self, which, t_wait, t_between, requested_by):
        self.id = uuid.uuid4().hex[:12]
        self.which = which
        self.t_wait = t_wait
        self.t_between = t_between
        self.requested_by = requested_by
        self.state = "running"
        self.error: Optional[str] = None
        self.started = time.time()
        self.ended: Optional[float] = None
        self.steps: list[dict] = []
        self.cut: set[int] = set()          # power-cut relays this job has energised
        self.abort = threading.Event()
        self.thread: Optional[threading.Thread] = None

    def as_dict(self) -> dict:
        return {"job_id": self.id, "which": self.which, "t_wait": self.t_wait,
                "t_between": self.t_between, "requested_by": self.requested_by,
                "state": self.state, "error": self.error, "started": self.started,
                "ended": self.ended, "steps": list(self.steps),
                "power_cut_now": sorted(CHANNEL_NAMES[i] for i in self.cut)}


class RelayOwner:
    """The interlock server's relay (module docstring).

    *driver* is the board (``kexp.control.ethernet_relay.EthernetRelayDirect``
    or a test fake) with ``read_relay_status``, ``read_magnet_status``,
    ``kill_magnets_and_read``, ``set_channel_and_read_all`` and
    ``set_channels_and_read_all``, each taking ``retries`` / ``timeout``.
    *on_contact(ok, exc)* is told the outcome of every contact (relay health).
    """

    def __init__(self, driver, *, on_contact: Optional[Callable] = None,
                 contact_budget_s: float = CONTACT_BUDGET_S):
        if getattr(driver, "IS_RELAY_CLIENT", False):
            # The client asks the interlock server: the server built on it
            # would ask itself and never reach the board.
            raise TypeError("RelayOwner needs the board (EthernetRelayDirect), not the "
                            "interlock client EthernetRelay")
        self._driver = driver
        self._on_contact = on_contact
        self.contact_budget_s = float(contact_budget_s)
        self.lock = PriorityLock()

        self._cache_lock = threading.Lock()
        self._states: Optional[list] = None
        self._states_mono: Optional[float] = None

        self._stats_lock = threading.Lock()
        self._stats = collections.Counter()
        self._latency_ms: collections.deque = collections.deque(maxlen=2000)
        self._stats_since = time.time()
        self._stats_logged_mono = time.monotonic()

        self._job_lock = threading.Lock()
        self._job: Optional[_Job] = None
        self._jobs: collections.OrderedDict = collections.OrderedDict()

    # ------------------------------------------------------------------
    # Contacts
    # ------------------------------------------------------------------

    def _acquire(self, priority: bool, lock_timeout: Optional[float]) -> None:
        if not self.lock.acquire(priority=priority, timeout=lock_timeout):
            raise RelayBusy("the relay is busy with another request")

    def _contact(self, fn, *args, store=None):
        """One bounded contact; the caller holds the lock.  *store(result)*
        runs before the contact is reported, so nobody sees the relay
        answering with the cache still holding the state from before."""
        t0 = time.monotonic()
        try:
            result = fn(*args, retries=0, timeout=self.contact_budget_s)
        except Exception as exc:
            self._count(exc, time.monotonic() - t0)
            if self._on_contact is not None:
                self._on_contact(False, exc)
            raise
        if store is not None:
            result = store(result)
        self._count(None, time.monotonic() - t0)
        if self._on_contact is not None:
            self._on_contact(True, None)
        return result

    def _count(self, exc: Optional[BaseException], dt: float) -> None:
        with self._stats_lock:
            self._stats["contacts"] += 1
            if exc is None:
                self._stats["ok"] += 1
                self._latency_ms.append(dt * 1e3)
            elif isinstance(exc, ConnectionRefusedError):
                self._stats["refused"] += 1
            elif isinstance(exc, (socket.timeout, TimeoutError)):
                self._stats["timeout"] += 1
            else:
                self._stats["other_error"] += 1

    def _store_states(self, states) -> list:
        states = [bool(s) for s in states][:N_RELAYS]
        with self._cache_lock:
            self._states = states
            self._states_mono = time.monotonic()
        return states

    def _store_magnet(self, enabled) -> bool:
        enabled = bool(enabled)
        with self._cache_lock:
            if self._states is not None:
                self._states = list(self._states)
                self._states[MAGNET_INHIBIT_IDX - 1] = enabled
                self._states_mono = time.monotonic()
        return enabled

    # --- reads ------------------------------------------------------------

    def read_all(self, lock_timeout: Optional[float] = None) -> list:
        """Read all four relays now (one contact).  Raises on failure."""
        self._acquire(False, lock_timeout)
        try:
            return self._contact(self._driver.read_relay_status, store=self._store_states)
        finally:
            self.lock.release()

    def read_magnet(self, lock_timeout: Optional[float] = None) -> bool:
        """The magnet relay, read now.  Raises on failure / RelayBusy."""
        self._acquire(False, lock_timeout)
        try:
            return self._contact(self._driver.read_magnet_status, store=self._store_magnet)
        finally:
            self.lock.release()

    # --- magnet kill --------------------------------------------------------

    def kill_once(self) -> bool:
        """Magnet relay off + read back, one contact, ahead of everything
        else waiting.  Returns True if the magnets STILL read enabled.
        Raises on a failed contact."""
        self._acquire(True, None)
        try:
            return self._contact(self._driver.kill_magnets_and_read, store=self._store_magnet)
        finally:
            self.lock.release()

    def kill_until_off(self, budget_s: float, stop_event: Optional[threading.Event] = None,
                       gap_s: float = 0.2) -> bool:
        """Kill contacts until the magnets read back off or *budget_s* is up
        (at least one attempt).  True = confirmed off."""
        t_end = time.monotonic() + max(0.0, budget_s)
        while True:
            try:
                if not self.kill_once():
                    return True
            except Exception as exc:
                _LOG.debug("kill contact failed: %r", exc)
            if time.monotonic() >= t_end:
                return False
            if stop_event is not None:
                if stop_event.wait(gap_s):
                    return False
            else:
                time.sleep(gap_s)

    # --- writes -------------------------------------------------------------

    def set_channel(self, idx: int, on: bool, lock_timeout: Optional[float] = None,
                    guard: Optional[Callable[[], Optional[dict]]] = None):
        """Write one relay and read all back (one contact).  *guard*, if
        given, runs while the lock is held: a dict it returns is a refusal
        (returned as is, nothing written).  Returns the states list or the
        refusal dict.  Raises on a failed contact / RelayBusy."""
        self._acquire(False, lock_timeout)
        try:
            if guard is not None:
                refusal = guard()
                if refusal is not None:
                    return refusal
            return self._contact(self._driver.set_channel_and_read_all, idx, on,
                                 store=self._store_states)
        finally:
            self.lock.release()

    # ------------------------------------------------------------------
    # Cache / stats
    # ------------------------------------------------------------------

    @property
    def states(self) -> Optional[list]:
        with self._cache_lock:
            return None if self._states is None else list(self._states)

    @property
    def states_age_s(self) -> Optional[float]:
        with self._cache_lock:
            mono = self._states_mono
        return None if mono is None else time.monotonic() - mono

    @property
    def magnets_enabled(self) -> Optional[bool]:
        states = self.states
        return None if states is None else states[MAGNET_INHIBIT_IDX - 1]

    def stats(self) -> dict:
        with self._stats_lock:
            lat = sorted(self._latency_ms)
            out = dict(self._stats)
            out["since"] = self._stats_since
        for key in ("contacts", "ok", "refused", "timeout", "other_error"):
            out.setdefault(key, 0)
        if lat:
            out["latency_ms_p50"] = round(lat[len(lat) // 2], 1)
            out["latency_ms_p95"] = round(lat[min(len(lat) - 1, int(0.95 * len(lat)))], 1)
            out["latency_ms_max"] = round(lat[-1], 1)
        return out

    def maybe_log_stats(self) -> None:
        now = time.monotonic()
        if now - self._stats_logged_mono < STATS_LOG_INTERVAL_S:
            return
        self._stats_logged_mono = now
        s = self.stats()
        _LOG.info("relay contacts since %s: %d (ok %d, refused %d, timeout %d, other %d); "
                  "latency p50 %s ms p95 %s ms max %s ms",
                  time.strftime("%m-%d %H:%M", time.localtime(s["since"])), s["contacts"],
                  s["ok"], s["refused"], s["timeout"], s["other_error"],
                  s.get("latency_ms_p50"), s.get("latency_ms_p95"), s.get("latency_ms_max"))

    def snapshot(self) -> dict:
        states = self.states
        age = self.states_age_s
        with self._job_lock:
            job = self._job if self._job is not None else (
                next(reversed(self._jobs.values())) if self._jobs else None)
            job_d = job.as_dict() if job is not None else None
        return {
            "relays": (None if states is None
                       else {CHANNEL_NAMES[i + 1]: s for i, s in enumerate(states)}),
            "states": states,
            "states_age_s": None if age is None else round(age, 2),
            "job": job_d,
            "stats": self.stats(),
        }

    # ------------------------------------------------------------------
    # ARTIQ restart jobs
    # ------------------------------------------------------------------

    def start_artiq_restart(self, which: str, t_wait: float, t_between: float = 0.0,
                            requested_by: str = "?") -> dict:
        if which not in _JOB_STEPS:
            return {"status": "error", "message": f"which must be one of {sorted(_JOB_STEPS)}"}
        try:
            t_wait = float(t_wait)
            t_between = float(t_between)
        except (TypeError, ValueError):
            return {"status": "error", "message": "t_wait / t_between must be numbers"}
        for name, value in (("t_wait", t_wait), ("t_between", t_between)):
            if not (0.0 <= value <= MAX_JOB_WAIT_S):
                return {"status": "error",
                        "message": f"{name} must be between 0 and {MAX_JOB_WAIT_S:.0f} s"}
        with self._job_lock:
            if self._job is not None:
                return {"status": "busy", "job_id": self._job.id,
                        "message": f"an ARTIQ restart ({self._job.which}) is already running"}
            job = _Job(which, t_wait, t_between, requested_by)
            self._job = job
            self._jobs[job.id] = job
            while len(self._jobs) > 20:
                self._jobs.popitem(last=False)
        _LOG.warning("ARTIQ restart (%s) requested by %s: power cut %.1f s%s", which,
                     requested_by, t_wait,
                     f", {t_between:.1f} s between crates" if which == "all" else "")
        job.thread = threading.Thread(target=self._run_job, args=(job,),
                                      name=f"relay-job-{job.id}", daemon=True)
        job.thread.start()
        return {"status": "started", "job_id": job.id}

    def job(self, job_id: str) -> dict:
        with self._job_lock:
            job = self._jobs.get(job_id)
            return {"state": "unknown", "error": f"no job {job_id}"} if job is None else job.as_dict()

    @property
    def job_running(self) -> bool:
        with self._job_lock:
            return self._job is not None

    def abort_job(self, timeout: float) -> None:
        """Stop a running restart at once; it restores any crate power it
        had cut (bounded by *timeout* here; the job keeps trying after)."""
        with self._job_lock:
            job = self._job
        if job is None:
            return
        _LOG.warning("ARTIQ restart (%s) aborted: restoring power", job.which)
        job.abort.set()
        if job.thread is not None:
            job.thread.join(timeout=timeout)
        if job.thread is not None and job.thread.is_alive():
            _LOG.critical("ARTIQ restart (%s): power restore not finished within %.1f s; "
                          "crates still cut: %s", job.which, timeout,
                          sorted(CHANNEL_NAMES[i] for i in job.cut) or "none")

    def _step(self, job: _Job, what: str, ok: bool, error: Optional[str] = None) -> None:
        job.steps.append({"t": time.time(), "what": what, "ok": ok, "error": error})

    def _job_write(self, job: _Job, idx: int, on: bool, what: str, budget_s: float,
                   abortable: bool) -> None:
        t_end = time.monotonic() + budget_s
        last = None
        while True:
            if abortable and job.abort.is_set():
                raise _JobAborted()
            try:
                states = self.set_channel(idx, on, lock_timeout=self.contact_budget_s * 2)
                if states[idx - 1] == bool(on):
                    self._step(job, what, True)
                    return
                last = f"read back {'off' if on else 'on'}"
            except Exception as exc:
                last = repr(exc)
            if time.monotonic() >= t_end:
                self._step(job, what, False, last)
                raise RuntimeError(f"{what}: not confirmed in {budget_s:.0f} s ({last})")
            time.sleep(0.2)

    def _job_wait(self, job: _Job, seconds: float) -> None:
        if job.abort.wait(seconds):
            raise _JobAborted()

    def _run_job(self, job: _Job) -> None:
        try:
            for k, (name, idx) in enumerate(_JOB_STEPS[job.which]):
                if k > 0:
                    self._job_wait(job, job.t_between)
                job.cut.add(idx)          # before the write: a lost ack may still have cut it
                self._job_write(job, idx, True, f"{name} power cut", JOB_WRITE_BUDGET_S, True)
                self._job_wait(job, job.t_wait)
                self._job_write(job, idx, False, f"{name} power restored", RESTORE_BUDGET_S, False)
                job.cut.discard(idx)
            job.state = "done"
            _LOG.warning("ARTIQ restart (%s) done", job.which)
        except _JobAborted:
            job.state = "aborted"
        except Exception as exc:
            job.state = "failed"
            job.error = str(exc)
            _LOG.error("ARTIQ restart (%s) failed: %s", job.which, exc)
        finally:
            for idx in sorted(job.cut):
                name = "main" if idx == ARTIQ_MAIN_RELAY_IDX else "satellites"
                try:
                    self._job_write(job, idx, False, f"{name} power restored (after {job.state})",
                                    RESTORE_BUDGET_S, False)
                    job.cut.discard(idx)
                except Exception as exc:
                    _LOG.critical("ARTIQ restart (%s): could NOT restore %s crate power: %s -- "
                                  "the crate is probably unpowered", job.which, name, exc)
                    job.error = (job.error + "; " if job.error else "") + str(exc)
            job.ended = time.time()
            with self._job_lock:
                if self._job is job:
                    self._job = None


__all__ = ["PriorityLock", "RelayBusy", "RelayOwner", "CONTACT_BUDGET_S"]
