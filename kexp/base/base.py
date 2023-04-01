from artiq.experiment import *
from artiq.experiment import delay_mu, delay

from kexp.config.expt_params import ExptParams

from kexp.control.cameras.basler_usb import BaslerUSB
import pypylon.pylon as py

from kexp.base.sub.devices import devices
from kexp.base.sub.cooling import cooling
from kexp.base.sub.image import image
import numpy as np

from kexp.util.data.data_vault import DataSaver

class Base(devices, cooling, image):
    def __init__(self,setup_camera=True):
        super().__init__()

        self.params = ExptParams()

        if setup_camera:
            self.camera = BaslerUSB()
            self.images = []
            self.image_timestamps = []

        self.prepare_devices()

        ds = DataSaver()
        self._rid = ds._get_rid()
        self._ridstr = " Run ID: "+ str(self._rid)

    @rpc(flags={"async"})
    def StartTriggeredGrab(self, N):
        '''
        Start camera waiting for triggers, wait for N images.

        Parameters
        ----------
        N: int
            Number of images to wait for.
        '''
        Nimg = int(N)
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
