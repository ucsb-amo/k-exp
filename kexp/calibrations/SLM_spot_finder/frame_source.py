"""Where the spot finder gets its camera frames: the FrameSource seam.

The window and the scan ask a FrameSource for video, for one fresh frame per
scan position (snap), and for the exposure/gain/shutter the panel sets. They
never touch a camera object themselves, so the source can be swapped:

- ServedAndorSource (served_source.py): the Andor opened in this process
  through beacon's camera server logic, as liveOD's camera host opens its
  own, and served so that liveOD's camera host can take it over (the spot
  finder closes it first, then follows it there). Used with --direct, and
  whenever liveOD does not serve the Andor.
- LocalAndorSource: the Andor opened in this process straight through the
  SDK, as the spot finder always did (CameraWorker, snap_frame,
  apply_camera_params, reset_camera_state, setup_shutter -- unchanged). Used
  for a camera object handed to the window (tests), and when beacon is
  missing; liveOD cannot take it over.
- StreamSource: the Andor liveOD owns, through liveOD's camera host
  (beacon.camera.stream). liveOD keeps the camera open and runs it; the spot
  finder subscribes, and its video asks the host for the live stream
  (START_LIVE) and gives the request back when it stops. A run can take the
  camera in the middle of a snap, and snap() then raises Preempted; the scan
  stops on it rather than filing a run frame, or no frame, under an SLM
  position.

choose_source() picks between them: StreamSource when the directory finds an
Andor on a liveOD camera host (``camera_server:<host>:liveod``), else the
Andor opened here, with a banner saying so.

Callbacks (on_frame, on_stopped) are called on the source's own thread. They
must be quick and must not touch widgets; the window re-emits them as Qt
signals.
"""

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

import numpy as np
from PyQt6 import QtCore

from waxx.control import DummyCamera

from andor_group import CameraWorker, snap_frame, apply_camera_params, reset_camera_state

try:
    # One Preempted for both sources: what beacon's CameraStream raises is what
    # run_scan catches. ServerRestarted and ServerStopping are Preempted.
    from beacon.camera.stream import Preempted, ServerRestarted, ServerStopping
    _BEACON_ERROR = ""
except ImportError as _e:       # no beacon here: only the local camera works
    _BEACON_ERROR = f"beacon.camera is not importable ({_e})"

    class Preempted(Exception):
        """A run took the camera while the spot finder was using it."""

        def __init__(self, reason: str, run_tag: Optional[str] = None,
                     message: Optional[str] = None):
            super().__init__(message or reason)
            self.reason = reason
            self.run_tag = run_tag

    class ServerRestarted(Preempted):
        def __init__(self, old_instance: str, new_instance: str,
                     message: Optional[str] = None):
            super().__init__("restart", None, message or (
                f"camera server restarted (instance {old_instance} -> {new_instance})"))
            self.old_instance = old_instance
            self.new_instance = new_instance

    class ServerStopping(Preempted):
        def __init__(self, message: Optional[str] = None):
            super().__init__("shutdown", None, message or "camera server is shutting down")


@dataclass(frozen=True)
class RunState:
    """What the source knows about a run holding its camera."""
    active: bool = False
    run_tag: Optional[str] = None


class FrameSource(Protocol):
    """What the spot finder needs from a camera. Times in seconds."""

    def is_open(self) -> bool:
        """True while a real camera is behind the source."""

    def open(self) -> None:
        """Connect. Blocking; the window calls it off the GUI thread."""

    def close(self) -> None:
        """Release the camera. Blocking. On an error the source stays open."""

    def frame_period(self) -> float:
        """Seconds between frames at the current settings."""

    def start_video(self, on_frame: Callable[[np.ndarray], None],
                    on_stopped: Optional[Callable[[], None]] = None) -> None:
        """Free-running frames to ``on_frame(frame)``; ``on_stopped()`` when it ends."""

    def stop_video(self) -> None:
        """Stop the video and wait for it to have stopped."""

    def video_running(self) -> bool:
        """Whether video is running now."""

    def apply(self, exposure_s: float, gain: int) -> tuple:
        """Set exposure and EM gain; returns ``(ok, msg)`` from the readback."""

    def set_shutter(self, open_: bool) -> None:
        """Open or close the camera shutter."""

    def begin_scan(self) -> None:
        """The scan owns the camera from here until end_scan()."""

    def snap(self, timeout_s: float) -> Optional[np.ndarray]:
        """One frame whose whole exposure starts after this call; None if none came.

        Raises Preempted when a run takes the camera, TimeoutError (or the
        camera's own error) when no frame arrives in ``timeout_s``.
        """

    def end_scan(self) -> None:
        """The scan is done with the camera."""

    def run_state(self) -> RunState:
        """Whether a run holds the camera, as far as this source can tell."""


