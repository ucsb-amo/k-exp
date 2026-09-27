"""The spot scan: step the SLM pattern over a grid, one Andor frame per position.

Each position is a strict sequence, and nothing of one position overlaps the next:

    0. ask the run gate whether the SLM may be written (no run in progress);
    1. send the SLM command and wait -- for the server's "applied" reply when it
       gives one, otherwise until the command has been delivered;
    2. sleep ``settle_s`` for the SLM's next video frame and liquid-crystal response;
    3. start a fresh camera acquisition and take its first frame;
    4. stop the acquisition.

The command for the next position is not sent until step 4 is done, so no
exposure can span a move, and every frame is stored with the (row, col) and
(cx, cy) it was taken at instead of by its place in a list.

A run ends the scan at once. A closed gate at step 0 stops it before the SLM
is written again; a run taking the camera at step 3 (Preempted) stops it with
the position in flight left blank -- not reached, not a failed frame -- and
with no further SLM write. Through liveOD's camera host, the host restarting
or the camera's settings changing under the scan are a Preempted too. Any other snap failure is a missing frame (a red X)
and the scan goes on, up to MAX_CONSECUTIVE_CAMERA_FAILURES in a row.

What this replaced took "the next frame" out of free-running video 10 ms after
queueing the SLM command on the GUI thread. That frame had usually been
exposing since before the command could reach the SLM; the SLM server applies
commands asynchronously and confirmed none of them; and a frame wait that
timed out handed back the previous frame. Each of those puts an image taken
at one position onto a later one, which in raster order shows up as features
wrapping from the end of one row into the start of the next.
"""

import time
from dataclasses import dataclass
from typing import Optional

import numpy as np
from PyQt6 import QtCore

from frame_source import Preempted

# A camera that fails this many positions in a row is not coming back mid-scan.
MAX_CONSECUTIVE_CAMERA_FAILURES = 3


@dataclass
class ScanPoint:
    index: int   # order in which it is taken
    row: int
    col: int
    cx: int
    cy: int


@dataclass
class ScanShot:
    point: ScanPoint
    frame: Optional[np.ndarray]
    slm_applied: Optional[bool]     # True: the server said so; None: it does not say
    t_slm_sent: Optional[float]     # time.monotonic() stamps
    t_slm_applied: Optional[float]
    t_acquire: float                # acquisition started
    t_frame: float                  # frame read, acquisition stopped
    server_apply_s: Optional[float] = None
    error: str = ""                 # why frame is None


def scan_grid(x0, y0, R, step, canvas_res):
    """xs, ys, and the points in raster order (x fastest)."""
    # Symmetric grid about the current spot position: the center itself is
    # always scanned, and offsets run out to +-R in multiples of `step`.
    n = R // step if R > 0 else 0
    offsets = [k * step for k in range(-n, n + 1)]

    # Drop (rather than clamp) points off the canvas -- clamping would
    # produce duplicate tiles sharing one label.
    xs = [x0 + d for d in offsets if 0 <= x0 + d < canvas_res[0]]
    ys = [y0 + d for d in offsets if 0 <= y0 + d < canvas_res[1]]
    points = [ScanPoint(index=r * len(xs) + c, row=r, col=c, cx=x, cy=y)
              for r, y in enumerate(ys) for c, x in enumerate(xs)]
    return xs, ys, points


def _always_open():
    return True, ""


def preempt_text(e):
    """``(what, detail)`` for a Preempted: what took the camera, and the error's text.

    A run is "camera taken by run R"; liveOD's camera host restarting, the
    camera moving, or its settings changing say so instead.
    """
    reason = getattr(e, "reason", "") or ""
    tag = getattr(e, "run_tag", None)
    what = {"restart": "camera host restarted",
            "shutdown": "camera host shutting down",
            "host_lost": "camera host stopped answering",
            "moved": "camera moved to another server",
            "settings_changed": "camera settings changed by another program",
            "refused": "camera host refused the snap"}.get(reason)
    if what is None:
        what = f"camera taken by run {tag}" if tag else "camera taken by a run"
    detail = str(e) or reason
    return what, detail


