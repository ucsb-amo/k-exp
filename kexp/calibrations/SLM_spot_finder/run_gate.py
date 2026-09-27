"""The run gate: the spot finder writes no SLM pattern while the machine is running.

An experiment writes the SLM from its own kernel (Base.setup_slm, right after
the camera is ready), and APD or Basler runs take no camera lock the spot
finder could notice. So the one machine-wide sign of a run is liveOD's run
state: POLL's ``run_in_progress`` goes True at INIT_RUN -- in finish_prepare,
before the kernel is even compiled -- and False at END_RUN / ABORT_RUN.

The gate fails closed. Writes are allowed only while the latest POLL
succeeded, said no run, and is younger than ``max_age_s``. No reply yet, a
failed poll, a reply without ``run_in_progress``, or a reply that is too old
all block writes -- liveOD's REP loop can be busy for a long time (an END_RUN
save), and a poll that is slow to come back must read as "don't know", never
as "no run".

A POLL is timed from when it was sent, not from when its reply arrived, so a
slow reply is as old as it could be. What is left is a race bounded by the
poll age: a write checked just before INIT_RUN is still sent. That write
lands before the run's own setup_slm (which comes after kernel compilation),
unless the SLM server is slower than that; only a lock on the SLM server
itself would close it.

Not seen here: runs made with ``suppress_live_od=True`` (the Monitor, the
tools/turn_on_* scripts, the APD PID experiments, ...) never talk to liveOD.
Most of them pass setup_slm=False, but not all. A run connected to the Monitor
announces itself to the Monitor server whether or not it uses liveOD
(Expt.finish_prepare_wax -> monitor.announce_run), so that is the place to
widen this gate.

The poll runs on its own thread, so check() never blocks the GUI.
"""

import threading
import time

POLL_PERIOD_S = 0.5
DEFAULT_MAX_AGE_S = 2.0
# Two INIT_RUN times further apart than this are two runs.
_INIT_RUN_TOLERANCE_S = 1.0


class LiveODStatus:
    """Default ``status_fn``: one liveOD POLL per call, returning the reply.

    The client is built on the first call (discovery blocks), and rebuilt
    after an error that is not a plain timeout, so a wedged REQ socket does
    not stay wedged. Raises on every failure; RunGate turns that into
    "unreachable".
    """

    def __init__(self, timeout_ms: int = 1000, discovery_timeout: float = 2.0):
        self.timeout_ms = int(timeout_ms)
        self.discovery_timeout = float(discovery_timeout)
        self._client = None

    def __call__(self) -> dict:
        if self._client is None:
            from waxx.util.live_od.live_od_client import LiveODClient
            self._client = LiveODClient(timeout_ms=self.timeout_ms,
                                        discovery_timeout=self.discovery_timeout)
        try:
            reply = self._client.poll()
        except ConnectionError:
            raise   # LiveODClient has already rediscovered and reconnected
        except Exception:
            self.close()
            raise
        if not isinstance(reply, dict) or reply.get("ok") is False:
            raise RuntimeError(f"liveOD refused POLL: {reply!r}")
        return reply

    def close(self):
        client, self._client = self._client, None
        if client is None:
            return
        # LiveODClient.close() terminates its context, which waits for unsent
        # messages unless the socket's linger is 0 -- never wait on a POLL.
        sock = getattr(client, "_socket", None)
        if sock is not None:
            try:
                import zmq
                sock.setsockopt(zmq.LINGER, 0)
            except Exception:
                pass
        try:
            client.close()
        except Exception:
            pass


