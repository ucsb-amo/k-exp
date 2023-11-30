from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.config import camera_params
from kexp.util.artiq.async_print import aprint

import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=False)

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.release()

        self.abs_image()
        
    def analyze(self):

        print("Done!")