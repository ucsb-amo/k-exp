from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential
from kexp.util.artiq.expt_params import ExptParams

from kexp.control.cameras.basler_usb import BaslerUSB

import numpy as np
import pypylon.pylon as py

import matplotlib.pyplot as plt

class test(EnvExperiment):
    def build(self):
        self.core = self.get_device("core")
        self.ttl = self.get_device("ttl4")
        
        self.camera = BaslerUSB(ExposureTime=10000)
        self.images = []
        self.images_timestamps = []
        
        self.p = ExptParams()
        self.p.t_trigger_us = 2
        self.p.N_img = 10
        self.p.img_delay_ms = 100

    @rpc(flags={"async"})
    def StartTriggeredGrab(self):
        self.camera.StartGrabbingMax(self.p.N_img, py.GrabStrategy_LatestImages)
        count = 0
        while self.camera.IsGrabbing():
            grab = self.camera.RetrieveResult(1000000,py.TimeoutHandling_ThrowException)
            if grab.GrabSucceeded():
                img = grab.GetArray()
                img_t = grab.TimeStamp
                self.images.append(img)
                self.images_timestamps.append(img_t)
                count += 1
            if count >= self.p.N_img:
                break
        self.camera.Close()

    @kernel
    def run(self):
        self.core.reset()

        self.StartTriggeredGrab()
        self.core.break_realtime()
        delay(0.5*s)
        
        for i in range(self.p.N_img):
            self.ttl.pulse(self.p.t_trigger_us * us)
            delay(self.p.img_delay_ms * ms)

    def analyze(self):

        print(np.diff(self.images_timestamps) / 1.e9)
        print(len(self.images))


        


