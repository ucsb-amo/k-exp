import time
import numpy as np
import os
import names
import pypylon.pylon as py
from PyQt6.QtCore import QThread, pyqtSignal

from waxa.atomdata import unpack_group

from waxx.control.cameras import DummyCamera
from waxa.base import Scribe

from waxx.config.timeouts import (CAMERA_MOTHER_CHECK_DELAY as CHECK_DELAY,
                                   UPDATE_EVERY, DATA_SAVER_TIMEOUT)
from kexp.util.live_od.camera_nanny import CameraNanny
from waxa.data.server_talk import server_talk as st

from queue import Queue, Empty

DATA_DIR = os.getenv("data")
RUN_ID_PATH = os.path.join(DATA_DIR,"run_id.py")

def nothing():
    pass

class CameraMother(QThread):
    """Legacy stub kept for import compatibility.

    File-watching has been removed.  Run spawning is now driven by
    ``LiveODServer.new_run_signal`` → ``LiveODWindow.spawn_baby``.
    """

    new_camera_baby = pyqtSignal(str, str)

    def __init__(self, output_queue: Queue = None, start_watching=False,
                 manage_babies=False, N_runs: int = None,
                 camera_nanny=CameraNanny(),
                 server_talk=None):
        super().__init__()

        if server_talk is None:
            self.server_talk = st()
        else:
            self.server_talk = server_talk
        self.server_talk: st

        self.camera_nanny = camera_nanny

        if not output_queue:
            self.output_queue = Queue()
        else:
            self.output_queue = output_queue

    def run(self):
        # No-op: file-watching has been removed.
        pass

class DataHandler(QThread, Scribe):
    got_image_from_queue = pyqtSignal(np.ndarray)
    save_data_bool_signal = pyqtSignal(int)
    image_type_signal = pyqtSignal(bool)

    def __init__(self, queue: Queue, data_filepath: str,
                 save_data=None, imaging_type=None, camera_key="",
                 n_img=None, n_shots=None, n_pwa_per_shot=None):
        """Create a DataHandler.

        Parameters
        ----------
        queue:
            Image queue shared with CameraBaby.
        data_filepath:
            Path to the HDF5 file.  Pass ``""`` when ``save_data=False``.
        save_data:
            Pre-populate ``self.save_data`` so no HDF5 read is needed.
            If *None* the value will be read from the HDF5 in
            ``read_params()`` (legacy behaviour).
        imaging_type:
            Pre-populate ``run_info.imaging_type``.  *None* ⟹ read from HDF5.
        camera_key:
            Camera key string (e.g. ``'xy_basler'``) used to look up
            ``camera_params`` when no HDF5 file exists (``save_data=False``).
        """
        self.data_filepath = data_filepath
        super().__init__()
        self.queue = queue

        from kexp.config.expt_params import ExptParams
        from kexp.config.camera_id import CameraParams
        from waxa.data import RunInfo
        self.params = ExptParams()
        self.camera_params = CameraParams()
        self.run_info = RunInfo()
        self.interrupted = False
        self._camera_key_hint = ""

        # Pre-populate from constructor arguments so HDF5 reads are
        # optional (required when save_data=False / no file exists).
        if save_data is not None:
            self.save_data = bool(save_data)
            self.run_info.save_data = int(bool(save_data))
        if imaging_type is not None:
            self.run_info.imaging_type = imaging_type
        if camera_key:
            self._camera_key_hint = camera_key

        # Pre-populate image count params when provided (critical for
        # save_data=False runs where read_params() skips the HDF5 read).
        if n_img is not None:
            self.params.N_img = int(n_img)
        if n_shots is not None:
            self.params.N_shots = int(n_shots)
        if n_pwa_per_shot is not None:
            self.params.N_pwa_per_shot = int(n_pwa_per_shot)

    def get_save_data_bool(self, save_data_bool):
        self.save_data = save_data_bool

    def get_img_number(self, N_img, N_shots, N_pwa_per_shot):
        self.N_img = N_img
        self.N_shots = N_shots
        self.N_pwa_per_shot = N_pwa_per_shot

    def run(self):
        if self.interrupted:
            self.quit()
        self.write_image_to_dataset()

    def read_params(self):
        """Populate camera/run-info attrs, then emit configuration signals.

        When ``save_data=True`` (HDF5 file available) the camera_params and
        run_info are read back from the file so that any server-side
        adjustments are reflected.  When ``save_data=False`` the attrs have
        already been set at construction time, so we skip the file read and
        just try to look up the camera by key.
        """
        if getattr(self, 'save_data', True) and self.data_filepath:
            with self.wait_for_data_available() as f:
                unpack_group(f, 'camera_params', self.camera_params)
                unpack_group(f, 'params', self.params)
                unpack_group(f, 'run_info', self.run_info)
        elif hasattr(self, '_camera_key_hint') and self._camera_key_hint:
            # No HDF5 — look up camera params by key so create_camera() works.
            from kexp.config.camera_id import cameras as cam_catalog, CameraParams as CP
            for cam in vars(cam_catalog).values():
                if isinstance(cam, CP):
                    cam_key = cam.key if not isinstance(cam.key, bytes) else cam.key.decode()
                    if cam_key == self._camera_key_hint:
                        self.camera_params = cam
                        break
        self.image_type_signal.emit(self.run_info.imaging_type)
        self.save_data_bool_signal.emit(self.run_info.save_data)

    def write_image_to_dataset(self):
        try:
            if self.save_data:
                f = self.wait_for_data_available(timeout=DATA_SAVER_TIMEOUT,
                                                 check_interrupt_method=self.break_check)
            while True:
                if self.interrupted:
                    break
                try:
                    img, _, idx = self.queue.get(block=False)
                    img_t = time.time()
                    self.got_image_from_queue.emit(img)
                    if self.save_data:
                        f['data']['images'][idx] = img
                        f['data']['image_timestamps'][idx] = img_t
                        print(f"saved {idx+1}/{self.N_img}")
                    if idx == (self.N_img - 1):
                        break
                except:
                    self.msleep(1)
        except Exception as e:
            # print(f"No images received after {TIMEOUT} seconds. Did the grab time out?")
            print(e)
        try:
            if self.save_data: f.close()
        except:
            pass

    def break_check(self):
        return self.interrupted