class LocalAndorSource:
    """The Andor opened in this process -- today's spot finder camera code.

    ``camera`` is an open camera, or None / a DummyCamera for "not connected".
    ``open_camera(exposure_s)`` returns a newly opened camera; the window
    passes one that builds its AndorEMCCD with the lab's readout settings.
    Knows nothing about runs: run_state() is always inactive and snap() never
    raises Preempted (the run gate is what keeps it off the SLM during runs).
    """

    kind = "local"
    shared = False      # this window owns the camera's settings

    def __init__(self, camera=None, open_camera: Optional[Callable] = None,
                 dummy_cls=DummyCamera, exposure_s: float = 0.05):
        self._dummy_cls = dummy_cls
        self.camera = camera if camera is not None else dummy_cls()
        self._open_camera = open_camera
        # AndorEMCCD is opened with this exposure; apply() sets the panel's
        # value right after, and remembers it for the next open.
        self._exposure_s = float(exposure_s)
        self.worker = CameraWorker(self.camera)
        self._on_frame = None
        self._on_stopped = None
        # Direct: called on the worker thread, as the FrameSource contract says.
        direct = QtCore.Qt.ConnectionType.DirectConnection
        self.worker.new_frame_sig.connect(self._deliver_frame, type=direct)
        self.worker.finished.connect(self._deliver_stopped, type=direct)

    # connection
    def is_open(self) -> bool:
        return not isinstance(self.camera, self._dummy_cls)

    def reset_to_video(self):
        """Free-running, internally triggered video (reset_camera_state)."""
        reset_camera_state(self.camera, self._dummy_cls)

    def open(self):
        if self.is_open():
            return
        if self._open_camera is None:
            raise RuntimeError("LocalAndorSource: no open_camera factory was given, "
                               "so there is no camera to open")
        camera = self._open_camera(self._exposure_s)
        reset_camera_state(camera, self._dummy_cls)
        self.camera = camera
        self.worker.camera = camera

    def close(self):
        self.stop_video()
        # AndorEMCCD.Close() closes the shutter before the SDK close (see
        # liveOD's CameraButton.close_camera for why it is Close, not close).
        # On an error the live handle is kept, so the source still reports the
        # real device and a second close can try again.
        self.camera.Close()
        self.camera = self._dummy_cls()
        self.worker.camera = self.camera

    # settings
    def frame_period(self) -> float:
        return float(self.camera.get_frame_timings()[1])

    def apply(self, exposure_s: float, gain: int):
        self._exposure_s = float(exposure_s)
        return apply_camera_params(self.camera, self._dummy_cls, self.worker,
                                   exposure_s=exposure_s, gain=gain)

    def set_shutter(self, open_: bool):
        if not self.is_open():
            return
        mode = "open" if open_ else "closed"
        was_running = self.worker.isRunning()
        if was_running:
            self.worker.stop()
        try:
            self.camera.setup_shutter(mode=mode)
        except Exception as e:
            print(e)
        if was_running:
            self.worker.start()

    # video
    def start_video(self, on_frame, on_stopped=None):
        self._on_frame = on_frame
        self._on_stopped = on_stopped
        self.worker.start()

    def stop_video(self):
        self.worker.stop()

    def video_running(self) -> bool:
        return self.worker.isRunning()

    def _deliver_frame(self, frame):
        cb = self._on_frame
        if cb is not None:
            cb(frame)

    def _deliver_stopped(self):
        cb = self._on_stopped
        if cb is not None:
            cb()

    # scan
    def begin_scan(self):
        # The scan starts its own acquisition at every position, so the
        # free-running video has to stop for it.
        if self.worker.isRunning():
            self.worker.stop()

    def snap(self, timeout_s: float):
        return snap_frame(self.camera, timeout_s)

    def end_scan(self):
        pass

    def run_state(self) -> RunState:
        return RunState()


# ----------------------------------------------------------------------
# liveOD's Andor, through its camera host
# ----------------------------------------------------------------------

#: liveOD's camera host advertises itself as camera_server:<host>:liveod.
LIVEOD_SERVER_PREFIX = "camera_server:"
LIVEOD_SERVER_SUFFIX = ":liveod"
ANDOR_CATEGORY = "andor_emccd"

#: How often the source asks the camera host for its status block (run state).
STATUS_POLL_S = 0.5
#: A status older than this is no run state at all: the source's gate closes
#: (fails closed, like RunGate).
STATUS_MAX_AGE_S = 2.0
#: One video wait; stop_video() returns within about this plus a reply.
VIDEO_SLICE_S = 0.5
#: Video that has had no frame this long, from a host that is not streaming,
#: says so (video_note).
VIDEO_NOTE_AFTER_S = 2.0
#: Host camera states in which a scan's snaps would open, or cannot use, the camera.
_NOT_SCANNABLE = ("closed", "absent", "reserved", "opening", "error", "faulted", "run_fault",
                  "hung")

#: Discovery bounds for choose_source: beacons for this long, then every server
#: at once, each reply within this -- about 2.5 s at worst, off the GUI thread.
DISCOVERY_COLLECT_S = 1.25
DISCOVERY_REQUEST_S = 0.6


