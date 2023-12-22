from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.config import camera_params
from kexp.util.artiq.async_print import aprint

import numpy as np

class test(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=False)

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        # self.dds.d1_3d_c.set_dds_gamma(delta=self.params.detune_d1_c_gm,amplitude=0.3,v_pd=5.0)
        # self.dds.d1_3d_c.on()

        self.gm(1.e-3)
        
    def analyze(self):

        print("Done!")