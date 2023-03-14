from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential

import pypylon.pylon as py
from kexp.control.cameras.basler_usb import BaslerUSB

from kexp.util.artiq.expt_params import ExptParams
from kexp.config.dds_state import defaults as default_dds

@rpc(flags={"async"})
def StartTriggeredGrab(expt, N, img_list, img_tstamp_list):
    '''
    Start camera waiting for triggers, wait for N images.

    Parameters
    ----------
    N: int
        Number of images to wait for.
    '''
    expt.camera.StartGrabbingMax(N, py.GrabStrategy_LatestImages)
    count = 0
    while expt.camera.IsGrabbing():
        grab = expt.camera.RetrieveResult(1000000,py.TimeoutHandling_ThrowException)
        if grab.GrabSucceeded():
            print(f'gotem (img {count+1}/{NoDefault})')
            img = grab.GetArray()
            img_t = grab.TimeStamp
            img_list.append(img)
            img_tstamp_list.append(img_t)
            count += 1
        if count >= N:
            break
    expt.camera.StopGrabbing()
    expt.camera.Close()

def prepare_camera(expt, params):
    expt.camera = BaslerUSB()
    params.t_exposure_delay = expt.camera.BslExposureStartDelay.GetValue() * 1.e-6
    params.t_pretrigger = params.t_exposure_delay