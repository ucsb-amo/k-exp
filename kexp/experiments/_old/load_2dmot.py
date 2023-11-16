from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

import numpy as np

class load_2dmot(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=False)
        # Base.__init__(self,setup_camera=False)

        self.run_info._run_description = "watch 2d mot with imaging light cone"

        ## Parameters

        self.p = self.params

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.load_2D_mot(self.p.t_2D_mot_load_delay * s)
        self.dds.imaging_fake.set_dds(amplitude=0.188)
        self.dds.imaging_fake.on()

    def analyze(self):
        print("Done!")