def _preempt_what(e) -> str:
    """Why a Preempted stopped something, in words (no run tag)."""
    reason = getattr(e, "reason", "")
    return {"restart": "liveOD's camera host restarted",
            "shutdown": "liveOD's camera host is shutting down",
            "moved": "the Andor moved to another camera server",
            "reserved": "the Andor was lent to another program",
            "host_lost": "liveOD's camera host stopped answering",
            "settings_changed": "liveOD's Andor settings were changed by another program",
            "refused": "liveOD's camera host refused the spot finder",
            }.get(reason, "")


class StreamSource:
    """The Andor liveOD owns, through liveOD's camera host (a CameraStream).

    liveOD opens the camera and keeps it; this only subscribes. So:

    - open() attaches (OPEN_CAMERA; never starts or stops acquisition) and
      close() detaches -- liveOD keeps the camera either way;
    - the video asks the camera host for the live stream (START_LIVE, from the
      video's own thread) and shows the frames it (and snaps) publish -- never
      a run frame. Stopping the video, or close(), gives the request back
      (STOP_LIVE) if this source made one; the host stops the stream only when
      nobody else, liveOD's own live view included, still asks for it.
      START_LIVE never opens the camera and is refused during a run (and to a
      program on another PC): the video then ends at once, calling on_stopped,
      with the reason in video_stop_reason, and video_note() explains it until
      the video is started again. A run taking the camera ends the video too;
    - a host stopping (ServerStopping) or restarting (ServerRestarted) ends the
      video or a snap as a Preempted, like a run, and closes the source's gate;
    - apply() and set_shutter() change liveOD's live settings (the camera host
      takes them only from programs on its own PC, and refuses them during a
      run); the result is the camera's readback, or the refusal;
    - every snap() of a scan must come back as a fresh "snap" frame of its
      own, at the settings revision of the scan's first frame -- a run frame,
      a stale or a foreign one is refused, and a run taking the camera, the
      host restarting or its settings changing raise Preempted.

    gate_snapshot() is this source's own view of the run state, for the
    window's write gate next to RunGate: closed while the camera host says a
    run holds the Andor, while its status is older than ``max_age_s``, and
    after a preemption until a newer status has been read. A background thread
    polls the status every ``status_poll_s`` while open (None: no thread;
    poll_status() by hand).
    """

    kind = "stream"
    shared = True       # liveOD owns the camera's settings: adopt them, don't impose

    def __init__(self, query="andor", label="SLM spot finder", directory=None, *,
                 timeout_s: float = 2.0, op_timeout_s: float = 15.0,
                 status_poll_s: Optional[float] = STATUS_POLL_S,
                 max_age_s: float = STATUS_MAX_AGE_S, clock=time.monotonic):
        if _BEACON_ERROR:
            raise RuntimeError(f"StreamSource needs beacon: {_BEACON_ERROR}")
        self.query = query
        self.label = str(label)
        self.directory = directory
        self.timeout_s = float(timeout_s)
        self.op_timeout_s = float(op_timeout_s)
        self.status_poll_s = None if status_poll_s is None else float(status_poll_s)
        self.max_age_s = float(max_age_s)
        self._clock = clock
        self._stream = None

        self._lock = threading.Lock()
        self._t_status = None        # clock() when the latest status's request was sent
        self._status_error = ""      # why the last status poll failed; "" if it did not
        self._instance = None
        self._host_state = ""
        self._run_active = False
        self._run_tag = None
        self._settings = {}
        self._settings_rev = None
        self._hold = ""              # a preemption seen: closed until a newer status
        self._t_hold = None
        self.runs_seen = 0
        self.restarts_seen = 0
        self.last_run_tag = None

        self._poll_thread = None
        self._poll_stop = None

        self._video_thread = None
        self._video_stop = None
        self._on_frame = None
        self._on_stopped = None
        self._video_t0 = None
        self._video_frames = 0
        self._live_requested = False  # this source's START_LIVE stands (STOP_LIVE owed)
        self._video_refusal = ""      # why the host did not start the live stream
        self.video_stop_reason = ""

        self._require_rev = None
        self._scan_rev0 = None

    # -- identity ----------------------------------------------------------

    @property
    def description(self) -> str:
        q, s = self.query, self._stream
        if s is not None:
            return f"{s.camera_id} on {s.server_id}"
        if hasattr(q, "server_id"):
            return f"{q.camera_id} on {q.server_id}"
        return str(q)

    def __repr__(self):
        return f"<StreamSource {self.description} label={self.label!r}>"

    # -- connection ----------------------------------------------------------

    def is_open(self) -> bool:
        return self._stream is not None

    def open(self):
        """Attach to the Andor on liveOD's camera host and read its status and
        settings. Starts no acquisition. Blocking (bounded by ``timeout_s``)."""
        if self._stream is not None:
            return
        from beacon.camera.stream import CameraStream
        stream = CameraStream(self.query, label=self.label, directory=self.directory,
                              timeout_s=self.timeout_s, op_timeout_s=self.op_timeout_s)
        try:
            t_sent = self._clock()
            settings, rev = stream.get_settings()      # attaches first (OPEN_CAMERA)
        except Exception:
            stream.close()
            raise
        self._stream = stream
        with self._lock:
            self._settings, self._settings_rev = dict(settings), rev
        self._record_status(stream, t_sent)
        print(f"[camera] attached to {self.description} (state {self._host_state}, "
              f"settings rev {rev}): {self._settings_line()}")
        self._start_poll()

    def close(self):
        """Stop the video (its live request given back) and detach. liveOD keeps
        the camera open; its stream runs on while anyone else asks for it."""
        self.stop_video()
        self._stop_poll()
        stream, self._stream = self._stream, None
        if stream is not None:
            # detaching also drops a live request a stuck video thread still holds
            stream.close()
        self._video_refusal = ""
        with self._lock:
            self._t_status = None
            self._status_error = ""
            self._hold = ""
            self._t_hold = None
            self._run_active = False
            self._run_tag = None
        self._require_rev = None

    def _require_stream(self):
        s = self._stream
        if s is None:
            raise RuntimeError("not attached to liveOD's Andor (click the andor button)")
        return s

    # -- status and the source's gate ---------------------------------------

    def _record_status(self, stream, t_sent):
        """Take the stream's latest status block as of ``t_sent``: run state,
        restarts, the host's camera state. Call only after a reply came."""
        st = stream.status(refresh=False)
        with self._lock:
            if st.instance and self._instance is not None and st.instance != self._instance:
                self.restarts_seen += 1
                print(f"[camera] liveOD's camera host restarted (instance {self._instance} -> "
                      f"{st.instance})")
            if st.instance:
                self._instance = st.instance
            self._host_state = st.state
            active, tag = bool(st.run.active), st.run.run_tag
            new_run = active and (not self._run_active
                                  or (tag and self._run_tag and tag != self._run_tag))
            if new_run:
                self.runs_seen += 1
            if active and tag:
                self.last_run_tag = tag
            self._run_active, self._run_tag = active, tag
            if st.settings_rev is not None:
                self._settings_rev = st.settings_rev
            if self._t_status is None or t_sent >= self._t_status:
                self._t_status = t_sent
            self._status_error = ""
            if self._hold and self._t_hold is not None and t_sent > self._t_hold:
                self._hold, self._t_hold = "", None

    def _hold_on(self, e):
        """A preemption: the gate stays closed until a status newer than now."""
        with self._lock:
            if isinstance(e, ServerRestarted) and e.new_instance != self._instance:
                self.restarts_seen += 1
                self._instance = e.new_instance
            if getattr(e, "reason", "") == "run":
                if not self._run_active:
                    self.runs_seen += 1
                self._run_active = True
                self._run_tag = e.run_tag or self._run_tag
                if e.run_tag:
                    self.last_run_tag = e.run_tag
            what = _preempt_what(e) or (f"run {e.run_tag} took liveOD's Andor" if e.run_tag
                                        else "a run took liveOD's Andor")
            self._hold, self._t_hold = what, self._clock()

    def poll_status(self) -> bool:
        """One status request (GET_SETTINGS) to the camera host; True if answered."""
        stream = self._stream
        if stream is None:
            return False
        t_sent = self._clock()
        try:
            settings, rev = stream.get_settings()
        except Exception as e:
            with self._lock:
                self._status_error = f"{type(e).__name__}: {e}"
            return False
        with self._lock:
            self._settings, self._settings_rev = dict(settings), rev
        self._record_status(stream, t_sent)
        return True

    def _start_poll(self):
        if self.status_poll_s is None or self._poll_thread is not None:
            return
        stop = threading.Event()

        def loop():
            while not stop.is_set():
                t0 = time.monotonic()
                self.poll_status()
                stop.wait(max(0.0, self.status_poll_s - (time.monotonic() - t0)))

        self._poll_stop = stop
        self._poll_thread = threading.Thread(target=loop, name="spot-stream-status",
                                             daemon=True)
        self._poll_thread.start()

    def _stop_poll(self):
        stop, thread = self._poll_stop, self._poll_thread
        self._poll_stop = self._poll_thread = None
        if stop is not None:
            stop.set()
        if thread is not None and thread is not threading.current_thread():
            # a poll against a vanished host can take a few seconds; it is a
            # daemon thread and does nothing once stopped
            thread.join(timeout=1.0)

    def gate_snapshot(self) -> dict:
        """May the SLM be written, as far as liveOD's camera host says: ok,
        reason, state ('open' | 'run' | 'held' | 'unreachable' | 'detached'),
        run_tag, age_s, runs_seen, restarts_seen, last_run_tag.

        Detached, the source has no opinion (ok); RunGate still decides."""
        with self._lock:
            base = {"run_tag": self._run_tag, "runs_seen": self.runs_seen,
                    "restarts_seen": self.restarts_seen, "last_run_tag": self.last_run_tag}
            if self._stream is None:
                return dict(base, ok=True, reason="", state="detached", age_s=None)
            now = self._clock()
            age = None if self._t_status is None else now - self._t_status
            state, reason = "open", ""
            if self._hold:
                state = "held"
                reason = (f"{self._hold} -- SLM writes blocked until liveOD's camera host "
                          f"reports its run state again")
            elif self._t_status is None or self._status_error:
                state = "unreachable"
                reason = (f"liveOD's camera host unreachable ({self._status_error or 'no reply yet'})"
                          f" -- SLM writes blocked until it answers")
            elif age > self.max_age_s:
                state = "unreachable"
                reason = (f"liveOD's camera host: no status for {age:.1f} s (limit "
                          f"{self.max_age_s:.1f} s) -- SLM writes blocked until it answers")
            elif self._run_active:
                state = "run"
                who = f"run {self._run_tag}" if self._run_tag else "a run (no run tag yet)"
                reason = f"{who} holds liveOD's Andor -- SLM writes blocked during runs"
            return dict(base, ok=state == "open", reason=reason, state=state, age_s=age)

    def check(self):
        s = self.gate_snapshot()
        return s["ok"], s["reason"]

    def run_state(self) -> RunState:
        with self._lock:
            return RunState(active=self._run_active, run_tag=self._run_tag)

    # -- settings ------------------------------------------------------------

    def _settings_line(self) -> str:
        s = self._settings
        exp, gain, shutter = s.get("exposure_time"), s.get("gain"), s.get("shutter")
        exp_txt = f"{float(exp):.4f} s" if isinstance(exp, (int, float)) else "?"
        return f"exposure={exp_txt}, EM gain={gain}, shutter={shutter}"

    def panel_settings(self) -> dict:
        """The camera's live settings as the panel shows them: exposure_s,
        gain, shutter_open (None where the host does not say)."""
        with self._lock:
            s = dict(self._settings)
        exp, gain, shutter = s.get("exposure_time"), s.get("gain"), s.get("shutter")
        return {"exposure_s": float(exp) if isinstance(exp, (int, float)) else None,
                "gain": int(gain) if isinstance(gain, (int, float)) else None,
                "shutter_open": None if shutter is None else shutter == "open",
                "settings_rev": self._settings_rev}

    def frame_period(self) -> float:
        with self._lock:
            s = dict(self._settings)
        for key in ("cycle_time", "exposure_time"):
            v = s.get(key)
            if isinstance(v, (int, float)) and v > 0:
                return float(v)
        return 1.0

    def _set(self, what: str, **values):
        """SET_SETTINGS; ``(out, "")`` or ``(None, why not)``."""
        from beacon.camera.stream import RunLocked, SettingRefused, ControlRefused
        stream = self._stream
        if stream is None:
            return None, f"{what} not applied: not attached to liveOD's Andor"
        t_sent = self._clock()
        try:
            out = stream.set(**values)
        except (RunLocked, SettingRefused, ControlRefused) as e:
            self._record_status(stream, t_sent)          # a refusal is a reply too
            if isinstance(e, RunLocked):
                who = f"run {e.run_tag}" if e.run_tag else "a run"
                return None, (f"{what} not applied: {who} holds liveOD's Andor, which takes "
                              f"no settings during a run ({e})")
            if isinstance(e, SettingRefused):
                return None, (f"{what} not applied: liveOD's camera host refused {e.field}: "
                              f"{e.reason}")
            return None, f"{what} not applied: liveOD's camera host refused it: {e.reason or e}"
        except Exception as e:
            # no reply (or no usable one): the status is not refreshed by it
            return None, f"{what} not applied: {type(e).__name__}: {e}"
        self._record_status(stream, t_sent)
        with self._lock:
            self._settings.update({k: v.get("value") for k, v in out["readback"].items()
                                   if isinstance(v, dict)})
            if out["settings_rev"] is not None:
                self._settings_rev = out["settings_rev"]
        return out, ""

    def apply(self, exposure_s: float, gain: int):
        """Exposure and EM gain for liveOD's live stream; ``(ok, msg)`` from
        the camera's readback, or the refusal (e.g. during a run)."""
        exposure_s, gain = float(exposure_s), int(gain)
        print(f"[camera] apply request (liveOD's Andor): exposure={exposure_s:.4f} s, "
              f"EMCCD gain={gain}")
        out, why = self._set("Camera params", exposure_time=exposure_s, gain=gain)
        if out is None:
            print(f"[camera] {why}")
            return False, why
        rb = out["readback"]
        ok, msgs = True, []
        exp = (rb.get("exposure_time") or {}).get("value")
        if isinstance(exp, (int, float)):
            # the same tolerance as the local apply: the camera's own quantization
            if abs(exp - exposure_s) > max(1e-6, 0.01 * exposure_s):
                ok = False
                msgs.append(f"exposure NOT SET: asked {exposure_s:.4f}s, camera "
                            f"{float(exp):.4f}s"
                            + (" (clamped)" if rb["exposure_time"].get("origin") == "clamped"
                               else ""))
            else:
                msgs.append(f"exposure={float(exp):.4f}s")
        else:
            ok = False
            msgs.append("exposure: no readback")
        g = (rb.get("gain") or {}).get("value")
        if isinstance(g, (int, float)) and int(g) == gain:
            msgs.append(f"gain={int(g)}")
        else:
            ok = False
            msgs.append(f"gain NOT SET: asked {gain}, camera {g}"
                        + (" (clamped)" if (rb.get("gain") or {}).get("origin") == "clamped"
                           else ""))
        msg = (("Applied: " if ok else "Partial: ") + " | ".join(msgs)
               + f" (liveOD's Andor, settings rev {out['settings_rev']})")
        print(f"[camera] {msg}")
        return ok, msg

    def set_shutter(self, open_: bool):
        """``(ok, msg)``. The shutter of liveOD's Andor, for its live stream."""
        want = "open" if open_ else "closed"
        out, why = self._set("Shutter", shutter=want)
        if out is None:
            print(f"[camera] {why}")
            return False, why
        got = (out["readback"].get("shutter") or {}).get("value")
        if got != want:
            return False, f"Shutter NOT SET: asked {want}, camera reads {got}"
        return True, f"Shutter {got} (liveOD's Andor, settings rev {out['settings_rev']})"

    # -- video ---------------------------------------------------------------

    def start_video(self, on_frame, on_stopped=None):
        """Start the video; returns at once. The video's thread asks liveOD's
        camera host for the live stream first; a refusal ends the video
        (on_stopped, video_stop_reason, video_note)."""
        stream = self._require_stream()
        if self.video_running():
            return
        self._on_frame, self._on_stopped = on_frame, on_stopped
        self.video_stop_reason = ""
        self._video_refusal = ""
        self._video_t0, self._video_frames = time.monotonic(), 0
        stop = threading.Event()
        thread = threading.Thread(target=self._video_loop, args=(stream, stop),
                                  name="spot-stream-video", daemon=True)
        self._video_stop, self._video_thread = stop, thread
        thread.start()

    def _request_live(self, stream) -> str:
        """START_LIVE: "" once liveOD's camera host streams the Andor for this
        source too, else why not, with what to do about it."""
        from beacon.camera.stream import RunLocked, ControlRefused
        t_sent = self._clock()
        try:
            stream.start_live()
        except RunLocked as e:
            self._record_status(stream, t_sent)          # a refusal is a reply too
            who = f"run {e.run_tag}" if e.run_tag else "a run"
            return (f"{who} holds liveOD's Andor, and its camera host starts no live stream "
                    f"during a run; start the video again when the run is over")
        except Preempted as e:                             # ServerStopping, ServerRestarted
            self._hold_on(e)
            return _preempt_what(e) or f"{type(e).__name__}: {e}"
        except ControlRefused as e:
            self._record_status(stream, t_sent)
            return f"liveOD's camera host refused the live stream: {e.reason or e}"
        except Exception as e:
            text = f"{type(e).__name__}: {e}"
            if "(not_open)" in text:
                self._record_status(stream, t_sent)
                return (f"liveOD's Andor is not open (its camera host never opens it for "
                        f"another program); open it in liveOD, then start the video again "
                        f"({text})")
            return f"liveOD's camera host did not start the live stream ({text})"
        self._record_status(stream, t_sent)
        self._live_requested = True
        return ""

    def _release_live(self, stream):
        """STOP_LIVE: give this source's request back. The host stops the stream
        only if nobody else (liveOD's own live view, say) still asks for it."""
        from beacon.camera.stream import RunLocked
        self._live_requested = False
        try:
            stream.stop_live()
        except RunLocked:
            pass                    # a run's lock cleared every request already
        except Exception as e:
            print(f"[camera] could not give liveOD's live stream back ({type(e).__name__}: "
                  f"{e}); the camera host drops the request when the spot finder detaches")

    def _video_loop(self, stream, stop):
        from beacon.camera.stream import RunLocked
        reason = ""
        try:
            why = self._request_live(stream)
            if why:
                reason = f"video not started: {why}"
                self._video_refusal = f"No live video: {why}."
                return
            while not stop.is_set():
                t_sent = self._clock()
                try:
                    f = stream.latest(timeout=VIDEO_SLICE_S, sources=("live", "snap"))
                except RunLocked as e:
                    who = f"run {e.run_tag}" if e.run_tag else "a run"
                    reason = f"video stopped: {who} took liveOD's Andor ({e})"
                    break
                except Preempted as e:  # a run, or the host stopping / restarting
                    self._hold_on(e)
                    tag = getattr(e, "run_tag", None)
                    what = _preempt_what(e) or (f"run {tag} took liveOD's Andor" if tag
                                                else "a run took liveOD's Andor")
                    reason = f"video stopped: {what} ({e})"
                    break
                except Exception as e:
                    if not stop.is_set():
                        reason = f"video stopped: {type(e).__name__}: {e}"
                    break
                self._record_status(stream, t_sent)
                if self._run_active:
                    # a live frame exposed just before the lock can still come
                    # once; the run has the camera now, so it is not shown
                    who = f"run {self._run_tag}" if self._run_tag else "a run"
                    reason = f"video stopped: {who} took liveOD's Andor"
                    break
                if f is None or f.source not in ("live", "snap") or f.run_tag is not None:
                    continue            # never a run frame
                if stop.is_set():
                    break
                self._video_frames += 1
                cb = self._on_frame
                if cb is not None:
                    cb(np.asanyarray(f.image, dtype=np.uint16))
        finally:
            if self._live_requested:
                self._release_live(stream)
            self.video_stop_reason = reason
            if reason:
                print(f"[camera] {reason}")
            cb = self._on_stopped
            if cb is not None:
                cb()

    def stop_video(self):
        """Stop the video and wait for it: its thread gives the live request back
        (STOP_LIVE) on the way out, if it made one."""
        stop, thread = self._video_stop, self._video_thread
        if stop is not None:
            stop.set()
        if thread is not None and thread is not threading.current_thread():
            # one wait slice plus STOP_LIVE's reply; a thread still inside a
            # request to a vanished host is a daemon that delivers nothing more
            thread.join(timeout=VIDEO_SLICE_S + 1.0)

    def video_running(self) -> bool:
        t, stop = self._video_thread, self._video_stop
        return t is not None and t.is_alive() and not stop.is_set()

    def video_note(self) -> str:
        """Why the video shows nothing: the camera host would not start the live
        stream (until the video is started again), or a running video has had
        no frame for a while from a host that is not streaming."""
        if not self.video_running():
            return self._video_refusal
        if self._video_frames:
            return ""
        if time.monotonic() - (self._video_t0 or 0.0) < VIDEO_NOTE_AFTER_S:
            return ""
        with self._lock:
            state = self._host_state
        if state == "streaming":
            return ""
        return (f"No frames: liveOD's Andor is not streaming (camera host state "
                f"{state or 'unknown'}).")

    # -- scan ----------------------------------------------------------------

    def begin_scan(self):
        """Check the camera can be scanned. Raises Preempted if a run holds it,
        RuntimeError if the host's camera is not open (a snap would open it;
        that is liveOD's to do).

        The scan's settings revision is the one its first frame comes back at,
        not the one read here: after a run, liveOD's camera host puts the live
        profile back before the next remote snap (the camera is left at the
        run's settings), which moves the revision once. Every later snap must
        match the first."""
        stream = self._require_stream()
        t_sent = self._clock()
        settings, rev = stream.get_settings()
        with self._lock:
            self._settings, self._settings_rev = dict(settings), rev
        self._record_status(stream, t_sent)
        st = stream.status(refresh=False)
        if st.run.active:
            e = Preempted("run", st.run.run_tag,
                          f"run {st.run.run_tag} holds liveOD's Andor; not scanning")
            self._hold_on(e)
            raise e
        if st.state in _NOT_SCANNABLE:
            raise RuntimeError(f"liveOD's Andor is {st.state} on its camera host: open it in "
                               f"liveOD first (the spot finder does not open liveOD's camera)")
        self._require_rev = None
        self._scan_rev0 = rev

    def snap(self, timeout_s: float):
        """A fresh "snap" frame at the scan's settings revision (uint16): the
        first snap after begin_scan() sets it, every later one must match.

        Raises Preempted when a run takes the camera (also RunLocked), the host
        restarts or stops answering (ServerRestarted / reason "host_lost"), or
        the settings change (reason "settings_changed"); SnapMismatch for a
        frame that is not this snap (never returned); the camera's timeout."""
        from beacon.camera.stream import (RunLocked, SettingsChanged, ControlRefused,
                                          SnapMismatch)
        stream = self._require_stream()
        with self._lock:
            inst0 = self._instance
        t_sent = self._clock()
        try:
            f = stream.snap(timeout=float(timeout_s), policy="restart",
                            require_rev=self._require_rev)
        except Preempted as e:           # a run started, or ServerRestarted
            self._hold_on(e)
            raise
        except RunLocked as e:
            p = Preempted("run", e.run_tag, str(e))
            self._hold_on(p)
            raise p from e
        except SettingsChanged as e:
            raise Preempted("settings_changed", None,
                            f"liveOD's Andor settings changed during the scan (settings_rev "
                            f"{e.expected} -> {e.actual}); later frames would not match the "
                            f"earlier ones") from e
        except ControlRefused as e:
            raise Preempted("refused", None, f"liveOD's camera host refused the snap: "
                                             f"{e.reason or e}") from e
        except SnapMismatch:
            raise                           # not this snap: never filed
        except Exception as e:
            lost = self._lost_host(stream, inst0, e)
            if lost is not None:
                self._hold_on(lost)
                raise lost from e
            raise
        self._record_status(stream, t_sent)
        if f.source != "snap" or f.run_tag is not None:
            raise SnapMismatch(f"liveOD's camera host returned a {f.source!r} frame (run_tag "
                               f"{f.run_tag!r}) for a snap; not filed")
        if self._require_rev is None:
            self._require_rev = f.settings_rev
            s = dict(f.settings)
            exp = s.get("exposure_time")
            exp_txt = f"{float(exp):.4f} s" if isinstance(exp, (int, float)) else "?"
            moved = ("" if f.settings_rev == self._scan_rev0 else
                     f" (the host re-applied its live settings: rev {self._scan_rev0} -> "
                     f"{f.settings_rev})")
            print(f"[camera] scanning through liveOD's Andor at settings rev {f.settings_rev}"
                  f"{moved}: exposure={exp_txt}, EM gain={s.get('gain')}, "
                  f"shutter={s.get('shutter')}")
        return np.asanyarray(f.image, dtype=np.uint16)

    def _lost_host(self, stream, inst0, err):
        """After a failed snap: did the host restart, or stop answering? One
        bounded status request says. None when the host is there as before."""
        t_sent = self._clock()
        try:
            stream.get_settings()
        except Preempted as e2:             # ServerStopping: the host says it is going
            return e2
        except Exception as e2:
            return Preempted("host_lost", None,
                             f"a snap failed ({type(err).__name__}: {err}) and liveOD's camera "
                             f"host does not answer ({type(e2).__name__}: {e2})")
        st = stream.status(refresh=False)
        if inst0 and st.instance and st.instance != inst0:
            e = ServerRestarted(inst0, st.instance)
            self._record_status(stream, t_sent)
            return e
        self._record_status(stream, t_sent)
        if st.run.active:
            return Preempted("run", st.run.run_tag,
                             f"a snap failed ({err}) and run {st.run.run_tag} holds the camera")
        return None

    def end_scan(self):
        self._require_rev = None


