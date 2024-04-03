from pylablib.devices import Andor
from pylablib.devices.interface.camera import trim_frames
import numpy as np

from queue import Queue
from PyQt6.QtCore import QThread, pyqtSignal

from pylablib.devices.Andor.atmcd32d_lib import wlib as lib

class AndorEMCCD(Andor.AndorSDK2Camera):
    def __init__(self, ExposureTime=0., gain = 30, vs_speed:int=2, vs_amp:int=1):
        # overwrite a broken method in the parent class
        self._initial_setup_temperature = self._initial_setup_temperature_fixed
        # init the parent class
        super().__init__(temperature=-60,fan_mode="full")
        # run startup setting methods
        self.set_EMCCD_gain(gain=gain)
        self.set_exposure(ExposureTime)
        self.set_trigger_mode("ext")
        self.setup_shutter(mode="open")
        self.set_vsspeed(vs_speed)
        self.set_vsamplitude(vs_amp)
        self.set_acquisition_mode("single")
        self.set_read_mode("image")
        self.set_cooler_mode(mode=1)

    def set_cooler_mode(self, mode:int = 1):
        lib.SetCoolerMode(mode)

    def set_vsamplitude(self, vs_amp:int = 0):
        lib.SetVSAmplitude(vs_amp)

    def Close(self):
        self.setup_shutter(mode="closed")
        self.close()

    def Open(self):
        self.setup_shutter(mode="open")
        self.open()

    def start_grab(self, N_img, output_queue:Queue,
                    timeout=10., missing_frame="skip", return_info=False, buff_size=None):
        """
        Snap `nframes` images (with preset image read mode parameters)
        Modified from pylablib.devices.interface.camera.
        
        `buff_size` determines buffer size (if ``None``, use the default size).
        Timeout is specified for a single-frame acquisition, not for the whole acquisition time.
        `missing_frame` determines what to do with frames which have been lost:
        can be ``"none"`` (replacing them with ``None``), ``"zero"`` (replacing them with zero-filled frame),
        or ``"skip"`` (skipping them, while still keeping total returned frames number to `n`).
        If ``return_info==True``, return tuple ``(frames, infos)``, where ``infos`` is a list of frame info tuples (camera-dependent);
        if some frames are missing and ``missing_frame!="skip"``, the corresponding frame info is ``None``.
        """
        if self.get_frame_format()=="array":
            try:
                self.set_frame_format("chunks")
                result=self.grab(nframes=N_img,frame_timeout=timeout,missing_frame=missing_frame,return_info=return_info,buff_size=buff_size)
                return tuple(np.concatenate(r,axis=0) for r in result) if return_info else np.concatenate(result,axis=0)
            finally:
                self.set_frame_format("array")
        acq_params=self._get_grab_acquisition_parameters(N_img,buff_size)
        frames,info,nacq=[],[],0
        self.start_acquisition(**acq_params)
        try:
            while nacq<N_img:
                self.wait_for_frame(timeout=timeout)
                print(f'gotem (img {nacq+1}/{N_img})') # added this line to give print statements
                if return_info:
                    new_frames,new_info,rng=self.read_multiple_images(missing_frame=missing_frame,return_info=True,return_rng=True)
                    info+=new_info
                else:
                    new_frames,rng=self.read_multiple_images(missing_frame=missing_frame,return_rng=True)
                for frame in new_frames:
                        if isinstance(frame,np.ndarray):
                            img_timestamp = 0.
                            output_queue.put((frame,img_timestamp,nacq))
                frames+=new_frames
                nacq+=rng[1]-rng[0]
            frames,info=trim_frames(frames,N_img,(info if return_info else None),chunks=self.get_frame_format()=="chunks")
            return (frames,info) if return_info else frames
        finally:
            self.stop_acquisition()

    def _initial_setup_temperature_fixed(self):
        if self._start_temperature=="off":
            trng=self.get_temperature_range()
            self.set_temperature(trng[1] if trng else 0,enable_cooler=False)
        else:
            if self._start_temperature is None:
                trng=self.get_temperature_range()
                if trng:
                    self._start_temperature=trng[0]+int((trng[1]-trng[0])*0.2)
                else:
                    self._start_temperature=0
            self.set_temperature(self._start_temperature,enable_cooler=True)

    def stop_grab(self):
        try:
            self.stop_acquisition()
        except:
            pass