def run_scan(points, set_center, snap, settle_s, should_stop, on_shot, may_write=_always_open):
    """Take one frame per point, strictly one after another (see module docstring).

    ``may_write()`` returns ``(ok, reason)`` and is asked before every
    ``set_center``; ``set_center(cx, cy)`` blocks and returns an
    SLMSendResult; ``snap()`` blocks and returns a frame from an acquisition
    it starts itself, or None, and raises Preempted when a run takes the
    camera. Returns ``(shots, outcome)``, outcome saying why the scan ended.
    """
    shots = []
    camera_failures = 0
    n = len(points)
    for p in points:
        if should_stop():
            return shots, f"stopped by user after {len(shots)}/{n} positions"

        ok, reason = may_write()
        if not ok:
            return shots, (f"stopped before ({p.cx}, {p.cy}), {len(shots)}/{n} done: "
                           f"{reason}")

        slm = set_center(p.cx, p.cy)
        if not slm.ok:
            if getattr(slm, "blocked", False):
                return shots, (f"stopped before ({p.cx}, {p.cy}), {len(shots)}/{n} done: "
                               f"{slm.error}")
            return shots, (f"stopped at ({p.cx}, {p.cy}), {len(shots)}/{n} "
                           f"done: SLM command failed -- {slm.error}")
        if settle_s > 0:
            time.sleep(settle_s)

        t_acquire = time.monotonic()
        error = ""
        try:
            frame = snap()
            if frame is None:
                error = "acquisition ended without a frame"
        except Preempted as e:
            # A run has the camera, and its kernel writes the SLM (or the
            # camera host restarted, or its settings changed under the scan):
            # stop now, write nothing more, and file nothing for this position.
            what, detail = preempt_text(e)
            return shots, f"{what} at ({p.cx}, {p.cy}), {len(shots)}/{n} done: {detail}"
        except Exception as e:
            frame, error = None, f"{type(e).__name__}: {e}"
        shot = ScanShot(point=p, frame=frame, slm_applied=slm.applied,
                        t_slm_sent=slm.t_sent, t_slm_applied=slm.t_applied,
                        t_acquire=t_acquire, t_frame=time.monotonic(),
                        server_apply_s=slm.server_apply_s, error=error)
        shots.append(shot)
        on_shot(shot)

        camera_failures = camera_failures + 1 if frame is None else 0
        if camera_failures >= MAX_CONSECUTIVE_CAMERA_FAILURES:
            return shots, (f"stopped: no camera frame at {camera_failures} positions "
                           f"in a row (last: {error})")
    return shots, f"finished: {len(shots)}/{n} positions"


def shots_to_grid(shots, nx, ny):
    """frames[row][col], placed by each shot's own (row, col); None where missing."""
    grid = [[None] * nx for _ in range(ny)]
    for s in shots:
        grid[s.point.row][s.point.col] = s.frame
    return grid


def frame_timeout_s(source):
    """How long to wait for one frame: two frame periods, plus 2 s for start-up.

    ``source`` is a FrameSource, or a bare camera with get_frame_timings().
    """
    try:
        if hasattr(source, "frame_period"):
            period = float(source.frame_period())
        else:
            period = float(source.get_frame_timings()[1])
    except Exception:
        period = 1.0
    return 2.0 * period + 2.0


class ScanWorker(QtCore.QThread):
    """Runs run_scan() off the GUI thread; it owns the frame source while it runs.

    Nothing in a step waits on the GUI thread, so a busy GUI (a big live
    mosaic redrawing) slows the display, never the association of frames.
    """
    shot_sig = QtCore.pyqtSignal(object)          # ScanShot
    finished_sig = QtCore.pyqtSignal(list, str)   # all shots, outcome

    def __init__(self, slm, source, points, settle_s, may_write=_always_open, parent=None):
        super().__init__(parent)
        self.slm = slm
        self.source = source
        self.points = list(points)
        self.settle_s = float(settle_s)
        self.may_write = may_write
        self._stop = False
        self._shots = []

    def stop(self):
        self._stop = True

    def _on_shot(self, shot):
        self._shots.append(shot)
        self.shot_sig.emit(shot)

    def run(self):
        outcome = "not started"
        try:
            self.source.begin_scan()
            try:
                timeout_s = frame_timeout_s(self.source)
                _, outcome = run_scan(
                    self.points,
                    set_center=self.slm.set_center_and_wait,
                    snap=lambda: self.source.snap(timeout_s),
                    settle_s=self.settle_s,
                    should_stop=lambda: self._stop,
                    on_shot=self._on_shot,
                    may_write=self.may_write,
                )
            finally:
                self.source.end_scan()
        except Preempted as e:
            what, detail = preempt_text(e)
            outcome = (f"{what} after {len(self._shots)}/{len(self.points)} "
                       f"positions: {detail}")
        except Exception as e:
            outcome = (f"stopped by an error after {len(self._shots)}/{len(self.points)} "
                       f"positions: {type(e).__name__}: {e}")
        finally:
            self.finished_sig.emit(list(self._shots), outcome)
