"""Where the spot finder gets its camera frames: the FrameSource seam.

The window and the scan ask a FrameSource for video, for one fresh frame per
scan position (snap), and for the exposure/gain/shutter the panel sets. They
never touch a camera object themselves, so the source can be swapped:

- LocalAndorSource: the Andor opened in this process through the SDK, exactly
  as the spot finder has always done it (CameraWorker, snap_frame,
  apply_camera_params, reset_camera_state, setup_shutter -- unchanged).
- StreamSource (not here yet): frames from the camera liveOD owns. There a
  run can take the camera in the middle of a snap, and snap() raises
  Preempted; the scan stops on it rather than filing a run frame, or no frame,
  under an SLM position.

Callbacks (on_frame, on_stopped) are called on the source's own thread. They
must be quick and must not touch widgets; the window re-emits them as Qt
signals.
"""

from dataclasses import dataclass
from typing import Callable, Optional, Protocol

import numpy as np
from PyQt6 import QtCore

from waxx.control import DummyCamera

from andor_group import CameraWorker, snap_frame, apply_camera_params, reset_camera_state


class Preempted(Exception):
    """A run took the camera while the spot finder was using it.

    ``run_tag`` names the run when the source knows it (a run id, as text),
    else None. Wave 3 makes this an alias of beacon.camera.stream.Preempted.
    """

    def __init__(self, reason: str, run_tag: Optional[str] = None):
        super().__init__(reason)
        self.reason = reason
        self.run_tag = run_tag


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
