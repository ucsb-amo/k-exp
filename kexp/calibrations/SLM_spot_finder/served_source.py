"""The Andor the spot finder opens itself, served so that liveOD can take it over.

When liveOD's camera host does not serve the Andor (liveOD not running, its
camera host off, or --direct), the spot finder opens the camera itself -- not
straight through the SDK, as LocalAndorSource does, but through the camera
server logic liveOD's camera host uses: a beacon CameraServerCore with one
CameraWorker driving waxx's EMCCDBackend. The worker is the only thread that
touches the camera; this source asks it (open, live apply, live stream, snap,
close).

The core serves the camera on the network as ``camera_server:<host>:spot_finder``,
under the id liveOD's camera host gives the Andor (``andor_emccd:andor``). So
when liveOD needs the Andor -- its camera host opening it at start, a live
stream, a run's INIT_RUN -- it finds it here and asks for it
(RELINQUISH_CAMERA, waxx.util.live_od.camera_host.claims), as it asks the
beacon server for a Basler:

1. the core reserves the camera for liveOD; a snap in progress ends at once
   (the scan stops on Preempted and files nothing under that position);
2. the worker closes the camera -- acquisition stopped (the video ends),
   shutter closed, cooler left on, SDK shut down, device lock released -- and
   checks that the device is free (CloseReport) before liveOD gets its answer;
3. liveOD opens the Andor and carries on (the run arms, the stream starts);
4. ``on_handover(info)`` tells the window, which follows the Andor to liveOD's
   camera host (StreamSource) -- or, with --direct, says so and stops there.

liveOD keeps the reservation (renewing it) while it has the camera and gives
it back (RETURN_CAMERA) when it closes it; ``on_returned(info)`` says so. The
camera then stays closed here until the andor button opens it again. The core
serves until shutdown() (the window closing), so liveOD can renew and return.

Only a program on this PC may take the camera or give it back. Other programs
may watch its video (a Camera Viewer can attach) but not change its settings,
snap, or start or stop its stream: the spot finder's panel owns them.

Callbacks (on_frame, on_stopped, on_handover, on_returned) are called on the
source's or the server's own threads. They must be quick and must not touch
widgets; the window re-emits them as Qt signals.
"""

import concurrent.futures
import logging
import socket
import threading
import time
from typing import Callable, Optional

import numpy as np

from beacon.camera.backend import ApplyMismatch, ApplyRefused
from beacon.camera.core import CameraServerCore, is_local_address, local_addresses
from beacon.camera.reservations import DEFAULT_TTL_S
from beacon.camera.schema import ANDOR_EMCCD, ANDOR_LIVE_EM_GAIN_CAP, build_live_profile
from beacon.camera.worker import NotOpenError, ReservedError, SnapPreempted, WorkerStopped

from frame_source import Preempted, RunState

logger = logging.getLogger(__name__)

SERVER_ID_PREFIX = "camera_server:"
SERVER_ID_SUFFIX = ":spot_finder"
#: liveOD's camera host names the Andor andor_emccd:<serial or key> (camera_specs);
#: kexp's cameras.andor has no serial and the key "andor"
DEFAULT_ANDOR_CAMERA_ID = "andor_emccd:andor"
#: this window's video, as a live requester of the core
LIVE_REQUESTER = "spot_finder"
#: AndorEMCCD's init (SDK Initialize, cooler, amplifier modes) takes seconds
OPEN_TIMEOUT_S = 60.0
CLOSE_TIMEOUT_S = 20.0
OP_TIMEOUT_S = 20.0
#: a snap's own timeout plus this for the worker to answer
SNAP_MARGIN_S = 5.0
#: A RELINQUISH waits this long for the camera's verified close before
#: answering; liveOD's camera host waits longer for the answer
#: (host.ANDOR_CLAIM_TIMEOUT_S, 20 s).
RELINQUISH_CLOSE_S = 15.0
#: One video wait; stop_video() returns within about this plus the live request's release.
VIDEO_SLICE_S = 0.25
#: After a handover, SLM writes stay blocked this long: longer than RunGate's
#: max age (2 s) plus a poll period (0.5 s), so by then a "no run" verdict
#: comes from a poll sent after liveOD took the camera -- and liveOD, busy in
#: an INIT_RUN, answers no POLL until the run is in progress.
HANDOVER_HOLD_S = 3.0


