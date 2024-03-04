from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.config import camera_params
from kexp.util.artiq.async_print import aprint

import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=False,camera_select="xy_basler")

        self.xvar('dummy',np.linspace(1.,1.,1)*1.e-3)

        self.finish_build()

    @kernel
    def scan_kernel(self):
        self.ttl.xy_basler.pulse(self.camera_params.t_camera_trigger)
        delay(30*ms)
        self.ttl.xy_basler.pulse(self.camera_params.t_camera_trigger)
        delay(30*ms)
        self.ttl.xy_basler.pulse(self.camera_params.t_camera_trigger)

        delay(1*s)

    @kernel
    def run(self):
        
        self.init_kernel()
        self.scan()

    def analyze(self):

        print("Done!")