class CameraBaby(QThread):
    image_captured = pyqtSignal(int)
    camera_connect = pyqtSignal(str)
    camera_grab_start = pyqtSignal(int,int,int)
    save_data_bool_signal = pyqtSignal(int)
    image_type_signal = pyqtSignal(bool)
    honorable_death_signal = pyqtSignal()
    dishonorable_death_signal = pyqtSignal()
    done_signal = pyqtSignal()
    break_signal = pyqtSignal()
    cam_status_signal = pyqtSignal(int)

    def __init__(self,data_handler:DataHandler,
                 name,output_queue:Queue,
                 camera_nanny:CameraNanny):
        super().__init__()

        self.name = name
        self.camera_nanny = camera_nanny
        self.camera = DummyCamera()
        self.queue = output_queue
        self.death = self.dishonorable_death
        self.data_handler = data_handler
        self.interrupted = False
        self.dead = False

    def run(self):
        try:
            self.cam_status_signal.emit(0)
            print(f"{self.name}: I am born!")
            self.data_handler.read_params()
            self.handshake()
            self.grab_loop()
        except Exception as e:
            print(e)
        if self.interrupted:
            print('Grab loop interrupted, shutting down.')
        self.death()
        if self.interrupted:
            self.dead = True
        self.done_signal.emit()

    def handshake(self):
        """Connect camera and signal readiness via cam_status_signal.

        Status codes
        ------------
        0  baby born
        1  camera opened
        2  camera ready (triggers LiveODServer._cam_ready_event via
           a DirectConnection in LiveODWindow.spawn_baby)
        3  (legacy: ready-ack; kept for status-light compatibility)
        """
        self.create_camera()
        self.cam_status_signal.emit(1)
        if self.camera is None or not self.camera.is_opened():
            raise ValueError("Camera not ready")
        # Status 2 → triggers server._cam_ready_event via DirectConnection
        self.cam_status_signal.emit(2)
        # Status 3 kept for the status-lights widget
        self.cam_status_signal.emit(3)

    def create_camera(self):
        self.camera = self.camera_nanny.persistent_get_camera(self.data_handler.camera_params)
        self.camera = self.camera_nanny.update_params(self.camera,self.data_handler.camera_params)
        camera_select = self.data_handler.camera_params.key
        if type(camera_select) == bytes: 
            camera_select = camera_select.decode()
        self.camera_connect.emit(camera_select)

    def honorable_death(self):
        try:
            self.camera.stop_grab()
        except:
            pass
        print(f"{self.name}: All images captured.")
        print(f"{self.name} has died honorably.")
        time.sleep(0.1)
        self.honorable_death_signal.emit()
        self.cam_status_signal.emit(-1)
        return True
    
    def dishonorable_death(self,delete_data=True):
        try:
            self.camera.stop_grab()
        except:
            pass
        self.data_handler.remove_incomplete_data(delete_data)
        print(f"{self.name} has died dishonorably.")
        time.sleep(0.1)
        self.dishonorable_death_signal.emit()
        self.cam_status_signal.emit(-1)
        return True

    def grab_loop(self):
        N_img = int(self.data_handler.params.N_img)
        N_shots = int(self.data_handler.params.N_shots)
        N_pwa_per_shot = int(self.data_handler.params.N_pwa_per_shot)
        self.camera_grab_start.emit(N_img,N_shots,N_pwa_per_shot)
        self.camera.start_grab(N_img,output_queue=self.queue,
                    check_interrupt_method=self.break_check)
        if not self.interrupted:
            self.death = self.honorable_death

    def break_check(self):
        return self.interrupted