def _resolve(value):
    return value() if callable(value) else value


def describe_holder(holder) -> str:
    """'liveOD (on kong, pid 1234)' from a reservation's holder dict."""
    h = holder if isinstance(holder, dict) else {}
    who = h.get("label") or h.get("server_id") or h.get("holder_id") or "another program"
    where = ", ".join(x for x in (f"on {h['host']}" if h.get("host") else "",
                                  f"pid {h['pid']}" if h.get("pid") else "") if x)
    return f"{who} ({where})" if where else str(who)


def handover_text(info) -> str:
    """What a handover did, in one sentence (no full stop)."""
    who = describe_holder((info or {}).get("holder"))
    if info.get("already"):
        return (f"{who} has the Andor: it took it over from the spot finder and has not "
                f"given it back")
    if info.get("ok"):
        return (f"{who} took the Andor over: the spot finder stopped its video, closed the "
                f"shutter and released the camera first")
    return (f"{who} took the Andor over; releasing it here was not verified "
            f"({info.get('error') or 'no close report'})")


def is_lent_error(exc) -> bool:
    """True for the error of an op refused because the camera is lent out."""
    return isinstance(exc, ReservedError)


def liveod_camera_id(params) -> str:
    """liveOD's camera host's id for the camera ``params`` describes (its
    camera_specs rule), so that liveOD finds its own Andor on this server;
    DEFAULT_ANDOR_CAMERA_ID when that cannot be worked out."""
    try:
        from waxx.util.live_od.camera_host.host import camera_specs
        for spec in camera_specs([params]):
            cid = spec.camera_id or ""
            if cid.partition(":")[2]:
                return cid
    except Exception as e:
        print(f"[camera] liveOD's camera id rule unavailable ({type(e).__name__}: {e})")
    print(f"[camera] serving the Andor as {DEFAULT_ANDOR_CAMERA_ID}")
    return DEFAULT_ANDOR_CAMERA_ID


class ServedCore(CameraServerCore):
    """CameraServerCore that says when it lent a camera (RELINQUISH) or got
    it back (RETURN), and waits ``relinquish_timeout_s`` for a lent camera's
    verified close (the Andor's SDK shutdown is slower than a Basler's).

    ``on_lent(camera_id, holder, result)`` after a RELINQUISH that reserved a
    camera for someone new (not a renewal), once the close is done or has
    failed; ``on_returned(camera_id, holder_id)`` after a RETURN that ended a
    reservation. Both run on the core's request threads."""

    def __init__(self, server_id, *, relinquish_timeout_s: float = RELINQUISH_CLOSE_S, **kw):
        super().__init__(server_id, **kw)
        self.relinquish_timeout_s = float(relinquish_timeout_s)
        self.on_lent: Optional[Callable] = None
        self.on_returned: Optional[Callable] = None

    def relinquish(self, camera_ids, holder, ttl_s: float = DEFAULT_TTL_S,
                   timeout_s: Optional[float] = None) -> dict:
        results = super().relinquish(camera_ids, holder, ttl_s,
                                     self.relinquish_timeout_s if timeout_s is None else timeout_s)
        hook = self.on_lent
        if hook is not None:
            for cid, r in results.items():
                # a renewal lends nothing new, a refusal lent nothing; a failed
                # close ("reserved": True) did lend it -- it is reserved now
                if r.get("renewed") or not (r.get("ok") or r.get("reserved")):
                    continue
                try:
                    hook(cid, holder.to_wire(), dict(r))
                except Exception:
                    logger.exception("[spot finder] on_lent failed")
        return results

    def return_cameras(self, camera_ids, holder_id: str) -> dict:
        results = super().return_cameras(camera_ids, holder_id)
        hook = self.on_returned
        if hook is not None:
            for cid, r in results.items():
                if not r.get("ok") or r.get("note") == "was not reserved":
                    continue
                try:
                    hook(cid, str(holder_id))
                except Exception:
                    logger.exception("[spot finder] on_returned failed")
        return results


