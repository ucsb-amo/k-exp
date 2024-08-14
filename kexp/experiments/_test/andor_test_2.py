from artiq.experiment import *
from artiq.coredevice.adf5356 import ADF5356
from artiq.coredevice.mirny import Mirny
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.util.artiq.async_print import aprint

import numpy as np

class test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)

        self.xvar('dummy',[1]*10)

        self.camera_params.em_gain = 290.
        self.camera_params.exposure_time = 5.e-6
        self.camera_params.amp_imaging = 0.08
        self.camera_params.t_dark_image_delay = 0.2
        self.camera_params.t_light_only_image_delay = 0.2
        self.camera_params.t_camera_trigger = 100.e-9
        self.p.t_imaging_pulse = 5.e-6

        # self.xvar('t_imaging_pulse',np.linspace(1.,25.,10)*1.e-6)

        self.finish_prepare()

    @kernel
    def scan_kernel(self):
        self.abs_image()
        delay(0.2*s)

        # self.dds.imaging.on()
        # self.ttl.camera.pulse(10.e-6)
        # delay(1.)
        # self.ttl.camera.pulse(10.e-6)
        # self.dds.imaging.off()
        # delay(1.)
        # self.ttl.camera.pulse(10.e-6)

    @kernel
    def run(self):

        self.init_kernel()
        self.scan()
        delay(1*s)

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)