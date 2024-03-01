from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.config import camera_params
from kexp.util.artiq.async_print import aprint

import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select="xy_basler")

        self.xvar('t_tof',np.linspace(1.,3.,3)*1.e-3)

        self.finish_build()

    @kernel
    def scan_kernel(self):
        print(self.params.t_tof)
        delay(1*s)
        self.abs_image()

    @kernel
    def run(self):
        
        self.init_kernel()
        self.StartTriggeredGrab()
        print(self.camera_params.connection_delay)
        # delay(self.camera_params.connection_delay)
        self.scan()

    def analyze(self):

        self.camera.Close()

        import os
        expt_filepath = os.path.abspath(__file__)
        self.ds.save_data(self, expt_filepath)

        print("Done!")