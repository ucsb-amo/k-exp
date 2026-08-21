import time
import threading
import numpy as np
from PyQt6 import QtCore


class CameraWorker(QtCore.QThread):
    new_frame_sig = QtCore.pyqtSignal(np.ndarray)

    def __init__(self, camera):
        super().__init__()
        self.camera = camera
        self.running = False

    def run(self):
        self.running = True
        # The read loop below swallows per-frame exceptions so a single bad
        # read does not kill the video. That silence is also why a camera that
        # is failing every read looks like a frozen or torn image rather than
        # like an error, so count them and say so.
        n_err = 0
        last_err = None
        try:
            self.camera.clear_acquisition()
            self.camera.start_acquisition()
            print("[camera] video: acquisition started")
            while self.running:
                try:
                    if self.camera.wait_for_frame(timeout=0.2):
                        frames = self.camera.read_multiple_images(return_info=False)
                        if frames is not None and len(frames) > 0:
                            data = np.asanyarray(frames[-1], dtype=np.uint16)
                            self.new_frame_sig.emit(data)
                except Exception as e:
                    n_err += 1
                    if n_err == 1 or n_err % 50 == 0:
                        print(f"[camera] video: frame read error #{n_err}: {e}")
                    last_err = e
                    continue
        finally:
            if n_err:
                print(f"[camera] video: stopped after {n_err} frame read error(s); "
                      f"last was: {last_err}")
            try:
                self.camera.stop_acquisition()
            except:
                pass

    def stop(self):
        self.running = False
        self.wait()


class FrameBuffer:
    """
    Thread-safe "latest frame" buffer + wait_for_next_frame().
    Keeps scan logic simple in the main GUI.
    """
    def __init__(self):
        self._frame_lock = threading.Lock()
        self._latest_frame = None
        self._frame_id = 0
        self._frame_wait = threading.Condition(self._frame_lock)

    def push(self, frame: np.ndarray):
        with self._frame_wait:
            self._latest_frame = frame.copy()
            self._frame_id += 1
            self._frame_wait.notify_all()

    def wait_for_next(self, timeout_s=1.5):
        with self._frame_wait:
            start_id = self._frame_id
            t0 = time.time()
            while self._frame_id == start_id:
                remaining = timeout_s - (time.time() - t0)
                if remaining <= 0:
                    break
                self._frame_wait.wait(timeout=remaining)
            if self._latest_frame is None:
                return None
            return self._latest_frame.copy()


def read_camera_state(camera):
    """Read back what the camera actually has set, one field per try.

    Each getter is isolated so one unsupported field comes back as an error
    string instead of taking the rest of the readout with it. A field that
    reads None is itself the interesting result: pylablib's setters return
    early and silently when the camera does not advertise the capability
    (``set_trigger_mode`` bails on a failed ``_check_option``), and the stored
    parameter then holds None rather than the mode that was asked for.
    """
    fields = (
        ("exposure", lambda: float(camera.get_exposure())),
        ("frame_period", lambda: float(camera.get_frame_timings()[1])),
        ("gain", lambda: camera.get_EMCCD_gain()),
        ("trigger", lambda: camera.get_trigger_mode()),
        ("acq_mode", lambda: camera.get_acquisition_mode()),
    )
    state = {}
    for key, getter in fields:
        try:
            state[key] = getter()
        except Exception as e:
            state[key] = f"<error: {e}>"
    return state


def format_camera_state(state):
    """One line, in the units the timing is actually judged in: ms and fps."""
    def ms(v):
        return f"{v * 1e3:.3f} ms" if isinstance(v, float) else str(v)

    period = state.get("frame_period")
    rate = f" ({1.0 / period:.2f} fps)" if isinstance(period, float) and period > 0 else ""
    gain = state.get("gain")
    if isinstance(gain, tuple):
        gain = f"{gain[0]} (advanced={gain[1]})"
    return (f"exposure={ms(state.get('exposure'))}  "
            f"frame_period={ms(period)}{rate}  "
            f"gain={gain}  "
            f"trigger={state.get('trigger')!r}  "
            f"acq={state.get('acq_mode')!r}")


def print_camera_state(camera, label):
    state = read_camera_state(camera)
    print(f"[camera] {label:<14} {format_camera_state(state)}")
    return state


def warn_on_video_state(state):
    """Flag the two settings that make a live view stutter rather than fail.

    A camera left on an external trigger only produces a frame when one
    arrives, and one left in 'single' acquisition produces one frame per
    explicit start. Either shows up as an intermittently updating, torn image
    rather than as an exception, so nothing upstream reports it.
    """
    if state.get("trigger") != "int":
        print(f"[camera] WARNING trigger reads {state.get('trigger')!r}, not 'int'. "
              f"The live view will only update when an external trigger arrives.")
    if state.get("acq_mode") != "cont":
        print(f"[camera] WARNING acquisition mode reads {state.get('acq_mode')!r}, "
              f"not 'cont'. The live view will not free-run.")


