from artiq.experiment import *
from kexp import Base
import os
from kexp.control.misc.slm_TEST import SLM
import numpy as np

class mot_observe(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self, setup_camera = False)
        self.slm = SLM() 

    @kernel
    def run(self):
        
        self.init_kernel()
        delay(50*ms)
        self.mot_observe()
        self.slm.write_phase_spot(
            diameter = 187,
            phase = 1.87,
            x_center = 250,
            y_center = 400
        )       

    def analyze(self):

        print("Done!")