from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential

import pypylon.pylon as py
from kexp.control.cameras.basler_usb import BaslerUSB

from kexp.util.artiq.expt_params import ExptParams
from kexp.experiments.base import devices

class camera():
    def __init__(self):
        self.camera = BaslerUSB()

    @rpc(flags={"async"})
    def StartTriggeredGrab(self, N, img_list, img_tstamp_list):
        '''
        Start camera waiting for triggers, wait for N images.

        Parameters
        ----------
        N: int
            Number of images to wait for.
        '''
        self.camera.StartGrabbingMax(N, py.GrabStrategy_LatestImages)
        count = 0
        while self.camera.IsGrabbing():
            grab = self.camera.RetrieveResult(1000000,py.TimeoutHandling_ThrowException)
            if grab.GrabSucceeded():
                print(f'gotem (img {count+1}/{NoDefault})')
                img = grab.GetArray()
                img_t = grab.TimeStamp
                img_list.append(img)
                img_tstamp_list.append(img_t)
                count += 1
            if count >= N:
                break
        self.camera.StopGrabbing()
        self.camera.Close()
        