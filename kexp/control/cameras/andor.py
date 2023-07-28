from pylablib.devices import Andor
from pylablib.devices.interface.camera import trim_frames
import numpy as np

class AndorEMCCD(Andor.AndorSDK2Camera):
    def __init__(self, ExposureTime=0., gain = 30, vsspeed = .9):
        super().__init__()
        self.set_temperature(temperature=-80)
        self.set_EMCCD_gain(gain=30)
        self.set_exposure(ExposureTime)
        self.set_trigger_mode("ext")
        self.setup_shutter(mode="open")
        self.set_vsspeed(vsspeed=.9)
        self.set_acquisition_mode("single")
        self.set_read_mode("image")

    def Close(self):
        self.setup_shutter(mode="closed")
        self.close()

    def grab_andor(self, nframes=1, frame_timeout=5., missing_frame="skip", return_info=False, buff_size=None):
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
                result=self.grab(nframes=nframes,frame_timeout=frame_timeout,missing_frame=missing_frame,return_info=return_info,buff_size=buff_size)
                return tuple(np.concatenate(r,axis=0) for r in result) if return_info else np.concatenate(result,axis=0)
            finally:
                self.set_frame_format("array")
        acq_params=self._get_grab_acquisition_parameters(nframes,buff_size)
        frames,info,nacq=[],[],0
        self.start_acquisition(**acq_params)
        try:
            while nacq<nframes:
                self.wait_for_frame(timeout=frame_timeout)
                print(f'gotem (img {nacq+1}/{nframes})') # added this line to give print statements
                if return_info:
                    new_frames,new_info,rng=self.read_multiple_images(missing_frame=missing_frame,return_info=True,return_rng=True)
                    info+=new_info
                else:
                    new_frames,rng=self.read_multiple_images(missing_frame=missing_frame,return_rng=True)
                frames+=new_frames
                nacq+=rng[1]-rng[0]
            frames,info=trim_frames(frames,nframes,(info if return_info else None),chunks=self.get_frame_format()=="chunks")
            return (frames,info) if return_info else frames
        finally:
            self.stop_acquisition()