def reset_camera_state(camera, DummyCameraCls):
    """Put the camera into free-running, internally triggered video.

    Each step gets its own try. They used to share one, so a throw in
    stop_acquisition() skipped the three calls after it without saying so and
    left the camera in the "ext" trigger / "single" acquisition state that
    AndorEMCCD.__init__ sets -- which does not raise anywhere, it just makes
    the live view update only when a trigger happens to arrive.
    """
    if isinstance(camera, DummyCameraCls):
        return

    print_camera_state(camera, "reset before:")

    steps = (
        ("stop_acquisition()", lambda: camera.stop_acquisition()),
        ("set_trigger_mode('int')", lambda: camera.set_trigger_mode("int")),
        ("set_acquisition_mode('cont')", lambda: camera.set_acquisition_mode("cont")),
        ("set_EMCCD_gain(0)", lambda: camera.set_EMCCD_gain(0)),
    )
    for name, step in steps:
        try:
            step()
            print(f"[camera]   reset ok      {name}")
        except Exception as e:
            print(f"[camera]   reset FAILED  {name}: {e}")

    warn_on_video_state(print_camera_state(camera, "reset after:"))


def apply_camera_params(camera, DummyCameraCls, worker, exposure_s: float, gain: int):
    """
    Safe apply: stop worker if running, apply params, restart.

    Every setting is read back off the camera afterwards and the readback is
    printed and checked against the request, so "applied" means the camera
    agreed rather than that the call did not raise.

    Returns (ok: bool, msg: str)
    """
    if isinstance(camera, DummyCameraCls):
        return True, "DummyCamera: params ignored."

    was_running = worker.isRunning()
    if was_running:
        try:
            worker.stop()
        except Exception:
            pass

    print(f"[camera] apply request: exposure={exposure_s:.4f} s, EMCCD gain={int(gain)}")
    before = print_camera_state(camera, "apply before:")

    ok = True
    msgs = []

    # exposure. AndorEMCCD inherits set_exposure() from pylablib's
    # AndorSDK2Camera -- that is the name its own __init__ uses. The camera
    # quantizes the request, and set_exposure() returns what it actually landed
    # on, so report the readback rather than the value we asked for.
    try:
        if hasattr(camera, "set_exposure"):
            actual = camera.set_exposure(exposure_s)
            if actual is None and hasattr(camera, "get_exposure"):
                actual = camera.get_exposure()
            msgs.append(f"exposure={float(actual):.4f}s"
                        if actual is not None else f"exposure={exposure_s:.4f}s")
        elif hasattr(camera, "set_exposure_time"):
            camera.set_exposure_time(exposure_s)
            msgs.append(f"exposure={exposure_s:.4f}s")
        elif hasattr(camera, "set_ExposureTime"):
            camera.set_ExposureTime(exposure_s)
            msgs.append(f"exposure={exposure_s:.4f}s")
        else:
            ok = False
            msgs.append("exposure: (method not found)")
    except Exception as e:
        ok = False
        msgs.append(f"exposure error: {e}")

    # gain
    try:
        if hasattr(camera, "set_EMCCD_gain"):
            camera.set_EMCCD_gain(int(gain))
            msgs.append(f"gain={int(gain)}")
        else:
            ok = False
            msgs.append("gain: (method not found)")
    except Exception as e:
        ok = False
        msgs.append(f"gain error: {e}")

    after = print_camera_state(camera, "apply after:")

    # Verify against the readback rather than against the absence of an
    # exception. The setters above can no-op silently, and the camera is free
    # to round the exposure to its own clock, so the only thing that settles
    # whether a setting took is what the camera says it now has.
    exp_after = after.get("exposure")
    if isinstance(exp_after, float):
        # A small difference is the camera's own quantization, not a failure.
        if abs(exp_after - exposure_s) > max(1e-6, 0.01 * exposure_s):
            ok = False
            print(f"[camera]   MISMATCH exposure: asked {exposure_s * 1e3:.3f} ms, "
                  f"camera reads {exp_after * 1e3:.3f} ms")
            msgs.append(f"exposure NOT SET (reads {exp_after:.4f}s)")
        else:
            print(f"[camera]   verified exposure = {exp_after * 1e3:.3f} ms")
    else:
        print(f"[camera]   could not read exposure back: {exp_after}")

    gain_after = after.get("gain")
    gain_val = gain_after[0] if isinstance(gain_after, tuple) else gain_after
    if isinstance(gain_val, int):
        if gain_val != int(gain):
            ok = False
            print(f"[camera]   MISMATCH gain: asked {int(gain)}, camera reads {gain_val}")
            msgs.append(f"gain NOT SET (reads {gain_val})")
        else:
            print(f"[camera]   verified EMCCD gain = {gain_val}")
    else:
        print(f"[camera]   could not read gain back: {gain_after}")

    # frame_period, not exposure, is what sets the live view's update rate, so
    # print it whenever it moves -- a exposure change that leaves the period
    # alone means the acquisition timing was not re-set up.
    per_before, per_after = before.get("frame_period"), after.get("frame_period")
    if isinstance(per_before, float) and isinstance(per_after, float):
        print(f"[camera]   frame period {per_before * 1e3:.3f} ms -> "
              f"{per_after * 1e3:.3f} ms"
              + ("  (unchanged)" if abs(per_after - per_before) <= 1e-9 else ""))

    warn_on_video_state(after)

    if was_running:
        try:
            worker.start()
            print("[camera] acquisition restarted")
        except Exception as e:
            print(f"[camera] acquisition restart FAILED: {e}")

    msg = ("Applied: " if ok else "Partial: ") + " | ".join(msgs)
    print(f"[camera] {msg}")
    return ok, msg