# ----------------------------------------------------------------------
# Choosing the source
# ----------------------------------------------------------------------

def is_liveod_server(server_id) -> bool:
    s = str(server_id or "")
    return s.startswith(LIVEOD_SERVER_PREFIX) and s.endswith(LIVEOD_SERVER_SUFFIX)


def find_liveod_andor(directory):
    """``(entry, why_not)``: the Andor a liveOD camera host serves over v2, or
    None and why not. One ``directory.list()`` (bounded by the directory)."""
    entries = directory.list()
    hits = [e for e in entries
            if e.category == ANDOR_CATEGORY and e.protocol == "v2"
            and any(is_liveod_server(s) for s in (e.server_id, *tuple(e.server_ids or ())))]
    if not hits:
        return None, "liveOD does not serve the Andor (camera host off)"
    usable = [e for e in hits if e.state not in ("absent", "reserved")]
    if not usable:
        e = hits[0]
        holder = e.holder or {}
        who = holder.get("label") or holder.get("server_id") or holder.get("holder_id") or ""
        return None, (f"liveOD's camera host lists the Andor as {e.state}"
                      + (f" (held by {who})" if who else ""))
    if len(usable) > 1:
        print(f"[camera] more than one liveOD Andor: "
              f"{', '.join(f'{e.camera_id} @ {e.server_id}' for e in usable)}; using the first")
    return usable[0], ""