class RunGate:
    """``check() -> (ok, reason)``: may the spot finder write the SLM now?

    ``status_fn()`` returns a dict with at least ``run_in_progress`` (bool),
    and optionally ``run_id`` and ``init_run_age_s`` (liveOD's POLL reply);
    it may block and may raise. None means a liveOD POLL (LiveODStatus).
    ``start()`` polls it every ``poll_period_s`` on a background thread;
    ``poll_once()`` does one poll on the caller's thread (for tests).
    """

    def __init__(self, status_fn=None, max_age_s: float = DEFAULT_MAX_AGE_S,
                 poll_period_s: float = POLL_PERIOD_S, clock=time.monotonic,
                 wall_clock=time.time):
        self._status_fn = status_fn if status_fn is not None else LiveODStatus()
        self.max_age_s = float(max_age_s)
        self.poll_period_s = float(poll_period_s)
        self._clock = clock
        self._wall = wall_clock
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

        self._t_good = None          # clock() when the last good POLL was sent
        self._run_in_progress = None
        self._run_id = None
        self._error = ""             # why the last poll failed; "" if it did not
        self._n_polls = 0            # polls attempted
        # Runs seen so far: a rising run_in_progress, a new run_id, or a new
        # INIT_RUN time between two polls (a run that came and went unseen).
        self.runs_seen = 0
        self._last_run_id = None     # the run the last one seen belonged to
        self._t_init_run = None      # wall time of liveOD's last INIT_RUN

    # ------------------------------------------------------------------
    # polling
    # ------------------------------------------------------------------

    def start(self):
        if self._thread is not None:
            return self
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="spot-run-gate", daemon=True)
        self._thread.start()
        return self

    def stop(self, timeout: float = 2.0):
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=timeout)
            if thread.is_alive():
                # Still inside a poll. It is a daemon thread; closing its
                # client under it is not safe, so leave both to the process exit.
                return
        close = getattr(self._status_fn, "close", None)
        if close is not None:
            try:
                close()
            except Exception:
                pass

    def _loop(self):
        while not self._stop.is_set():
            t0 = self._clock()
            self.poll_once()
            self._stop.wait(max(0.0, self.poll_period_s - (self._clock() - t0)))

    def poll_once(self) -> bool:
        """One status_fn call; True if it gave a usable reply."""
        t_sent = self._clock()
        try:
            status = self._status_fn()
            if not isinstance(status, dict) or "run_in_progress" not in status:
                raise ValueError(f"reply has no run_in_progress: {status!r}")
            running = status["run_in_progress"]
            if not isinstance(running, bool):
                running = bool(running) if running in (0, 1) else None
            if running is None:
                raise ValueError(f"run_in_progress is {status['run_in_progress']!r}, "
                                 f"not a bool")
        except Exception as e:
            with self._lock:
                self._n_polls += 1
                self._error = f"{type(e).__name__}: {e}"
            return False

        run_id = status.get("run_id")
        age = status.get("init_run_age_s")
        t_init = None
        if isinstance(age, (int, float)):
            t_init = self._wall() - float(age)
        with self._lock:
            self._n_polls += 1
            new_run = False
            if running and not self._run_in_progress:
                new_run = True
            if self._t_good is not None:
                if run_id is not None and self._run_id is not None and run_id != self._run_id:
                    new_run = True
                if (t_init is not None and self._t_init_run is not None
                        and abs(t_init - self._t_init_run) > _INIT_RUN_TOLERANCE_S):
                    new_run = True
            if new_run:
                self.runs_seen += 1
                self._last_run_id = run_id
            if t_init is not None:
                self._t_init_run = t_init
            self._t_good = t_sent
            self._run_in_progress = running
            self._run_id = run_id
            self._error = ""
        return True

    # ------------------------------------------------------------------
    # the gate
    # ------------------------------------------------------------------

    def check(self):
        s = self.snapshot()
        return s["ok"], s["reason"]

    __call__ = check

    def snapshot(self) -> dict:
        """The gate and why: ok, reason, state ('open' | 'run' | 'unreachable'),
        run_id, age_s, runs_seen, last_run_id."""
        with self._lock:
            now = self._clock()
            age = None if self._t_good is None else now - self._t_good
            state, reason = "open", ""
            if self._t_good is None or self._error:
                # never answered, or the latest poll failed: a failure closes
                # the gate at once, without waiting out max_age_s
                state = "unreachable"
                why = (self._error if self._error else
                       "no reply yet" if self._n_polls == 0 else "no usable reply")
                reason = f"liveOD unreachable ({why}) -- SLM writes blocked until liveOD answers"
            elif age > self.max_age_s:
                state = "unreachable"
                reason = (f"liveOD unreachable: no run state for {age:.1f} s "
                          f"(limit {self.max_age_s:.1f} s) -- SLM writes blocked "
                          f"until liveOD answers")
            elif self._run_in_progress:
                state = "run"
                who = f"run {self._run_id}" if self._run_id else "a run (no run id)"
                reason = f"{who} in progress -- SLM writes blocked during runs"
            return {
                "ok": state == "open",
                "reason": reason,
                "state": state,
                "run_id": self._run_id,
                "age_s": age,
                "runs_seen": self.runs_seen,
                "last_run_id": self._last_run_id,
            }