class ServedAndorSource:
    """The Andor opened here, served so that liveOD's camera host can take it
    over (see the module docstring). A FrameSource.

    ``backend_factory()`` builds the camera backend on the worker thread at
    the first open (tests: a FakeBackend); by default waxx's EMCCDBackend
    with the lab's readout settings. ``camera_id`` and ``readout`` (dict of
    hs_speed, vs_speed, vs_amp, preamp, baseline_clamp; either may be a
    callable) are read when the server is first built, at the first open().
    ``core_factory(server_id, **kw)`` replaces ServedCore (tests: bound to
    127.0.0.1, no duplicate check); ``serve=False`` never binds or beacons.
    ``local_addresses``: the client addresses that count as this PC.
    """

    kind = "served"
    shared = False      # this window owns the camera's settings
    async_ops = True    # apply and shutter wait for the camera's worker: off the GUI thread

    def __init__(self, backend_factory: Optional[Callable] = None, *, camera_id=None,
                 readout=None, exposure_s: float = 0.05, server_id: Optional[str] = None,
                 core_factory: Optional[Callable] = None, serve: bool = True,
                 label: str = "SLM spot finder", local_addresses=None,
                 relinquish_timeout_s: float = RELINQUISH_CLOSE_S,
                 hold_s: float = HANDOVER_HOLD_S, clock=time.monotonic):
        self._backend_factory = backend_factory
        self._camera_id_arg = camera_id
        self._readout_arg = readout
        self._exposure_s = float(exposure_s)
        self._gain = 0
        self._shutter = "open"
        self.hostname = socket.gethostname()
        self.server_id = server_id or f"{SERVER_ID_PREFIX}{self.hostname}{SERVER_ID_SUFFIX}"
        self._core_factory = core_factory or ServedCore
        self._serve = bool(serve)
        self.label = str(label)
        self._local = set(local_addresses) if local_addresses is not None else None
        self._relinquish_timeout_s = float(relinquish_timeout_s)
        self._hold_s = float(hold_s)
        self._clock = clock

        self.camera_id: Optional[str] = None
        self._core = None
        self._worker = None
        self._base_profile: dict = {}
        self._core_lock = threading.Lock()
        self._lock = threading.Lock()
        self._lent: Optional[dict] = None      # the holder, while lent out
        self._t_lent: Optional[float] = None
        self.handovers = 0
        self.last_close_report = None
        self.on_handover: Optional[Callable[[dict], None]] = None
        self.on_returned: Optional[Callable[[dict], None]] = None

        self._frame_cv = threading.Condition()
        self._video_thread = None
        self._video_stop = None
        self._video_wanted = False              # started, and not stopped by stop_video()
        self._on_frame = None
        self._on_stopped = None
        self.video_stop_reason = ""

    # -- identity --------------------------------------------------------------

    @property
    def description(self) -> str:
        return f"{self.camera_id or 'the Andor'}, served as {self.server_id}"

    def __repr__(self):
        return f"<ServedAndorSource {self.description}>"

    @property
    def core(self):
        return self._core

    @property
    def worker(self):
        return self._worker

    def lent_to(self) -> Optional[dict]:
        """The holder the camera is lent to, or None."""
        with self._lock:
            return dict(self._lent) if self._lent else None

    # -- the server ------------------------------------------------------------

    def _live_base(self, readout: dict) -> dict:
        """The live profile without the panel's values: the schema's live
        defaults (as liveOD's camera host has them) with the lab's readout
        settings on top, internally triggered."""
        profile = build_live_profile(ANDOR_EMCCD)[0]
        for key in ("hs_speed", "vs_speed", "vs_amp", "preamp", "baseline_clamp"):
            if key in readout:
                profile[key] = int(readout[key])
        profile["trigger_mode"] = "int"
        return profile

    def _live_defaults(self) -> dict:
        return {**self._base_profile, "exposure_time": self._exposure_s,
                "gain": int(self._gain), "shutter": self._shutter}

    @staticmethod
    def _default_backend_factory(readout: dict):
        def make():
            from waxx.control.cameras.emccd_backend import EMCCDBackend
            return EMCCDBackend(serial=None, live_em_gain_cap=ANDOR_LIVE_EM_GAIN_CAP, **readout)
        return make

    def _ensure_core(self):
        with self._core_lock:
            if self._core is not None:
                return self._core
            cid = str(_resolve(self._camera_id_arg) or DEFAULT_ANDOR_CAMERA_ID)
            readout = {k: v for k, v in dict(_resolve(self._readout_arg) or {}).items()
                       if k in ("hs_speed", "vs_speed", "vs_amp", "preamp", "baseline_clamp")}
            factory = self._backend_factory or self._default_backend_factory(readout)
            try:
                core = self._core_factory(self.server_id, policy="persistent", allow_v1=False,
                                          write_policy=self._write_policy,
                                          relinquish_timeout_s=self._relinquish_timeout_s)
            except RuntimeError as e:
                raise RuntimeError(f"the spot finder cannot serve the Andor as {self.server_id}: "
                                   f"{e} (is another spot finder open on this PC?)") from e
            core.on_lent = self._lent_hook
            core.on_returned = self._returned_hook
            self._base_profile = self._live_base(readout)
            if self._local is None:
                self._local = local_addresses()
            w = core.add_camera(cid, factory, category=ANDOR_EMCCD.name,
                                live_defaults=self._live_defaults(), owner_key="spot_finder",
                                info={"serial": "", "model": "", "user_id": cid.partition(":")[2]})
            w.add_tap(self._frame_tap)
            if self._serve:
                try:
                    core.start_in_thread()
                except Exception:
                    core.stop(5.0)
                    raise
                print(f"[camera] serving the Andor ({cid}) as {self.server_id} on port "
                      f"{core.port}: liveOD's camera host can take it over")
            self._core, self._worker, self.camera_id = core, w, cid
            return core

    def _write_policy(self, client_addr, camera_id, keys):
        """Who may do what to the Andor served here (module docstring)."""
        keys = sorted(str(k) for k in keys)
        if keys and set(keys) <= {"relinquish", "return"}:
            if is_local_address(client_addr, self._local):
                return True, ""
            return False, (f"{client_addr or 'an unknown address'} is not this PC: only "
                           f"liveOD's camera host, on this PC, may take the SLM spot finder's "
                           f"Andor or give it back")
        return False, (f"the SLM spot finder owns this Andor's settings, snaps and live stream "
                       f"while it has it open; other programs may watch its video, not change "
                       f"{keys}")

    def _frame_tap(self, frame):
        with self._frame_cv:
            self._frame_cv.notify_all()

    def _lent_hook(self, camera_id, holder, result):
        if camera_id != self.camera_id:
            return
        holder = dict(holder or {}) or {"label": "another program"}
        with self._lock:
            self._lent, self._t_lent = holder, self._clock()
            self.handovers += 1
        with self._frame_cv:
            self._frame_cv.notify_all()             # the video sees it now
        rep = dict(result.get("close_report") or {})
        info = {"holder": dict(holder), "ok": bool(result.get("ok")),
                "error": str(result.get("error") or ""), "close_report": rep,
                "video": bool(self._video_wanted), "camera_id": camera_id,
                "server_id": self.server_id}
        text = handover_text(info)
        if rep.get("errors"):
            text += f" (close steps that failed: {'; '.join(map(str, rep['errors']))})"
        print(f"[camera] {text}")
        cb = self.on_handover
        if cb is not None:
            cb(info)

    def _returned_hook(self, camera_id, holder_id):
        if camera_id != self.camera_id:
            return
        with self._lock:
            holder, self._lent, self._t_lent = self._lent, None, None
        holder = holder or {"holder_id": holder_id}
        print(f"[camera] {describe_holder(holder)} gave the Andor back; it stays closed here "
              f"until the andor button opens it")
        cb = self.on_returned
        if cb is not None:
            cb({"holder": dict(holder), "camera_id": camera_id})

    # -- connection ----------------------------------------------------------

    def is_open(self) -> bool:
        w = self._worker
        return w is not None and w.is_open

    def _require_open(self):
        w = self._worker
        if w is None or not w.is_open:
            lent = self.lent_to()
            if lent:
                raise RuntimeError(f"{describe_holder(lent)} has the Andor (it took it over)")
            raise RuntimeError("the Andor is not connected (andor button)")
        return w

    def open(self):
        """Serve the Andor (first time only), then open it. Blocking, bounded by
        OPEN_TIMEOUT_S; the window calls it off the GUI thread. Raises
        ReservedError while liveOD has the camera (is_lent_error), DeviceBusy
        when another program holds the device."""
        self._ensure_core()
        w = self._worker
        if w.is_open:
            return
        self._shutter = "open"                  # as AndorEMCCD.__init__: opened with the shutter open
        w.set_live_defaults(self._live_defaults())
        w.call("open", OPEN_TIMEOUT_S)
        with self._lock:
            self._lent, self._t_lent = None, None
        print(f"[camera] Andor open ({self.description}): {self._settings_line()}")

    def close(self):
        """Stop the video and close the Andor (acquisition stopped, shutter
        closed, SDK closed, device lock released). The server stays up, the
        camera listed as closed, so liveOD can still claim it. Returns the
        close report (its errors are printed)."""
        self.stop_video()
        w = self._worker
        if w is None or not w.is_open:
            return None
        report = w.call("close", CLOSE_TIMEOUT_S)
        self.last_close_report = report
        if report is not None and (report.errors or report.attached_after):
            print(f"[camera] Andor close reported: device still attached="
                  f"{report.attached_after}, failed steps={list(report.errors)}")
        return report

    def shutdown(self, timeout_s: float = CLOSE_TIMEOUT_S):
        """The window is closing: close the Andor and stop serving it."""
        try:
            self.close()
        except Exception as e:
            print(f"[camera] close at shutdown failed: {type(e).__name__}: {e}")
        with self._core_lock:
            core, self._core = self._core, None
        if core is not None:
            core.stop(timeout_s)

    # -- settings --------------------------------------------------------------

    def _settings_line(self) -> str:
        w = self._worker
        s = w.settings if w is not None else {}
        exp, gain, shutter = s.get("exposure_time"), s.get("gain"), s.get("shutter")
        exp_txt = f"{float(exp):.4f} s" if isinstance(exp, (int, float)) else "?"
        return f"exposure={exp_txt}, EM gain={gain}, shutter={shutter}"

    def frame_period(self) -> float:
        w = self._worker
        s = w.settings if w is not None else {}
        for key in ("cycle_time", "exposure_time"):
            v = s.get(key)
            if isinstance(v, (int, float)) and v > 0:
                return float(v)
        return 1.0

    def _apply_live(self, what: str, **values):
        """A live apply on the worker: ``(readback, "")`` or ``(None, why not)``."""
        w = self._worker
        if w is None or not w.is_open:
            lent = self.lent_to()
            return None, (f"{what} not applied: " + (f"{describe_holder(lent)} has the Andor"
                                                     if lent else "the Andor is not connected"))
        try:
            rb = w.call("apply", OP_TIMEOUT_S, values=values, purpose="live")
        except ReservedError as e:
            return None, f"{what} not applied: {describe_holder(e.holder)} has the Andor"
        except ApplyRefused as e:
            return None, f"{what} not applied: {e.field}: {e.reason}"
        except ApplyMismatch as e:
            return None, f"{what} not applied as asked: {e}"
        except concurrent.futures.TimeoutError:
            return None, f"{what}: the camera did not answer within {OP_TIMEOUT_S:g} s"
        except Exception as e:
            return None, f"{what} not applied: {type(e).__name__}: {e}"
        return rb, ""

    def apply(self, exposure_s: float, gain: int):
        """Exposure and EM gain; ``(ok, msg)`` from the camera's readback."""
        exposure_s, gain = float(exposure_s), int(gain)
        print(f"[camera] apply request: exposure={exposure_s:.4f} s, EMCCD gain={gain}")
        rb, why = self._apply_live("Camera params", exposure_time=exposure_s, gain=gain)
        if rb is None:
            print(f"[camera] {why}")
            return False, why
        self._exposure_s, self._gain = exposure_s, gain
        self._worker.set_live_defaults(self._live_defaults())   # kept for a reopen
        ok, msgs = True, []
        exp_rb = rb.get("exposure_time")
        exp = getattr(exp_rb, "value", None)
        if isinstance(exp, (int, float)):
            # the camera's own quantization is not a failure
            if abs(exp - exposure_s) > max(1e-6, 0.01 * exposure_s):
                ok = False
                msgs.append(f"exposure NOT SET: asked {exposure_s:.4f}s, camera {float(exp):.4f}s"
                            + (" (clamped)" if getattr(exp_rb, "origin", "") == "clamped" else ""))
            else:
                msgs.append(f"exposure={float(exp):.4f}s")
        else:
            ok = False
            msgs.append("exposure: no readback")
        g_rb = rb.get("gain")
        g = getattr(g_rb, "value", None)
        if isinstance(g, (int, float)) and int(g) == gain:
            msgs.append(f"gain={int(g)}")
        else:
            ok = False
            msgs.append(f"gain NOT SET: asked {gain}, camera {g}"
                        + (" (clamped)" if getattr(g_rb, "origin", "") == "clamped" else ""))
        msg = ((("Applied: " if ok else "Partial: ") + " | ".join(msgs))
               + f" (settings rev {getattr(rb, 'settings_rev', '?')})")
        print(f"[camera] {msg}")
        return ok, msg

    def set_shutter(self, open_: bool):
        """``(ok, msg)``: the shutter, from the camera's readback."""
        want = "open" if open_ else "closed"
        rb, why = self._apply_live("Shutter", shutter=want)
        if rb is None:
            print(f"[camera] {why}")
            return False, why
        self._shutter = want
        self._worker.set_live_defaults(self._live_defaults())
        got = getattr(rb.get("shutter"), "value", None)
        if got != want:
            return False, f"Shutter NOT SET: asked {want}, camera reads {got}"
        return True, f"Shutter {got}"

    # -- video ---------------------------------------------------------------

    def start_video(self, on_frame, on_stopped=None):
        """Start the video; returns at once. Its thread asks the worker for the
        live stream; the camera being taken over ends it (on_stopped,
        video_stop_reason)."""
        self._require_open()
        if self.video_running():
            return
        self._on_frame, self._on_stopped = on_frame, on_stopped
        self.video_stop_reason = ""
        self._video_wanted = True
        stop = threading.Event()
        thread = threading.Thread(target=self._video_loop, args=(stop,),
                                  name="spot-served-video", daemon=True)
        self._video_stop, self._video_thread = stop, thread
        thread.start()

    def _video_loop(self, stop):
        core, w, cid = self._core, self._worker, self.camera_id
        reason, requested = "", False
        try:
            after = w.slot.last_seq                # frames from now on
            try:
                core.request_live(cid, LIVE_REQUESTER).result(OP_TIMEOUT_S)
                requested = True
            except ReservedError as e:
                reason = f"video not started: {describe_holder(e.holder)} has the Andor"
                return
            except NotOpenError:
                reason = "video not started: the Andor is not connected"
                return
            except Exception as e:
                reason = f"video not started: {type(e).__name__}: {e}"
                return
            while not stop.is_set():
                with self._frame_cv:
                    f = w.slot.latest(sources=("live", "snap"), after_seq=after)
                    if f is None:
                        self._frame_cv.wait(VIDEO_SLICE_S)
                        f = w.slot.latest(sources=("live", "snap"), after_seq=after)
                if stop.is_set():
                    break
                lent = self.lent_to()
                state = w.state
                if lent or state == "reserved":
                    res = core.reservation(cid) or {}
                    reason = (f"video stopped: {describe_holder(lent or res.get('holder'))} "
                              f"took the Andor over")
                    break
                if state in ("closed", "absent", "faulted"):
                    err = w.snapshot()["error"]
                    reason = f"video stopped: the Andor is {state}" + (f" ({err})" if err else "")
                    break
                if f is None:
                    continue
                after = f.seq
                cb = self._on_frame
                if cb is not None:
                    cb(np.asanyarray(f.image, dtype=np.uint16))
        finally:
            if requested:
                try:
                    core.release_live(cid, LIVE_REQUESTER).result(OP_TIMEOUT_S)
                except Exception:
                    pass                # a close or a handover cleared every live request
            self.video_stop_reason = reason
            if reason:
                print(f"[camera] {reason}")
            cb = self._on_stopped
            if cb is not None:
                cb()

    def stop_video(self):
        """Stop the video and wait for it (its live request is given back)."""
        self._video_wanted = False
        stop, thread = self._video_stop, self._video_thread
        if stop is not None:
            stop.set()
        with self._frame_cv:
            self._frame_cv.notify_all()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=VIDEO_SLICE_S + 5.0)

    def video_running(self) -> bool:
        t, stop = self._video_thread, self._video_stop
        return t is not None and t.is_alive() and not stop.is_set()

    # -- scan ----------------------------------------------------------------

    def begin_scan(self):
        """Raises Preempted while liveOD has the camera, RuntimeError when it is
        not connected."""
        lent = self.lent_to()
        if lent:
            raise Preempted("reserved", None,
                            f"{describe_holder(lent)} has the Andor (it took it over); not scanning")
        self._require_open()

    def snap(self, timeout_s: float):
        """One frame whose exposure starts after this call (the worker's snap:
        a fresh acquisition, its first frame), uint16. Raises Preempted when
        liveOD takes the camera over during the snap, TimeoutError when no
        frame came."""
        w = self._worker
        if w is None:
            raise RuntimeError("the Andor is not connected (andor button)")
        timeout_s = float(timeout_s)
        try:
            f = w.call("snap", timeout_s + SNAP_MARGIN_S, timeout_s=timeout_s)
        except ReservedError as e:
            raise Preempted("reserved", None,
                            f"{describe_holder(e.holder)} took the Andor over; the frame at this "
                            f"position was not taken") from e
        except (SnapPreempted, WorkerStopped) as e:
            raise Preempted("shutdown", None,
                            f"the spot finder's camera server is stopping ({e})") from e
        except concurrent.futures.TimeoutError:
            raise TimeoutError(f"snap: the camera did not answer within "
                               f"{timeout_s + SNAP_MARGIN_S:g} s") from None
        return np.asanyarray(f.image, dtype=np.uint16)

    def end_scan(self):
        pass

    # -- run state, the write gate --------------------------------------------

    def run_state(self) -> RunState:
        return RunState()

    def gate_snapshot(self) -> dict:
        """ok, reason, state ('open' | 'detached' | 'held'), for the window's
        write gate next to RunGate: held for HANDOVER_HOLD_S after liveOD took
        the camera over (it may be for a run), open otherwise."""
        base = {"run_tag": None, "runs_seen": 0, "restarts_seen": 0, "last_run_tag": None,
                "age_s": None, "handovers": self.handovers}
        with self._lock:
            lent, t = self._lent, self._t_lent
        if lent and t is not None:
            left = self._hold_s - (self._clock() - t)
            if left > 0:
                return dict(base, ok=False, state="held",
                            reason=(f"{describe_holder(lent)} took the Andor over (perhaps for a "
                                    f"run) -- SLM writes blocked for {left:.1f} s more, until "
                                    f"liveOD's run state is known"))
        return dict(base, ok=True, reason="", state="open" if self.is_open() else "detached")

    def check(self):
        s = self.gate_snapshot()
        return s["ok"], s["reason"]


__all__ = ["ServedAndorSource", "ServedCore", "describe_holder", "handover_text",
           "is_lent_error", "liveod_camera_id", "DEFAULT_ANDOR_CAMERA_ID", "HANDOVER_HOLD_S",
           "RELINQUISH_CLOSE_S", "SERVER_ID_SUFFIX"]