@dataclass
class SourceChoice:
    """What choose_source found. ``source`` is a StreamSource for "stream",
    None otherwise ("direct": use the local camera; "none": use no camera)."""
    kind: str               # "stream" | "direct" | "none"
    banner: str
    level: str              # "info" | "warn" | "error"
    source: object = None


def choose_source(mode: str = "auto", directory=None, label: str = "SLM spot finder",
                  **stream_kw) -> SourceChoice:
    """Pick the camera source. ``mode``: "auto" (liveOD's Andor if a camera host
    serves it, else the local camera), "direct" (always local; nothing is
    asked), "stream" (liveOD's Andor or nothing). Blocking, bounded by the
    directory (DISCOVERY_COLLECT_S + 2 x DISCOVERY_REQUEST_S); never opens a
    camera."""
    if mode not in ("auto", "direct", "stream"):
        raise ValueError(f"source mode {mode!r} is not 'auto', 'direct' or 'stream'")
    if mode == "direct":
        return SourceChoice("direct", "--direct: using the Andor directly (liveOD's camera host "
                                      "is not asked); release it in liveOD first", "info")
    if _BEACON_ERROR:
        entry, why = None, f"cannot look for liveOD's camera host: {_BEACON_ERROR}"
        own = False
    else:
        own = directory is None
        if own:
            from beacon.camera.directory import CameraDirectory
            directory = CameraDirectory(collect_for=DISCOVERY_COLLECT_S,
                                        request_timeout_s=DISCOVERY_REQUEST_S, label=label)
        try:
            entry, why = find_liveod_andor(directory)
        except Exception as e:
            entry, why = None, f"looking for liveOD's camera host failed ({type(e).__name__}: {e})"
    if entry is not None:
        src = StreamSource(entry, label=label, directory=directory, **stream_kw)
        return SourceChoice("stream", f"Andor through liveOD ({entry.server_id}): liveOD keeps "
                                      f"the camera and its settings; a run takes it", "info", src)
    if own:
        try:
            directory.close()
        except Exception:
            pass
    if mode == "stream":
        return SourceChoice("none", f"{why} -- --stream was given, so the Andor is not opened "
                                    f"directly", "error")
    return SourceChoice("direct", f"{why} -- using the camera directly; release it in liveOD "
                                  f"first", "warn")
