from artiq.experiment import *
from kexp import Base
import os

import numpy as np

class mot_observe(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self, setup_camera = False)
        self.finish_prepare()

    @kernel
    def run(self):
        
        self.init_kernel(setup_awg=False,
                         setup_slm=False,
                         init_shuttler=False)
        delay(50*ms)
        self.mot_observe()

    def analyze(self):

        print("Done!")