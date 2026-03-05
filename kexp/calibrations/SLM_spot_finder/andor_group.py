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
        try:
            self.camera.clear_acquisition()
            self.camera.start_acquisition()
            while self.running:
                try:
                    if self.camera.wait_for_frame(timeout=0.2):
                        frames = self.camera.read_multiple_images(return_info=False)
                        if frames is not None and len(frames) > 0:
                            data = np.asanyarray(frames[-1], dtype=np.uint16)
                            self.new_frame_sig.emit(data)
                except Exception:
                    continue
        finally:
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


def reset_camera_state(camera, DummyCameraCls):
    if isinstance(camera, DummyCameraCls):
        return
    try:
        camera.stop_acquisition()
        camera.set_trigger_mode("int")
        camera.set_acquisition_mode("cont")
        camera.set_EMCCD_gain(0)
    except Exception as e:
        print(f"Camera Reset Error: {e}")


def apply_camera_params(camera, DummyCameraCls, worker, exposure_s: float, gain: int):
    """
    Safe apply: stop worker if running, apply params, restart.
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

    ok = True
    msgs = []

    # exposure
    try:
        if hasattr(camera, "set_exposure_time"):
            camera.set_exposure_time(exposure_s)
            msgs.append(f"exposure={exposure_s:.4f}s")
        elif hasattr(camera, "set_ExposureTime"):
            camera.set_ExposureTime(exposure_s)
            msgs.append(f"exposure={exposure_s:.4f}s")
        elif hasattr(camera, "ExposureTime"):
            setattr(camera, "ExposureTime", exposure_s)
            msgs.append(f"exposure={exposure_s:.4f}s")
        else:
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
            msgs.append("gain: (method not found)")
    except Exception as e:
        ok = False
        msgs.append(f"gain error: {e}")

    if was_running:
        try:
            worker.start()
        except Exception:
            pass

    return ok, ("Applied: " if ok else "Partial: ") + " | ".join(msgs)
