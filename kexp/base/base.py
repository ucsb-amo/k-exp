from artiq.experiment import *
from artiq.experiment import delay_mu, delay

import pypylon.pylon as py
import numpy as np

from kexp.config import ExptParams
from kexp.control import BaslerUSB
from kexp.base.sub import Devices, Cooling, Image, Dealer
from kexp.util.data import DataSaver, RunInfo

import kexp.config.camera_params as camera_params
# also import the andor camera parameters

class Base(Devices, Cooling, Image, Dealer):
    def __init__(self,setup_camera=True,absorption_image=True,basler_imaging=True):
        super().__init__()

        self.params = ExptParams()

        if setup_camera:
            if basler_imaging:
                if absorption_image:
                    self.camera_params = camera_params.basler_absorp_camera_params
                else:
                    self.camera_params = camera_params.basler_fluor_camera_params
                self.camera = BaslerUSB(BaslerSerialNumber=self.camera_params.serial_no)
                self.StartTriggeredGrab = self.start_triggered_grab_basler
            else:
                self.StartTriggeredGrab = self.start_triggered_grab_andor
                # self.camera_params = acp
                raise ValueError("Andor is not set up yet.")
        self.images = []
        self.image_timestamps = []

        self.prepare_devices()

        self.run_info = RunInfo(self)
        self._ridstr = " Run ID: "+ str(self.run_info.run_id)

        self.xvarnames = []
        self.sort_idx = []
        self.sort_N = []

        self.ds = DataSaver()

    @rpc(flags={"async"})
    def start_triggered_grab_basler(self):
        '''
        Start camera waiting for triggers, wait for N images.

        Parameters
        ----------
        N: int
            Number of images to wait for.
        '''
        Nimg = int(self.params.N_img)
        self.camera.StartGrabbingMax(Nimg, py.GrabStrategy_LatestImages)
        count = 0
        while self.camera.IsGrabbing():
            grab = self.camera.RetrieveResult(1000000, py.TimeoutHandling_ThrowException)
            if grab.GrabSucceeded():
                print(f'gotem (img {count+1}/{Nimg})')
                img = np.uint8(grab.GetArray())
                img_t = grab.TimeStamp
                self.images.append(img)
                self.image_timestamps.append(img_t)
                count += 1
            if count >= Nimg:
                break
        self.camera.StopGrabbing()
        self.camera.Close()

    @rpc(flags={"async"})
    def start_triggered_grab_andor(self):
        pass

    def get_N_img(self):
        N_img = 1
        msg = ""
        
        for key in self.xvarnames:
            xvar = vars(self.params)[key]
            if not isinstance(xvar,list) and not isinstance(xvar,np.ndarray):
                xvar = [xvar]
            N_img = N_img * len( vars(self.params)[key] )
            msg += f" {len(xvar)} values of {key}."

        msg += f" {N_img} total shots."

        N_img = 3 * N_img # 3 shots per value of independent variable (xvar)

        msg += f" {N_img} total images expected."
        print(msg)
        self.params.N_img = N_img
